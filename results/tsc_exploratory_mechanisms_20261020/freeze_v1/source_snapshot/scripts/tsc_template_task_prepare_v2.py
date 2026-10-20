"""Extend the CPU-only blinded Hotpot selection with blinded Repo sources."""
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
from scripts.tsc_template_task_protocol_v2 import MODELS,DISK,STUDY,prepared,budget
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import ordered_candidates
from scripts.tsc_revision_build_inputs import source
from scripts.phase17_live_common import digest
from scripts.tsc_template_task_prepare_v1 import read,sha,write,jsonl

def main(root):
    study=root/STUDY;read(study/'input_selection_complete_v1.json')
    protocol=read(study/'protocol_v2.json')
    excluded=set(read(study/'input_selection_complete_v1.json')['excluded_after']);assert len(excluded)==734
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    assert sha(pool)==read(root/'results/tsc_revision_r4/inputs/input_commitment_v1.json')['source_pool_sha256']
    tokenizers={m:AutoTokenizer.from_pretrained(str(Path(DISK)/'models'/m),local_files_only=True) for m in MODELS}
    rows=[json.loads(s) for s in pool.read_text(encoding='utf-8').splitlines() if s.strip()]
    allsets=[]
    for kind,count,seed in [('development',2,2026101906),('validation',3,2026101907)]:
        out=study/('inputs_'+kind+'_v2');out.mkdir();old=study/('inputs_'+kind+'_v1')
        qa=[json.loads(s) for s in (old/'original_sessions_v1.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(qa)==count and all(r['revision_family']=='HotpotQA' for r in qa)
        originals,chosen,ledger,shapes=[],[],[],[];before=sorted(excluded)
        def capacity(value,exhaustive):
            value=deepcopy(value);value['revision_input_fidelity']={'protocol':'structure-preserving-window-v2'};rr=[]
            for model,tok in tokenizers.items():
                for tenant in (range(8) if exhaustive else (7,)):
                    for turn in (range(9) if exhaustive else (0,8)):
                        for level in ('L0','L3'):
                            _,_,messages=prepared(value,tenant,turn,level)
                            for segment in value['segments']:
                                if segment['type'] in ('CODE_PREFIX','USER_QUERY'):assert segment['text'] in messages[1]['content']
                            ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
                            if len(ids)+budget(value)+1+(0 if exhaustive else 128)>16384:return dict(fits=False,model=model,level=level,prompt_tokens=len(ids))
                            rr.append(dict(model=model,source_group=source(value),tenant=tenant,turn=turn,level=level,
                                prompt_tokens=len(ids),output_budget=budget(value),prompt_ids_sha256=digest(ids)))
            if exhaustive:capacity.last=rr
            return dict(fits=True,shapes=len(rr))
        def pack(value,selection):
            result=pack_task_input(value,lambda x:capacity(x,False),validate=lambda x:capacity(x,True))
            ledger.append(dict(source_group=source(value),selection=selection,packing={k:v for k,v in result.items() if k!='sample'}))
            if result['sample'] is None:return False
            assert len(capacity.last)==432
            originals.append(value);chosen.append(result['sample']);shapes.extend(capacity.last)
            print(json.dumps(dict(kind=kind,family=value['revision_family'],source=source(value),packing=result['status'])),flush=True)
            return True
        for value in qa:assert pack(value,'same Hotpot source selected under v1 before any GPU outcome')
        found=0
        for row in ordered_candidates(rows,excluded,'RepoBench',seed):
            group=source(row);namespace='template-task-'+hashlib.sha256(group.encode()).hexdigest()[:16]
            value={**row,'revision_session_id':namespace,'revision_source_group':group,'revision_family':'RepoBench',
                   'revision_input_fidelity':{'protocol':'structure-preserving-window-v2'}}
            if not pack(value,dict(seed=seed,hash=hashlib.sha256((str(seed)+':'+group).encode()).hexdigest())):continue
            excluded.add(group);found+=1
            if found==count:break
        assert found==count
        for name,rr in [('original_sessions_v2.jsonl',originals),('sessions_v2.jsonl',chosen),('CPU_shapes_v2.jsonl',shapes)]:jsonl(out/name,rr)
        receipt=dict(kind=kind,sources=[dict(source=source(s),family=s['revision_family']) for s in chosen],
            new_source_outcomes_used=False,old_Hotpot_sources_preserved=True,exclusions_before_Repo=before,
            Repo_seed=seed,packing_ledger=ledger,actual_tokenizer_shapes=len(shapes),all_fit_16K=True,protocol_sha256=sha(study/'protocol_v2.json'),source_sha256=sha(Path(__file__)))
        write(out/'receipt_v2.json',receipt);allsets.append(dict(kind=kind,sources=receipt['sources']))
    write(study/'input_selection_complete_v2.json',dict(sets=allsets,excluded_after=sorted(excluded),model_outputs_used=0,
        source_pool_sha256=sha(pool),protocol_sha256=sha(study/'protocol_v2.json')))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
