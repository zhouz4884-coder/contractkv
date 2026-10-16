"""CPU tokenizer-only context preflight; never load weights or generate answers."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_summarize import read
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.tsc_revision_r4_live_summary import MODELS

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ids_sha(ids):return hashlib.sha256(json.dumps(ids,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
 if a.output.exists():raise ValueError('Preserve preflight version')
 os.environ['TOKENIZERS_PARALLELISM']='false'
 from transformers import AutoTokenizer
 protocolpath=root/'configs/tsc_revision_r1r_validation_protocol_v1.json';protocol=json.loads(protocolpath.read_text())
 registrypath=root/'results/tsc_revision_r4/model_registry_v1.json';registry=json.loads(registrypath.read_text())
 catalogpath=root/'results/tsc_revision_r4/development_fit_v3/calibration_v1.json';catalog=json.loads(catalogpath.read_text())
 inputs={'single-session':root/'results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl','template-fanout':root/'results/tsc_revision_r4/inputs/heldout_fanout_v1.jsonl'}
 knownpath=root/'results/tsc_revision_r4/development_inputs_v1/cold_sessions.jsonl';known={s['revision_session_id']:s for s in read(knownpath)}
 records=[];controls=[];grouped=defaultdict(list)
 for alias,model in MODELS.items():
  entry=next(m for m in registry['models'] if m['model']==model)
  tokenizer=AutoTokenizer.from_pretrained(entry['model_path'],local_files_only=True)
  args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity=model,policy_hash='tokenizer-preflight-no-forward')
  def tokenize(messages):return list(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True))
  old=read(root/f'results/tsc_revision_r4/development_pilot_v1/cells/single-session_{alias}_raw-order_r1/raw.jsonl')
  for row in [r for r in old if r['row_type'] in ('warm','future')][:6]:
   ids=tokenize(prepare(args,known[row['session_id']],row['turn_id'])[1])
   controls.append({'model':model,'session_id':row['session_id'],'turn_id':row['turn_id'],'matches_actual_prior_API_IDs':ids==row['prompt_token_ids'],'tokens':len(ids)})
  for study,path in inputs.items():
   tenants=1 if study=='single-session' else 10
   for original in read(path):
    for tenant in range(tenants):
     sample=deepcopy(original)
     if tenants>1:sample['shared_template_id']=original['revision_session_id'];sample['revision_session_id']+=f'-tenant{tenant:02d}'
     for turn in range(10):
      case,raw,maximum,budget,_=prepare(args,sample,turn);rawids=tokenize(raw);level=catalog['models'][model][study][sample['revision_family']]['level']
      if level!='L0':
       order=layout_for_level(case,level,protocol['layout']['ladder'])['topological_order'];candidate=[raw[0],{'role':'user','content':_ordered_text(order,case['segments'])}];candidateids=tokenize(candidate)
      else:candidateids=rawids
      record={'model':model,'study':study,'source_group':sample['revision_source_group'],'session_id':sample['revision_session_id'],'turn_id':turn,
              'family':sample['revision_family'],'output_budget':budget,'raw_prompt_tokens':len(rawids),'candidate_level':level,'candidate_prompt_tokens':len(candidateids),
              'raw_tokenizer_IDs_sha256':ids_sha(rawids),'candidate_tokenizer_IDs_sha256':ids_sha(candidateids),
              'max_prompt_plus_output_budget':max(len(rawids),len(candidateids))+budget}
      records.append(record);grouped[model,study,sample['revision_family']].append(record)
 summaries=[{'model':m,'study':s,'family':f,'requests':len(rows),'raw_max_tokens':max(r['raw_prompt_tokens'] for r in rows),
             'candidate_max_tokens':max(r['candidate_prompt_tokens'] for r in rows),'max_prompt_plus_budget':max(r['max_prompt_plus_output_budget'] for r in rows)} for (m,s,f),rows in grouped.items()]
 limit=protocol['runtime']['max_model_len'];fits=all(r['max_prompt_plus_output_budget']<=limit for r in records);matched=all(r['matches_actual_prior_API_IDs'] for r in controls)
 result={'schema_version':'tsc-r4.cpu-tokenizer-preflight.v1','execution_complete':len(records)==4500 and len(controls)==18 and fits and matched,
         'no_weights_loaded_no_model_forward':True,'new50_model_outcomes_used':False,'CPU_tokenizer_counts_not_actual_serving_ID_evidence':True,
         'known_actual_API_ID_controls':controls,'all_known_API_IDs_match':matched,'requests_checked':len(records),'context_limit':limit,'all_fit':fits,
         'stable_word_limit':protocol['layout']['stable_word_limit'],'model_registry_sha256':sha(registrypath),'generation_protocol_sha256':sha(protocolpath),
         'calibration_sha256':sha(catalogpath),'input_sha256':{s:sha(p) for s,p in inputs.items()},'summary':summaries,'requests':records,'analysis_source_sha256':sha(Path(__file__))}
 a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'complete':result['execution_complete'],'requests':len(records),'actual_API_controls_match':matched,'all_fit':fits,'global_max_tokens_plus_budget':max(r['max_prompt_plus_output_budget'] for r in records)}))
 return 0 if result['execution_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
