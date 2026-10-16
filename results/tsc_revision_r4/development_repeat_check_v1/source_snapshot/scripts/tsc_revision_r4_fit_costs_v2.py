"""Calibrate phase-three predictors from observed R3; never read new test outputs."""
import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from types import SimpleNamespace
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_r2_select_policy import percentile


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def source_probability_lower(rows,field,seed):
    bysource=defaultdict(list)
    for row in rows:bysource[row['source_group']].append(float(row[field]))
    if not bysource:return 0.
    means=[statistics.fmean(v) for _,v in sorted(bysource.items())]
    rng=random.Random(seed);n=len(means)
    # Source-level Beta(1,1) shrinkage prevents all-observed-pass => certainty.
    values=[(sum(rng.choices(means,k=n))+1)/(n+2) for _ in range(2000)]
    return percentile(values,.10)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve each predictor fit')
    old=a.root/'results/tsc_revision_r3';base=old/'validation_v1'
    proof=json.loads((base/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not proof['execution_complete']:raise ValueError('Complete prior audit required')
    protocol=json.loads((a.root/'configs/tsc_revision_r1r_validation_protocol_v1.json').read_text(encoding='utf-8'))
    planpath=a.root/'configs/tsc_revision_r4_development_plan_v2.json';plan=json.loads(planpath.read_text(encoding='utf-8'))
    previous=json.loads((a.root/'configs/tsc_revision_r3_catalog_v1.json').read_text(encoding='utf-8'))
    samples={r['revision_source_group']:r for r in read(old/'inputs/heldout_sealed_sessions_v1.jsonl')}
    groups=defaultdict(list);rawfamily=defaultdict(list);rawglobal=defaultdict(list);sources=[];cases={}
    for directory in sorted((base/'cells').glob('*_margin-benefit_r*')):
        rawdir=directory.with_name(directory.name.replace('_margin-benefit_','_raw-order_'))
        data=read(directory/'raw.jsonl');raw=read(rawdir/'raw.jsonl')
        for d in (directory,rawdir):
            record=json.loads((d/'summary.json').read_text(encoding='utf-8'))
            if not record['execution_complete'] or sha(d/'raw.jsonl')!=record['raw_file_sha256']:raise ValueError('Prior raw changed')
            sources.append({'cell':d.name,'raw_sha256':sha(d/'raw.jsonl')})
        baseline={(r['session_id'],r['turn_id']):r for r in raw if r['row_type'] in ('warm','future')}
        for r in raw:
            if r['row_type']=='future':
                rawfamily[r['study'],r['model'],r['family']].append(r['ttft_ms'])
                rawglobal[r['study'],r['model']].append(r['ready_ttft_ms'])
        witnesses={};plans={};business=defaultdict(list)
        for r in data:
            if r['row_type'] in ('warm','future'):
                key=r['certificate_namespace'],r['query_scope'];business[key].append(r)
                if r['scope_first_raw_business']:witnesses[key]=r
            elif r['row_type']=='prospective_plan':plans[r['certificate_namespace'],r['query_scope']]=r
        for decision in data:
            if decision['row_type']!='verification':continue
            key=decision['certificate_namespace'],decision['query_scope'];w=witnesses.get(key)
            if w is None:raise ValueError('R3 complete witness required for calibration')
            signature=w['session_id'],w['turn_id'],w['model']
            if signature not in cases:
                sample=deepcopy(samples[w['source_group']]);sample['revision_session_id']=w['session_id']
                if w['study']=='template-fanout':sample['shared_template_id']=w['certificate_namespace']
                args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity=w['model'],policy_hash=sha(base/'freeze.json'))
                prepared=prepare(args,sample,w['turn_id'])
                if prepared[4]!=w['query_scope']:raise ValueError('Prior scope reconstruction changed')
                cases[signature]=prepared[0]
            check=reference_scope_contract(cases[signature],w['output_text'],plan['max_literal_answer_words'],raw_margins=w.get('reference_margins'),ambiguity_boundary=plan['nonliteral_ambiguity_boundary'])
            eligible=(check['shareable_query_scope'] and w.get('witness_available') and
                      bool(w.get('reference_margins')) and min(w['reference_margins'])>=plan['raw_margin_floor'])
            gain=[];coefficient=[];delta=[];native=[]
            if eligible and decision['certificate_issued']:
                for row in business[key]:
                    if row['effective_level']=='L0':continue
                    ref=baseline[row['session_id'],row['turn_id']]
                    tokens=ref['new_prefill_tokens']-row['new_prefill_tokens'];saved=ref['ttft_ms']-row['ttft_ms']
                    gain.append(saved);native.append(ref['prefix_hit_tokens'])
                    if tokens>0:coefficient.append(saved/tokens);delta.append(tokens)
            row={'study':w['study'],'model':w['model'],'family':w['family'],'source_group':w['source_group'],
                 'repeat':w['repeat'],'query_scope':key[1],'new_reference_eligible':bool(eligible),
                 'new_rule_and_actual_backend_pass':bool(eligible and decision['certificate_issued']),
                 'actual_GPU_calls':len(decision['attempts']),'actual_issued':decision['certificate_issued'],
                 'complete_qualification_ms':decision['complete_verification_ms'],
                 'observed_LP_latency_difference_ms':max(0,w['latency_ms']-baseline[w['session_id'],w['turn_id']]['latency_ms']),
                 'planning_ms':plans[key]['plan']['cpu_http_preparation_ms'],
                 'gain_per_reuse':statistics.fmean(gain) if gain else None,
                 'marginal_gain_per_cached_token':statistics.fmean(coefficient) if coefficient else None,
                 'actual_prefill_token_reduction':statistics.fmean(delta) if delta else None,
                 'raw_native_prefix_tokens':max(native) if native else None,
                 'scope_check':check}
            groups[w['study'],w['model'],w['family']].append(row)
    models={};flat=[]
    for model,prior in previous['models'].items():
        models[model]={}
        for study in ('single-session','template-fanout'):
            models[model][study]={}
            for family,oldcal in prior.items():
                if oldcal['level']=='L0':models[model][study][family]={'level':'L0','reason':'inherited_family_L0'};continue
                rows=groups[study,model,family];called=[r for r in rows if r['actual_GPU_calls']]
                eligible=[r for r in rows if r['new_reference_eligible']]
                passed=[r for r in rows if r['new_rule_and_actual_backend_pass'] and r['gain_per_reuse'] is not None]
                seed=10672132+int(hashlib.sha256((study+model+family).encode()).hexdigest()[:8],16)
                quantiles={}
                for q in plan['cost_quantile_grid']:
                    c=percentile([r['complete_qualification_ms'] for r in called],q) if called else 0
                    lp=percentile([r['observed_LP_latency_difference_ms'] for r in rows],q)
                    quantiles[str(q)]={'complete_qualification_ms':c,'raw_logprob_diagnostic_ms':lp,
                                       'total_cost_ms':max(1.,c+lp+1.)}
                coeff=[r['marginal_gain_per_cached_token'] for r in passed if r['marginal_gain_per_cached_token'] is not None]
                delta=[r['actual_prefill_token_reduction'] for r in passed if r['actual_prefill_token_reduction'] is not None]
                native=[r['raw_native_prefix_tokens'] for r in passed if r['raw_native_prefix_tokens'] is not None]
                record={'level':oldcal['level'],'observed_source_units':len({r['source_group'] for r in rows}),'observed_scope_units':len(rows),
                        'observed_shareable_references':len(eligible),'observed_new_rule_passes':len(passed),
                        'p_joint_lower':source_probability_lower(rows,'new_rule_and_actual_backend_pass',seed),
                        'p_pass_given_eligible_lower':source_probability_lower(eligible,'actual_issued',seed+1),
                        'cost_quantiles':quantiles,'save_per_reuse_q25_ms':max(0.,percentile([r['gain_per_reuse'] for r in passed],.25)) if passed else 0.,
                        'save_per_cached_token_q25_ms':max(0.,percentile(coeff,.25)) if coeff else 0.,
                        'calibrated_prefill_reduction_p95_tokens':percentile(delta,.95) if delta else 0.,
                        'raw_native_prefix_p95_tokens':percentile(native,.95) if native else 0.,
                        'raw_family_ttft_p95_ms':percentile(rawfamily[study,model,family],.95),
                        'raw_global_ready_p99_ms':percentile(rawglobal[study,model],.99)}
                models[model][study][family]=record
                flat.append({'study':study,'model':model,'family':family,**{k:v for k,v in record.items() if k!='cost_quantiles'},
                             'cost_q90_ms':quantiles['0.9']['total_cost_ms'],'cost_q95_ms':quantiles['0.95']['total_cost_ms']})
    result={'schema_version':'tsc-r4.observed-cost-calibration.v1','models':models,'raw_token_margin_floor':plan['raw_margin_floor'],
            'candidate_token_margin_floor':plan['candidate_and_eos_floor'],'max_literal_answer_words':plan['max_literal_answer_words'],
            'source_cells':sources,'plan_sha256':sha(planpath),'analysis_source_sha256':sha(Path(__file__)),'scope_policy_sha256':sha(Path(__file__).with_name('tsc_revision_r4_policy_v2.py')),
            'source_probability_method':'Whole source clusters, all queries/repeats kept together; Beta(1,1) shrinkage, 2000 bootstrap draws, lower10th percentile. Development estimator, not a formal risk bound.',
            'new_R4_outcomes_used':False,'scope':'Development predictor only. Actual prospective efficacy and complete wall must be measured separately.'}
    a.output.mkdir(parents=True)
    (a.output/'calibration_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with (a.output/'calibration_summary_v1.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    (a.output/'observed_scope_features_v1.json').write_text(json.dumps([r for group in groups.values() for r in group],indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':len(flat),'new_shareable_scope_units':sum(r['observed_shareable_references'] for r in flat),
                      'new_rule_observed_passes':sum(r['observed_new_rule_passes'] for r in flat),'new_R4_outcomes_used':False}))


if __name__=='__main__':main()
