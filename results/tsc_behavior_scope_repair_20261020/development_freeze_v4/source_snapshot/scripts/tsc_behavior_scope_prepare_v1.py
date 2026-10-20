"""Blinded source-disjoint inputs; no output, answer or gold-location filtering."""
import os
for k,v in dict(TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',USE_TORCH='0',USE_TF='0',CUDA_VISIBLE_DEVICES='').items():os.environ[k]=v
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transformers import AutoTokenizer
from scripts.tsc_template_task_protocol_v2 import prepared,budget,DISK
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import ordered_candidates
from scripts.tsc_revision_build_inputs import source
from scripts.phase17_live_common import digest

STUDY=Path('results/tsc_behavior_scope_repair_20261020')
MODELS=['Qwen3-8B','Mistral-7B-Instruct-v0.3']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def jsonl(p,rr):
    with p.open('x',encoding='utf-8') as f:
        for r in rr:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')

def main(root):
    study=root/STUDY;protocol=read(study/'protocol_v1.json')
    former=root/'results/tsc_template_task_serving_20261019/input_selection_complete_v2.json'
    excluded=set(read(former)['excluded_after'])
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    assert sha(pool)==read(former)['source_pool_sha256']
    allrows=[json.loads(s) for s in pool.read_text(encoding='utf-8').splitlines() if s.strip()]
    toks={m:AutoTokenizer.from_pretrained(str(Path(DISK)/'models'/m),local_files_only=True) for m in MODELS}
    sets=[]
    for kind,counts in [('development',{'HotpotQA':2,'RepoBench':1}),('validation',{'HotpotQA':3,'RepoBench':1})]:
        out=study/('inputs_'+kind+'_v1');out.mkdir();before=sorted(excluded)
        chosen=[];original=[];ledger=[];shapes=[]
        def capacity(sample,exhaustive):
            rr=[]
            for model,tok in toks.items():
                for tenant,turn in [(0,0),(0,1),(1,1)]:
                    for level in ['L0','L3']:
                        _,_,messages=prepared(sample,tenant,turn,level)
                        for segment in sample['segments']:
                            if segment['type'] in ['CODE_PREFIX','USER_QUERY']:assert segment['text'] in messages[1]['content']
                        ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
                        if len(ids)+budget(sample)+1+(0 if exhaustive else 128)>16384:return {'fits':False}
                        rr.append(dict(model=model,source_group=source(sample),tenant=tenant,turn=turn,level=level,
                                       prompt_tokens=len(ids),prompt_ids_sha256=digest(ids)))
            if exhaustive:capacity.last=rr
            return {'fits':True}
        for family,count in counts.items():
            seed=protocol['seeds'][kind][family];found=0
            for row in ordered_candidates(allrows,excluded,family,seed):
                group=source(row);sample={**deepcopy(row),'revision_family':family,'revision_source_group':group,
                    'revision_session_id':'behavior-scope-'+hashlib.sha256(group.encode()).hexdigest()[:16],
                    'revision_input_fidelity':{'protocol':'structure-preserving-window-v2'}}
                result=pack_task_input(sample,lambda x:capacity(x,False),validate=lambda x:capacity(x,True))
                ledger.append(dict(source=group,family=family,seed=seed,packing={k:v for k,v in result.items() if k!='sample'}))
                if result['sample'] is None:continue
                chosen.append(result['sample']);original.append(sample);shapes.extend(capacity.last);excluded.add(group);found+=1
                print(json.dumps(dict(set=kind,source=group,packing=result['status'])),flush=True)
                if found==count:break
            assert found==count
        jsonl(out/'sessions_v1.jsonl',chosen);jsonl(out/'original_sessions_v1.jsonl',original);jsonl(out/'CPU_shapes_v1.jsonl',shapes)
        receipt=dict(sources=[dict(source=source(s),family=s['revision_family']) for s in chosen],excluded_before=before,
                     packing_ledger=ledger,protocol_sha256=sha(study/'protocol_v1.json'),source_pool_sha256=sha(pool),
                     model_outputs_used=0,actual_shapes=len(shapes),source_sha256=sha(Path(__file__)))
        write(out/'receipt_v1.json',receipt);sets.append(receipt['sources'])
    write(study/'input_selection_v1.json',dict(status='PASS',sets=sets,excluded_after=sorted(excluded),new_model_outputs=0,source_sha256=sha(Path(__file__))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
