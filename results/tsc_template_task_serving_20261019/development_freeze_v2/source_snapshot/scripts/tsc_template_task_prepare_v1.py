"""Blind new-source 16K packing and every declared tokenizer shape, CPU only."""
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
from scripts.tsc_template_task_protocol_v1 import MODELS,DISK,STUDY,prepared
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import ordered_candidates
from scripts.tsc_revision_build_inputs import source
from scripts.phase17_live_common import digest

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
def jsonl(p,rr):
    with p.open('x',encoding='utf-8',newline='\n') as f:
        for r in rr:f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n')

def main(root):
    study=root/STUDY;protocol=read(study/'protocol_v1.json')
    former=read(root/'results/tsc_effective_reuse_recovery_20261019/input_selection_complete_v1.json')
    excluded=set(former['excluded_after_all_selection']) if 'excluded_after_all_selection' in former else set()
    if not excluded:
        known=read(root/'results/tsc_effective_reuse_recovery_20261019/inputs_validation_v1/preparation_receipt_v1.json')
        excluded.update(known['excluded_source_groups_before']);excluded.update(known['selected_source_groups'])
    assert len(excluded)==729
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    assert sha(pool)==read(root/'results/tsc_revision_r4/inputs/input_commitment_v1.json')['source_pool_sha256']
    registry=read(root/'results/tsc_revision_mechanism_controls_20261018/preflight_v3/model_asset_registry_v1.json')
    for m in registry['models']:
        if m['model'] not in MODELS:continue
        for a in m['files']:
            if a['file'].startswith(('tokenizer','special_tokens','vocab','merges')):assert sha(Path(DISK)/'models'/m['model']/a['file'])==a['sha256']
    tokenizers={m:AutoTokenizer.from_pretrained(str(Path(DISK)/'models'/m),local_files_only=True) for m in MODELS}
    rr=[json.loads(s) for s in pool.read_text(encoding='utf-8').splitlines() if s.strip()]
    sets=[]
    for kind,count,seed in [('development',2,2026101904),('validation',3,2026101905)]:
        target=study/('inputs_'+kind+'_v1');target.mkdir();before=sorted(excluded)
        originals,chosen,ledger,shapes=[],[],[],[]
        def capacity(sample,exhaustive):
            sample=deepcopy(sample);sample['revision_input_fidelity']={'protocol':'structure-preserving-window-v2'}
            out=[]
            for model,tok in tokenizers.items():
                for tenant in (range(10) if exhaustive else (9,)):
                    for turn in (range(7) if exhaustive else (0,6)):
                        for level in ('L0','L3'):
                            _,_,messages=prepared(sample,tenant,turn,level)
                            ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
                            if len(ids)+129+(0 if exhaustive else 128)>16384:return dict(fits=False,model=model,prompt_tokens=len(ids),level=level)
                            out.append(dict(model=model,source_group=source(sample),tenant=tenant,turn=turn,level=level,prompt_tokens=len(ids),output_budget=128,prompt_ids_sha256=digest(ids)))
            if exhaustive:capacity.last=out
            return dict(fits=True,shapes=len(out))
        for row in ordered_candidates(rr,excluded,'HotpotQA',seed):
            group=source(row);namespace='template-task-'+hashlib.sha256(group.encode()).hexdigest()[:16]
            sample={**row,'revision_session_id':namespace,'revision_source_group':group,'revision_family':'HotpotQA',
                'revision_input_fidelity':{'protocol':'structure-preserving-window-v2'}}
            result=pack_task_input(sample,lambda x:capacity(x,False),validate=lambda x:capacity(x,True))
            ledger.append(dict(source_group=group,selection_hash=hashlib.sha256((str(seed)+':'+group).encode()).hexdigest(),packing={k:v for k,v in result.items() if k!='sample'}))
            if result['sample'] is None:continue
            packed=result['sample'];assert len(capacity.last)==420
            originals.append(sample);chosen.append(packed);shapes.extend(capacity.last);excluded.add(group)
            print(json.dumps(dict(kind=kind,source=group,packing=result['status'])),flush=True)
            if len(chosen)==count:break
        assert len(chosen)==count
        jsonl(target/'original_sessions_v1.jsonl',originals);jsonl(target/'sessions_v1.jsonl',chosen);jsonl(target/'CPU_shapes_v1.jsonl',shapes)
        receipt=dict(selected_source_groups=[source(x) for x in chosen],exclusions_before_selection=before,
            new_sources_not_previous_or_other_set=True,selection_seed=seed,source_pool_sha256=sha(pool),packing_ledger=ledger,
            models=MODELS,all_shapes_fit_16K=True,shapes=len(shapes),new_model_outputs=0,source_sha256=sha(Path(__file__)))
        write(target/'receipt_v1.json',receipt);sets.append(dict(kind=kind,selected_sources=receipt['selected_source_groups']))
    write(study/'input_selection_complete_v1.json',dict(sets=sets,excluded_after=sorted(excluded),new_model_outputs=0,protocol_sha256=sha(study/'protocol_v1.json')))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
