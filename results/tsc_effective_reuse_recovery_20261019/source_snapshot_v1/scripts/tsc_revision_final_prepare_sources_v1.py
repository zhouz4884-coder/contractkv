"""Blind new-source packing after core archival; no model outcomes are read."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

for key,value in dict(TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',USE_TORCH='0',USE_TF='0',CUDA_VISIBLE_DEVICES='').items():
    os.environ[key]=value
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import source,family
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import ordered_candidates
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,ordered_text_preserving_segments
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase17_live_common import digest
from transformers import AutoTokenizer

MODELS=['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct']
DISK=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
def jsonl(p,rr):
    with p.open('x',encoding='utf-8') as f:
        for r in rr:f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n')


class Capacity:
    def __init__(self,generation,catalog,tokenizers,diagnostic):
        self.generation=generation;self.catalog=catalog;self.tokenizers=tokenizers;self.diagnostic=diagnostic
    def __call__(self,candidate,exhaustive):
        maxima={};count=0;guard=0 if exhaustive else 128;shapes=[]
        for model,tok in self.tokenizers.items():
            maximum=0
            args=SimpleNamespace(protocol=self.generation,experiment='free-generation',output_budget=0,
                model_identity=model,policy_hash='final-source-CPU-capacity-only')
            for tenant in range(10) if exhaustive else (9,):
                sample=deepcopy(candidate);sample['revision_input_fidelity']={'protocol':'structure-preserving-window-v2'}
                sample['shared_template_id']=candidate['revision_session_id'];sample['revision_session_id']+=f'-tenant{tenant:02d}'
                for turn in range(10) if exhaustive else (0,1,2):
                    case,raw,_,budget,_=prepare(args,sample,turn)
                    level='L3' if self.diagnostic else self.catalog['models'][model]['template-fanout'][sample['revision_family']]['level']
                    candidate_messages=raw
                    if level!='L0':
                        order=layout_for_level(case,level,self.generation['layout']['ladder'])['topological_order']
                        candidate_messages=[raw[0],dict(role='user',content=ordered_text_preserving_segments(order,case['segments']))]
                    for segment in sample['segments']:
                        if segment['type'] in ('CODE_PREFIX','USER_QUERY'):
                            assert segment['text'] in raw[1]['content'] and segment['text'] in candidate_messages[1]['content']
                    raw_ids=tok.apply_chat_template(raw,tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
                    compiled_ids=raw_ids if level=='L0' else tok.apply_chat_template(candidate_messages,tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
                    assert isinstance(raw_ids,list) and isinstance(compiled_ids,list)
                    if exhaustive:
                        for condition,ids in [('raw',raw_ids),('candidate',compiled_ids)]:
                            shapes.append(dict(model=model,source_group=source(sample),tenant=tenant,turn=turn,
                                condition=condition,level='L0' if condition=='raw' else level,
                                prompt_tokens=len(ids),output_budget=budget,prompt_ids_sha256=digest(ids)))
                    total=max(len(raw_ids),len(compiled_ids))+budget;count+=1;maximum=max(maximum,total)
                    if total+guard>16384:
                        return dict(fits=False,checked_request_variants=count,all_declared_variants_checked=False,
                            first_failure=dict(model=model,tenant=tenant,turn=turn,prompt_plus_budget=total),conservative_guard_tokens=guard)
            maxima[model]=maximum
        if exhaustive:self.last_success_shapes=shapes
        return dict(fits=True,checked_request_variants=count,all_declared_variants_checked=exhaustive,
            max_prompt_plus_budget_by_model=maxima,conservative_guard_tokens=guard)


def main(root):
    core=root/'results/tsc_revision_mechanism_controls_20261018'
    assert (core/'closure_v5.json').is_file() and (core/'raw_evidence_archive_manifest_v1.json').is_file(), 'Archive core diagnostics before new-source selection'
    assert len(read(core/'execution_state_v1.json')['completed_cells'])==9
    study=root/'results/tsc_task_faithful_open_arrival_20261018'
    protocol=read(study/'selection_protocol_v1.json')
    assert sha(Path(__file__))==protocol['selector_sha256']
    known_path=root/'results/tsc_final_existing_evidence_CPU_20261018/final_known_source_exclusions_v1.json'
    assert sha(known_path)==protocol['known_exclusion_inventory_sha256']
    known=read(known_path);excluded=set(known['excluded_source_groups']);assert len(excluded)==704
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    original=read(root/'results/tsc_revision_r4/inputs/input_commitment_v1.json')
    assert sha(pool)==original['source_pool_sha256']
    for rel,expected in protocol['unchanged_input_implementation_sha256'].items():assert sha(root/rel)==expected,rel
    generation=read(root/protocol['generation_protocol']);assert generation['layout']['stable_word_limit']==0
    catalog=read(root/protocol['selected_catalog'])
    registry=read(core/'preflight_v3/model_asset_registry_v1.json')
    for model in registry['models']:
        if model['model'] not in MODELS:continue
        for asset in model['files']:
            if asset['file'].startswith(('tokenizer','special_tokens','vocab','merges')):
                assert sha(DISK/'models'/model['model']/asset['file'])==asset['sha256']
    tokenizers={model:AutoTokenizer.from_pretrained(str(DISK/'models'/model),local_files_only=True) for model in MODELS}
    rows=[json.loads(x) for x in pool.read_text(encoding='utf-8').splitlines() if x.strip()]
    selected_sets=[]
    for condition,targets,seed,diagnostic in [
        ('real_repobench_mechanism',[('RepoBench',3)],protocol['real_repo_selection_seed'],True),
        ('task_faithful_open_arrival',[('HotpotQA',3),('RepoBench',3)],protocol['open_arrival_selection_seed'],False)]:
        out=root/('results/tsc_real_repobench_mechanism_20261018/inputs_v1' if diagnostic else 'results/tsc_task_faithful_open_arrival_20261018/inputs_v1')
        assert not out.exists(),'No replacement/partial source-selection resume'
        out.mkdir(parents=True);packed=[];originals=[];ledger=[];examined=[];all_shapes=[];start_exclusions=sorted(excluded)
        capacity=Capacity(generation,catalog,tokenizers,diagnostic)
        for target,required in targets:
            count=0
            for row in ordered_candidates(rows,excluded,target,seed):
                identity=source(row);namespace=('repo-mech-' if diagnostic else 'open-faithful-')+hashlib.sha256(identity.encode()).hexdigest()[:16]
                sample={**row, 'revision_session_id':namespace,'phase19b_session_id':namespace,'revision_source_group':identity,'revision_family':target}
                types={x['type'] for x in sample['segments'] if x['text']}
                critical='CODE_PREFIX' if target=='RepoBench' else 'USER_QUERY'
                if critical not in types:
                    examined.append(dict(source_group=identity,family=target,status='missing_nonempty_critical_task_field',critical=critical));continue
                capacity.last_success_shapes=[]
                result=pack_task_input(sample,lambda x:capacity(x,False),validate=lambda x:capacity(x,True))
                meta={k:v for k,v in result.items() if k!='sample'};meta.update(source_group=identity,family=target,namespace=namespace)
                ledger.append(meta);examined.append(dict(source_group=identity,family=target,status=result['status'],
                    selection_hash=hashlib.sha256((str(seed)+':'+identity).encode()).hexdigest(),critical_capacity_eligible=result['sample'] is not None))
                if result['sample'] is None:continue
                chosen=result['sample'];chosen['revision_input_fidelity']={'protocol':'structure-preserving-window-v2','status':result['status']}
                assert len(capacity.last_success_shapes)==600
                all_shapes.extend(capacity.last_success_shapes)
                originals.append(sample);packed.append(chosen);excluded.add(identity);count+=1
                print(json.dumps(dict(condition=condition,prepared_sources=len(packed),source_group=identity,status=result['status'])),flush=True)
                if count==required:break
            assert count==required,'Insufficient blind critical-capacity-eligible sources for '+target
        jsonl(out/'original_selected_sessions_v1.jsonl',originals);jsonl(out/'faithful_selected_sessions_v1.jsonl',packed)
        jsonl(out/'CPU_prompt_shapes_v1.jsonl',all_shapes)
        selected={source(x) for x in packed};assert len(selected)==len(packed) and not selected.intersection(start_exclusions)
        record=dict(condition=condition,selection_seed=seed,selected_source_groups=sorted(selected),sources=len(selected),
            exclusions_before_selection=start_exclusions,excluded_unique_sources_before_selection=len(start_exclusions),
            selected_source_groups_not_previously_observed=True,source_pool_sha256=sha(pool),known_exclusion_inventory_sha256=sha(known_path),
            selection_protocol_sha256=sha(study/'selection_protocol_v1.json'),source_sha256=sha(Path(__file__)),
            data_files=[dict(path=p.relative_to(root).as_posix(),sha256=sha(p)) for p in [out/'original_selected_sessions_v1.jsonl',out/'faithful_selected_sessions_v1.jsonl',out/'CPU_prompt_shapes_v1.jsonl']],
            candidates_examined_in_predeclared_hash_order=examined,packing_ledgers=ledger,
            capacity_checked_three_models_ten_tenants_ten_turns=True,capacity_diagnostic_L3_override_only=diagnostic,
            production_family_eligibility_unchanged=True,reference_labels_answer_positions_or_model_outcomes_used=False,new_GPU_requests=0)
        write(out/'preparation_record_v1.json',record);selected_sets.append(dict(condition=condition,sources=sorted(selected)))
    assert len(selected_sets)==2
    write(study/'input_selection_complete_v1.json',dict(status='complete',sets=selected_sets,total_new_sources=9,
        final_excluded_unique_sources=len(excluded),all_source_sets_disjoint=True,new_GPU_requests=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    with installed_adapter():main(p.parse_args().root.resolve())
