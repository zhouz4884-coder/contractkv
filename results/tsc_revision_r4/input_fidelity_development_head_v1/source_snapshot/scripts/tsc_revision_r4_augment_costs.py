"""Add observable prefix state and staged information/GPU costs to dev fit."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_fit_costs_v2 import source_probability_lower
from scripts.tsc_revision_r2_select_policy import percentile
from scripts.tsc_revision_r3_output_contract import python_statement_contract


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]


def probability(rows,field,seed,upper=False):
    if not rows:return 0.
    if upper:
        complement=[{**r,'_complement':not r[field]} for r in rows]
        return 1-source_probability_lower(complement,'_complement',seed)
    return source_probability_lower(rows,field,seed)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve augmented fit version')
    prior=a.root/'results/tsc_revision_r4/development_fit_v2'
    result=json.loads((prior/'calibration_v1.json').read_text(encoding='utf-8'))
    features=json.loads((prior/'observed_scope_features_v1.json').read_text(encoding='utf-8'))
    key=lambda r:(r['study'],r['model'],r['repeat'],r['source_group'],r['query_scope'])
    lookup={key(r):r for r in features};groups=defaultdict(list);all_features=[]
    base=a.root/'results/tsc_revision_r3/validation_v1'
    for directory in sorted((base/'cells').glob('*_margin-benefit_r*')):
        data=read(directory/'raw.jsonl');closed=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
        if sha(directory/'raw.jsonl')!=closed['raw_file_sha256']:raise ValueError('Raw source changed')
        witnesses={};plans={};active={}
        for r in data:
            kind=r['row_type']
            if kind in ('warm','future') and r['scope_first_raw_business']:witnesses[r['certificate_namespace'],r['query_scope']]=r
            elif kind=='prospective_plan':plans[r['certificate_namespace'],r['query_scope']]=r
            elif kind=='verification':
                scope=r['certificate_namespace'],r['query_scope'];w=witnesses[scope];plan=plans[scope]['plan']
                state='warm' if active.get(scope[0])==plan['stable_content_hash'] else 'cold'
                original=lookup[key(w)];eligible=(original['new_reference_eligible'] and w['finish_reason']=='stop' and
                    (w['family']!='RepoBench' or python_statement_contract(w['output_text'])['passed']))
                attempt=r['attempts'][0] if r['attempts'] else None
                extra={**original,'witness_turn':w['turn_id'],'prefix_state_observable_before_attempt':state,
                       'new_reference_eligible':bool(eligible),'new_rule_and_actual_backend_pass':bool(eligible and r['certificate_issued']),
                       'actual_prefix_read_tokens':attempt.get('cached_prefix_read_tokens',0) if attempt else None,
                       'gpu_registration_cost_ms':max(0,r['complete_verification_ms']-plan['cpu_http_preparation_ms']) if attempt else None}
                groups[w['study'],w['model'],w['family'],state].append(extra);all_features.append(extra)
                if r['certificate_issued']:active[scope[0]]=plan['stable_content_hash']
    flat=[]
    for model,studies in result['models'].items():
        for study,families in studies.items():
            for family,calibration in families.items():
                if calibration['level']=='L0':continue
                pooled=[r for state in ('cold','warm') for r in groups[study,model,family,state]]
                gains=[r['gain_per_reuse'] for r in pooled if r['new_rule_and_actual_backend_pass'] and r['gain_per_reuse'] is not None]
                coefs=[r['marginal_gain_per_cached_token'] for r in pooled if r['new_rule_and_actual_backend_pass'] and r['marginal_gain_per_cached_token'] is not None]
                calibration['save_per_reuse_median_ms']=max(0.,statistics.median(gains)) if gains else 0.
                calibration['save_per_cached_token_median_ms']=max(0.,statistics.median(coefs)) if coefs else 0.
                calibration['prefix_states']={}
                for state in ('cold','warm'):
                    rows=groups[study,model,family,state]
                    if not rows:
                        calibration['prefix_states'][state]={'fallback_to_cold':True,'reason':'no_observed_prefix_state'};continue
                    called=[r for r in rows if r['actual_GPU_calls']]
                    eligible=[r for r in rows if r['new_reference_eligible'] and r['actual_GPU_calls']]
                    seed=10672133+int(hashlib.sha256((study+model+family+state).encode()).hexdigest()[:8],16)
                    quantiles={}
                    for q in (.9,.95):
                        gpu=percentile([r['gpu_registration_cost_ms'] for r in called],q) if called else 0.
                        planning=percentile([r['planning_ms'] for r in rows],q)
                        lp=percentile([r['observed_LP_latency_difference_ms'] for r in rows],q)
                        quantiles[str(q)]={'gpu_registration_ms':max(1.,gpu),
                                           'information_ms':planning+lp+1.,
                                           'planning_ms':planning,'raw_logprob_diagnostic_ms':lp,
                                           'total_if_GPU_attempted_ms':max(1.,gpu)+planning+lp+1.}
                    entry={'observed_scope_units':len(rows),'observed_source_units':len({r['source_group'] for r in rows}),
                           'p_joint_lower':probability(rows,'new_rule_and_actual_backend_pass',seed),
                           'p_eligible_upper':probability(rows,'new_reference_eligible',seed+1,True),
                           'p_pass_given_eligible_lower':probability(eligible,'actual_issued',seed+2),
                           'cost_quantiles':quantiles,
                           'observable_prefix_miss_attempts':sum(r['actual_GPU_calls'] and state=='warm' and not r['actual_prefix_read_tokens'] for r in rows),
                           'cost_is_from_observed_state_not_counterfactual_new_policy':True}
                    calibration['prefix_states'][state]=entry
                    flat.append({'study':study,'model':model,'family':family,'prefix_state':state,
                                 **{k:v for k,v in entry.items() if k!='cost_quantiles'},
                                 'gpu_cost_q90_ms':quantiles['0.9']['gpu_registration_ms'],
                                 'gpu_cost_q95_ms':quantiles['0.95']['gpu_registration_ms'],
                                 'information_q95_ms':quantiles['0.95']['information_ms'],
                                 'median_save_per_reuse_ms':calibration['save_per_reuse_median_ms']})
    result['schema_version']='tsc-r4.staged-prefix-state-calibration.v1'
    result['parent_calibration_sha256']=sha(prior/'calibration_v1.json')
    result['augmentation_source_sha256']=sha(Path(__file__))
    result['calibration_boundary']='All R3 is observed development. Prefix state uses an earlier issued same stable hash, which is observable before dispatch; actual hit/miss is an audited outcome, never used as an online oracle. Costs include observed misses. New policy may change the state distribution; live validation is required.'
    a.output.mkdir(parents=True)
    (a.output/'calibration_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (a.output/'scope_features_v1.json').write_text(json.dumps(all_features,indent=2)+'\n',encoding='utf-8')
    with (a.output/'prefix_state_summary_v1.csv').open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    print(json.dumps({'prefix_state_groups':len(flat),'source_scopes':len(all_features),
                      'observable_warm_misses':sum(r['observable_prefix_miss_attempts'] for r in flat),'new_R4_outcomes_used':False}))


if __name__=='__main__':main()
