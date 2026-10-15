"""Select only from the predeclared development grid; never inspect heldout outcomes."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_benefit_policy import prospective_benefit
from scripts.tsc_revision_live import FROZEN_LEVELS

def percentile(values,q):
    ordered=sorted(values);x=(len(ordered)-1)*q;lo=int(x);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]*(hi-x)+ordered[hi]*(x-lo) if hi!=lo else ordered[lo]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def select(plan,data):
    from math import ceil
    models={'qwen':'Qwen3-8B','mistral':'Mistral-7B-Instruct-v0.3','llama':'Llama-3.1-8B-Instruct'}
    catalog={};groups={}
    for key,identity in models.items():
        catalog[identity]={}
        for family,maxlevel in FROZEN_LEVELS[identity].items():
            cell=[x for x in data['latency_predictor_observations'] if x['model_key']==key and x['family']==family]
            if maxlevel=='L0':catalog[identity][family]={'level':'L0','reason':'inherited_family_L0'};continue
            coef=statistics.median(x['ttft_per_new_prefill_token_ms'] for x in cell if x['ttft_per_new_prefill_token_ms'] is not None)
            native=ceil(percentile([x['native_prefix_hit_tokens'] for x in cell],.95)/16)
            for i in range(1,int(maxlevel[1:])+1):
                slots=[x for x in data['slots'] if x['model_key']==key and x['family']==family and x['level']==f'L{i}']
                groups[(identity,family,f'L{i}')]=(slots,{'level':f'L{i}','verification_rpc_p95_ms':percentile([x['verification_rpc_ms'] for x in slots],.95),'complete_qualification_p95_ms':percentile([x['complete_qualification_ms'] for x in slots],.95),'prefill_ms_per_token':coef,'raw_native_prefix_full_blocks_p95':native})
    grids=[];catalogs=[]
    for raw,cand,factor in itertools.product(plan['raw_answer_minimum_margin_grid'],plan['candidate_answer_and_eos_minimum_margin_grid'],plan['benefit_safety_factor_grid']):
        deployed={m:dict(v) for m,v in catalog.items()};objective=0;bad=compiled=attempted=0;cost=0
        for identity in models.values():
            for family,maxlevel in FROZEN_LEVELS[identity].items():
                if maxlevel=='L0':continue
                choices=[]
                for i in range(1,int(maxlevel[1:])+1):
                    slots,calibration=groups[(identity,family,f'L{i}')];value=0;drops=admitted=tries=0
                    for slot in slots:
                        for tenants,weight in zip(plan['selection_declared_tenant_scenarios'],plan['selection_scenario_weights']):
                            remain=plan['expected_query_repetitions_per_registered_tenant_hint']*tenants-min(2,tenants)
                            gate=prospective_benefit(max(0,slot['stable_full_blocks']-calibration['raw_native_prefix_full_blocks_p95']),16,remain,calibration['prefill_ms_per_token'],calibration['verification_rpc_p95_ms'],slot['planning_ms'],factor,calibration['complete_qualification_p95_ms'])
                            net=-slot['planning_ms']
                            if gate['allow_verification'] and slot['raw_full_min_including_eos']>=raw:
                                tries+=1
                                passed=slot['rank_path_certificate_issued'] and slot['candidate_answer_min']>=cand and slot['candidate_eos_margin']>=cand
                                net=-gate['estimated_cost_ms']
                                if passed:
                                    admitted+=1;drops+=slot['observed_material_drops'];net+=gate['estimated_saved_ms']
                            value+=weight*net/len(slots)
                    choices.append((drops,value,-calibration['complete_qualification_p95_ms'],i,admitted,tries,calibration))
                safe=[c for c in choices if c[0]==0]
                if not safe:bad+=1;continue
                chosen=max(safe,key=lambda x:(x[1],x[2],-x[3]));objective+=chosen[1]/15
                compiled+=chosen[4];attempted+=chosen[5];cost+=-chosen[2]
                deployed[identity][family]={**chosen[6],'development_predicted_net_ms':chosen[1],'development_accepted_scope_scenarios':chosen[4],'development_attempted_scope_scenarios':chosen[5]}
        eligible=raw>0 and cand>0 and bad==0 and compiled>0
        record={'raw_floor':raw,'candidate_floor':cand,'safety_factor':factor,'eligible_final':eligible,'unsafe_cells_without_safe_level':bad,'predicted_net_ms_equal_model_family':objective,'accepted_scope_scenarios':compiled,'attempted_scope_scenarios':attempted,'cost_tiebreak':cost}
        grids.append(record);catalogs.append(deployed)
    valid=[i for i,g in enumerate(grids) if g['eligible_final']]
    if not valid:raise ValueError('No nontrivial safe development policy in frozen grid')
    best=max(valid,key=lambda i:(grids[i]['predicted_net_ms_equal_model_family'],-grids[i]['cost_tiebreak'],grids[i]['raw_floor'],grids[i]['candidate_floor'],grids[i]['safety_factor']))
    chosen=grids[best]
    result={'schema_version':'tsc-r2.frozen-single-shot-catalog.v1','raw_token_margin_floor':chosen['raw_floor'],'candidate_token_margin_floor':chosen['candidate_floor'],'benefit_safety_factor':chosen['safety_factor'],'expected_query_repetitions_per_registered_tenant_hint':plan['expected_query_repetitions_per_registered_tenant_hint'],'online_verification_attempt_limit':1,'models':catalogs[best],'development_selection':chosen,'selection_objective_detail':'Equal model/family weights; each level has three queries per source. Average declared tenant scenarios. Failed eligible verification costs the conservative p95 estimate, rejected early costs actual planning. This predictor excludes unmeasured raw-logprob overhead and is not a measured serving speedup.','new_heldout_sessions_sha256':plan['new_heldout_sessions_sha256'],'development_only':True}
    return result,grids

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--profile-analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    audit=json.loads((a.profile_analysis/'completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']:raise ValueError('Profile audit required')
    path=a.profile_analysis/'selection_input_v1.json';result,grid=select(json.loads(a.plan.read_text(encoding='utf-8')),json.loads(path.read_text(encoding='utf-8')))
    result.update(selection_plan_sha256=sha(a.plan),profile_selection_input_sha256=sha(path))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists():raise ValueError('Preserve selected policy; create a new explicit version')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with a.output.with_suffix('.grid.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(grid[0]));writer.writeheader();writer.writerows(grid)
    print(json.dumps(result))
