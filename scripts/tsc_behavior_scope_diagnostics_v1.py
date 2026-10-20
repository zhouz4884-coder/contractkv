"""Post-hoc explanation of observed costs, residency and all-route differences."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import statistics
STUDY=Path('results/tsc_behavior_scope_repair_20261020')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def first(left,right):
    return next((i for i,(a,b) in enumerate(zip(left,right)) if a!=b),min(len(left),len(right)) if left!=right else None)
def main(root,output):
    study=root/STUDY;primary=read(study/'validation_analysis_v5.json');assert primary['status']=='PASS'
    jobs=read(study/'validation_jobs_v4.json')['jobs'];indexed={};costs=[];registrations=[];residency=[];raw_variants=defaultdict(set)
    for job in jobs:
        cell=study/'runs'/job['id']/'attempt1';rr=lines(cell/'responses.jsonl');summary=read(cell/'summary_v1.json')
        business=[r for r in rr if r['row_type']=='business'];regs=[r for r in rr if r['row_type']=='registration']
        events={r['request_id']:r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        business_s=sum(r['result']['latency_ms'] for r in business)/1000;controller=sum(r['full_controller_ms'] for r in regs)/1000
        remainder=summary['wall_s']-business_s-controller;assert remainder>=0
        preparation=0
        for r in business:
            result=r['result'];key=(job['model'],job['repeat'],job['policy'],r['source_group'],r['tenant'],r['turn'],r['access'])
            indexed[key]=r
            request_begin=result['first_time']-result['ttft_ms']/1000
            preparation+=max(0,request_begin-r['started'])
            if job['policy']=='Raw-authorized':raw_variants[job['model'],r['source_group'],result['prompt_ids_sha256']].add((tuple(result['output_token_ids']),result['finish_reason']))
            if r['compiled']:
                reg=next(x for x in regs if x['source_group']==r['source_group'] and (job['policy']=='Deployment' or (x['tenant'],x['turn'])==(r['tenant'],r['turn'])))
                event=events[result['request_id']];hit=event['prefix_hit_tokens'];commit=reg['certificate']['committed_tokens']
                residency.append(dict(model=job['model'],repeat=job['repeat'],policy=job['policy'],source=r['source_group'],tenant=r['tenant'],access=r['access'],
                    hit='full' if hit>=commit else 'partial' if hit else 'zero',actual_hit_tokens=hit,committed_tokens=commit))
        costs.append(dict(model=job['model'],repeat=job['repeat'],policy=job['policy'],direct_wall_s=summary['wall_s'],
                          cumulative_business_HTTP_s=business_s,complete_registration_controller_s=controller,
                          other_preparation_binding_logging_drain_s=remainder,observed_business_pre_dispatch_preparation_s=preparation))
        for r in regs:
            c=r['certificate'];registrations.append(dict(model=job['model'],repeat=job['repeat'],policy=job['policy'],source=r['source_group'],tenant=r['tenant'],
                PASS=c['certificate_issued'],reason=c.get('failure_reason',''),controller_ms=r['full_controller_ms'],
                private_candidate_or_canary_generated=any(x['row_type']=='reference_generation' and x['source_group']==r['source_group'] and (job['policy']=='Deployment' or x.get('tenant')==r['tenant']) for x in rr),
                actual_verification_RPCs=len(c['attempts']),committed_tokens=c.get('committed_tokens',0)))
    comparisons=[]
    for model in primary['models']:
        bypolicy={p:{k:sum(c[k] for c in costs if c['model']==model and c['policy']==p) for k in ['direct_wall_s','cumulative_business_HTTP_s','complete_registration_controller_s','other_preparation_binding_logging_drain_s','observed_business_pre_dispatch_preparation_s']} for p in ['Raw-authorized','Deployment','Strict-exact']}
        base=bypolicy['Raw-authorized'];strict=bypolicy['Strict-exact']
        saving=base['cumulative_business_HTTP_s']-strict['cumulative_business_HTTP_s']
        extra_controller=strict['complete_registration_controller_s'];extra_other=strict['other_preparation_binding_logging_drain_s']-base['other_preparation_binding_logging_drain_s']
        delta=base['direct_wall_s']-strict['direct_wall_s'];assert abs(delta-(saving-extra_controller-extra_other))<1e-8
        comparisons.append(dict(model=model,policies=bypolicy,business_HTTP_saving_s=saving,additional_controller_s=extra_controller,
            additional_other_s=extra_other,net_direct_wall_saved_s=delta,not_pure_GPU_kernel_attribution=True))
    differences=[]
    for p in primary['pairs']:
        if p['IDs_and_EOS_equal']:continue
        common=(p['model'],p['repeat']);coordinate=(p['source'],p['tenant'],p['turn'],p['access'])
        raw=indexed[common+('Raw-authorized',)+coordinate];policy=indexed[common+(p['policy'],)+coordinate]
        differences.append(dict(**p,Raw_text=raw['result']['output_text'],policy_text=policy['result']['output_text'],
            Raw_output_ids=raw['result']['output_token_ids'],policy_output_ids=policy['result']['output_token_ids'],
            Raw_actual_prompt_ids_sha256=raw['result']['prompt_ids_sha256'],policy_actual_prompt_ids_sha256=policy['result']['prompt_ids_sha256'],
            first_output_difference_zero_based=first(raw['result']['output_token_ids'],policy['result']['output_token_ids']),
            Raw_witness_requested=raw['result']['witness_requested'],policy_witness_requested=policy['result']['witness_requested'],
            policy_output_seen_in_Raw_repeats=(tuple(policy['result']['output_token_ids']),policy['result']['finish_reason']) in raw_variants[p['model'],p['source'],raw['result']['prompt_ids_sha256']]))
    result=dict(status='PASS',cost_comparisons=comparisons,per_cell_costs=costs,registrations=registrations,residency=residency,
                differing_pairs=differences,Raw_exact_prompt_groups_with_variation=sum(len(v)>1 for v in raw_variants.values()),
                boundary='Descriptive actual-clock decomposition, not a GPU kernel causal intervention. Raw-repeat membership does not prove absence of policy influence.',
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','cost_comparisons':comparisons,'Strict_fallback_differences':[d for d in differences if d['policy']=='Strict-exact']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.output)
