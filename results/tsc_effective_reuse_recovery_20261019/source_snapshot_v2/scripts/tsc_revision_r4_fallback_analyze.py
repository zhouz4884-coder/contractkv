"""Explain frozen fallback score changes offline without altering the scorer."""
import argparse
from collections import Counter
import csv
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,first_divergence
from scripts.phase20a_official_quality import normalize_answer,standard_score,qa_f1,references
from scripts.tsc_revision_r4_live_summary import MODELS

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Preserve supplement version')
 config=json.loads((a.root/'freeze.json').read_text(encoding='utf-8'))['protocol'];samples={}
 for study,path in config['input_files'].items():samples[study]={s['revision_source_group']:s for s in read(a.root/'source_snapshot'/path)}
 pairs=list(csv.DictReader((a.root/'analysis/quality_pairs_v1.csv').open(encoding='utf-8')))
 cases=[];cache={}
 def rows(study,model,policy,rep):
  key=study,model,policy,rep
  if key not in cache:
   alias=next(k for k,v in MODELS.items() if v==model);path=a.root/'cells'/f'{study}_{alias}_{policy}_r{rep}'/'raw.jsonl';cache[key]=(read(path),sha(path))
  return cache[key]
 for pair in pairs:
  if pair['policy']!='risk-tail' or pair['effective_level']!='L0' or float(pair['quality_drop'])<=.03:continue
  study,model,rep=pair['study'],pair['model'],pair['repeat'];sid,turn=pair['session_id'],int(pair['turn_id']);sample=samples[study][pair['source_group']];outputs={}
  for policy in ('raw-order','risk-tail'):
   records,digest=rows(study,model,policy,rep);r=next(r for r in records if r['row_type']=='future' and r['session_id']==sid and r['turn_id']==turn)
   score,metric,_=standard_score(sample['dataset'],sample['task'],r['output_text'],sample.get('answer',''))
   if abs(score-r['task_score'])>1e-12:raise ValueError('Frozen metric mismatch')
   outputs[policy]={k:r[k] for k in ('output_text','output_token_ids','prompt_token_ids','prompt_ids_sha256','effective_level','prefix_hit_tokens','new_prefill_tokens','task_score','finish_reason')}
   outputs[policy]['raw_file_sha256']=digest
   if metric=='qa_f1':
    ref=max(references(sample.get('answer','')),key=lambda ref:qa_f1(r['output_text'],ref));pt=normalize_answer(r['output_text']).split();gt=normalize_answer(ref).split()
    outputs[policy]['metric_detail']={'normalized_prediction':pt,'best_normalized_reference':gt,'overlap_with_multiplicity':sum((Counter(pt)&Counter(gt)).values()),'prediction_words':len(pt),'reference_words':len(gt)}
   if policy=='risk-tail':outputs[policy]['scope_decisions']=[{'issued':x['certificate_issued'],'reason':x['failure_reason'],'GPU_calls':len(x['attempts'])} for x in records if x['row_type']=='verification' and x['certificate_namespace']==r['certificate_namespace'] and x['query_scope']==r['query_scope']]
  raw,new=outputs['raw-order'],outputs['risk-tail']
  if raw['prompt_token_ids']!=new['prompt_token_ids']:raise ValueError('Unexpected L0 prompt mismatch')
  raw.pop('prompt_token_ids');new.pop('prompt_token_ids');x,y=raw['output_text'].split(),new['output_text'].split()
  edits=[{'operation':tag,'raw_words':x[i:j],'policy_words':y[k:l]} for tag,i,j,k,l in SequenceMatcher(None,x,y).get_opcodes() if tag!='equal']
  cases.append({'study':study,'model':model,'repeat':int(rep),'session_id':sid,'turn_id':turn,'source_group':pair['source_group'],'outputs':outputs,
                'prompt_IDs_exactly_equal':True,'first_output_ID_divergence':first_divergence(raw['output_token_ids'],new['output_token_ids']),
                'text_edits':edits,'material_drop_retained':True,'mechanism_cause':'unknown; no batch/numerical cause inferred from ID identity alone'})
 result={'schema_version':'tsc-r4.fallback-metric-supplement.v2','offline_after_outputs_only':True,'cases':cases,'case_count':len(cases),
         'raw_archive_sha256':json.loads((a.root/'raw_evidence_archive_manifest_v1.json').read_text())['archive_sha256'],
         'scorer_sha256':sha(Path('scripts/phase20a_official_quality.py')),'analysis_source_sha256':sha(Path(__file__)),
         'generation_or_grading_changed':False,'no_semantic_judge_score_added':True,'all_frozen_material_drops_retained':True}
 a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'cases':len(cases),'edits':[c['text_edits'] for c in cases]}))

if __name__=='__main__':main()
