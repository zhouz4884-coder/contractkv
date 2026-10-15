"""Audit and summarize the prospective R1R matrix without changing live data."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics
import sys

if __package__ in (None, ''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read, write, first_divergence
from scripts.tsc_revision_r1r_summary import route_audit
from scripts.tsc_revision_live import load_metrics
from scripts.summarize_submission_supplement import percentile

MODELS=('Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct')


def expected_cells():
    names=[]
    for study,policies in (('single-session',('raw-order','query-full','query-prefix')),('template-fanout',('raw-order','query-prefix'))):
        for model,policy,repeat in itertools.product(('qwen','mistral','llama'),policies,(1,2,3)):
            names.append(f'{study}_{model}_{policy}_r{repeat}')
    return names


def audit_cell(directory,expected_sessions):
    summary=json.loads((directory/'summary.json').read_text()); raw=directory/'raw.jsonl'
    rows=read(raw); future=[r for r in rows if r['row_type']=='future']; business=[r for r in rows if r['row_type'] in ('warm','future')]
    findings=[]
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=summary['raw_file_sha256']: findings.append('raw_hash_mismatch')
    expected=450 if summary['study']=='single-session' else 900
    if len(future)!=expected or summary['expected_futures']!=expected: findings.append('future_count')
    identities=[r['request_id'] for r in business]
    if len(set(identities))!=len(identities): findings.append('duplicate_request_id')
    positions=[(r['session_id'],r['turn_id']) for r in business]
    if len(set(positions))!=len(positions): findings.append('duplicate_session_turn')
    expected_positions={(sid,turn) for sid in expected_sessions for turn in range(10)}
    if set(positions)!=expected_positions: findings.append('frozen_session_turn_set_mismatch')
    for row in business:
        expected_sample=expected_sessions.get(row['session_id'])
        if not expected_sample or (row['source_group'],row['family'],row['certificate_namespace'])!=expected_sample:
            findings.append('frozen_source_family_or_namespace_mismatch'); break
    if any(r['row_type']!=('warm' if r['turn_id']==0 else 'future') for r in business): findings.append('warm_future_classification')
    if len({(r['study'],r['model'],r['repeat'],r['policy']) for r in business})!=1: findings.append('mixed_cell_labels')
    if any(not r['success'] for r in business): findings.append('business_generation_failure')
    if any(not r['token_ids_available'] or not r['output_token_ids'] for r in business): findings.append('missing_actual_token_ids')
    if any(len(r['output_token_ids'])!=r['completion_tokens'] for r in business): findings.append('token_usage_mismatch')
    events=load_metrics(directory/'metrics.jsonl')
    for r in business:
        event=events.get(r['request_id'])
        if not event or not r.get('metric_join_success'): findings.append('missing_actual_metric_join'); break
        if r['new_prefill_tokens']!=int(event['prompt_tokens'])-int(event['prefix_hit_tokens']): findings.append('prefill_metric_mismatch'); break
    route=route_audit(rows)
    if route['scope_invalid_admissions']: findings.append('unknown_scope_compiled')
    if route['rejected_published_tokens']: findings.append('rejected_publication')
    witnesses={(r['certificate_namespace'],r['query_scope']):r for r in business if r.get('scope_first_raw_business')}
    calls=0; verify_ms=0; attempts=[]
    for r in rows:
        if r['row_type']!='verification': continue
        witness=witnesses.get((r['certificate_namespace'],r['query_scope']))
        if not witness: findings.append('missing_raw_business_witness')
        elif r['certificate_issued'] and (witness['finish_reason']!='stop' or not witness.get('witness_available')): findings.append('uncertifiable_witness_admitted')
        if r['certificate_issued'] and r['committed_tokens']>r['stable_prefix_tokens']: findings.append('publication_beyond_stable')
        calls+=len(r['attempts']); verify_ms+=r['complete_verification_ms']
        attempts+=r['attempts']
    if calls!=summary['verification_calls'] or abs(verify_ms-summary['verification_ms_total'])>1e-5: findings.append('verification_cost_mismatch')
    control=json.loads((directory/'pre_measurement_control.summary.json').read_text())
    for key in ('cold_read_decisions_agree','cached_read_observed','no_unapproved_or_generic_read','zero_rejected_publication'):
        if not control[key]: findings.append('pre_measurement_control:'+key)
    return {'cell':directory.name,'findings':sorted(set(findings)),'futures':len(future),'business':len(business),'actual_metric_joins':sum(r.get('metric_join_success',False) for r in business),**route},summary,rows


def mean(rows,key): return statistics.fmean(r[key] for r in rows)


def clustered_ready_ci(pairs,seed=10672126,draws=5000):
    by_source=defaultdict(lambda:defaultdict(list))
    for r in pairs: by_source[r['source_group']][r['repeat']].append(r)
    sources=sorted(by_source); rng=random.Random(seed); values=[]
    # Requests/tenants remain grouped. Repeat indices are paired across policies.
    stats={s:{k:(sum(r['raw_ready_ttft_ms'] for r in rs),sum(r['ready_ttft_ms'] for r in rs)) for k,rs in repeats.items()} for s,repeats in by_source.items()}
    for _ in range(draws):
        raw=compiled=0.0
        repeats=[rng.choice((1,2,3)) for _ in range(3)]
        for source in rng.choices(sources,k=len(sources)):
            for repeat in repeats:
                x,y=stats[source][repeat]; raw+=x; compiled+=y
        values.append(100*(1-compiled/raw))
    return percentile(values,.025),percentile(values,.975)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-partial',action='store_true'); a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    cells={}; audits=[]; performance=[]; all_attempts=[]; missing=[]; model_identities={}
    freeze_path=a.root/'freeze_v1.json'; freeze_sha=hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    expected_by_study={}
    for study,filename,tenants in (('single-session','heldout_sealed_sessions_v1.jsonl',1),('template-fanout','heldout_fanout_sessions_v1.jsonl',10)):
        samples=read(a.root/'source_snapshot/results/tsc_revision_r1r/inputs'/filename)
        expected={}
        for sample in samples:
            for tenant in range(tenants):
                sid=sample['revision_session_id']+(f'-tenant{tenant:02d}' if tenants>1 else '')
                expected[sid]=(sample['revision_source_group'],sample['revision_family'],sample['revision_session_id'])
        expected_by_study[study]=expected
    for name in expected_cells():
        directory=a.root/'cells'/name
        if not (directory/'summary.json').is_file(): missing.append(name); continue
        expected_study,model_alias,expected_policy,repeat_name=name.split('_')
        audit,summary,rows=audit_cell(directory,expected_by_study[expected_study]); audits.append(audit)
        manifest=json.loads((directory/'manifest.json').read_text())
        if manifest['freeze_sha256']!=freeze_sha: audit['findings'].append('cell_freeze_mismatch')
        if manifest['sessions_sha256']!=summary['sessions_sha256']: audit['findings'].append('cell_input_mismatch')
        future=[r for r in rows if r['row_type']=='future']; first=future[0]
        expected_model={'qwen':'Qwen3-8B','mistral':'Mistral-7B-Instruct-v0.3','llama':'Llama-3.1-8B-Instruct'}[model_alias]
        if (first['study'],first['model'],first['policy'],first['repeat'])!=(expected_study,expected_model,expected_policy,int(repeat_name[1:])):
            audit['findings'].append('cell_labels_do_not_match_planned_cell')
        identity=json.dumps({k:manifest[k] for k in ('model_files','shards','packages','environment')},sort_keys=True)
        previous=model_identities.setdefault(first['model'],identity)
        if previous!=identity: audit['findings'].append('model_runtime_or_environment_changed_between_cells')
        key=(first['study'],first['model'],first['repeat'],first['policy']); cells[key]=(summary,rows)
        wall=summary['wall_s_including_all_setup_and_verification']
        performance.append({'cell':name,'study':key[0],'model':key[1],'repeat':key[2],'policy':key[3],
                            'future_requests':len(future),'compiled_futures':sum(r['effective_level']!='L0' for r in future),
                            'mean_ready_ttft_ms':mean(future,'ready_ttft_ms'),'p99_ready_ttft_ms':percentile([r['ready_ttft_ms'] for r in future],.99),
                            'mean_backend_ttft_ms':mean(future,'ttft_ms'),'new_prefill_tokens_mean':mean(future,'new_prefill_tokens'),
                            'wall_s':wall,'full_wall_goodput_rps':len(future)/wall,
                            'ready_1500ms_slo_goodput_rps':sum(r['success'] and r['ready_ttft_ms']<=1500 for r in future)/wall,
                            'verification_ms_total':summary['verification_ms_total'],'verification_calls':summary['verification_calls'],**{k:v for k,v in audit.items() if k not in ('findings','cell')}})
        for row in rows:
            if row['row_type']=='verification':
                for attempt in row['attempts']: all_attempts.append({'cell':name,'study':key[0],'model':key[1],'policy':key[3],'family':row['family'],**attempt})
    pairs=[]; repeats=[]
    for key,(summary,rows) in cells.items():
        study,model,repeat,policy=key
        if policy=='raw-order' or (study,model,repeat,'raw-order') not in cells: continue
        refs={(r['session_id'],r['turn_id']):r for r in cells[(study,model,repeat,'raw-order')][1] if r['row_type']=='future'}
        for r in rows:
            if r['row_type']!='future': continue
            ref=refs[(r['session_id'],r['turn_id'])]
            pairs.append({'study':study,'model':model,'repeat':repeat,'policy':policy,'source_group':r['source_group'],
                          'family':r['family'],'session_id':r['session_id'],'turn_id':r['turn_id'],'effective_level':r['effective_level'],
                          'raw_score':ref['task_score'],'candidate_score':r['task_score'],'quality_drop':ref['task_score']-r['task_score'],
                          'first_diverging_token':first_divergence(ref['output_token_ids'],r['output_token_ids']),
                          'raw_output_tokens':len(ref['output_token_ids']),'candidate_output_tokens':len(r['output_token_ids']),
                          'raw_ready_ttft_ms':ref['ready_ttft_ms'],'ready_ttft_ms':r['ready_ttft_ms'],
                          'raw_finish':ref['finish_reason'],'candidate_finish':r['finish_reason']})
    for study,model in itertools.product(('single-session','template-fanout'),MODELS):
        for r1,r2 in itertools.combinations((1,2,3),2):
            if (study,model,r1,'raw-order') not in cells or (study,model,r2,'raw-order') not in cells: continue
            raw1={(r['session_id'],r['turn_id']):r for r in cells[(study,model,r1,'raw-order')][1] if r['row_type']=='future'}
            for row in cells[(study,model,r2,'raw-order')][1]:
                if row['row_type']!='future': continue
                ref=raw1[(row['session_id'],row['turn_id'])]
                repeats.append({'study':study,'model':model,'repeat1':r1,'repeat2':r2,'source_group':row['source_group'],
                                'score_abs_diff':abs(ref['task_score']-row['task_score']),
                                'token_diverged':ref['output_token_ids']!=row['output_token_ids']})
    groups=defaultdict(list)
    for row in pairs:
        groups[(row['study'],row['model'],row['policy'],'ALL')].append(row)
        groups[(row['study'],row['model'],row['policy'],row['family'])].append(row)
    quality=[]
    for key,rs in sorted(groups.items()):
        quality.append({'study':key[0],'model':key[1],'policy':key[2],'family':key[3],
                        'pairs':len(rs),'distinct_sources':len({r['source_group'] for r in rs}),
                        'compiled_pairs':sum(r['effective_level']!='L0' for r in rs),
                        'token_divergences':sum(r['first_diverging_token']!=-1 for r in rs),
                        'compiled_token_divergences':sum(r['first_diverging_token']!=-1 and r['effective_level']!='L0' for r in rs),
                        'material_drops_gt_0_03':sum(r['quality_drop']>.03 for r in rs),
                        'compiled_material_drops':sum(r['quality_drop']>.03 and r['effective_level']!='L0' for r in rs),
                        'distinct_sources_with_compiled_drop':len({r['source_group'] for r in rs if r['quality_drop']>.03 and r['effective_level']!='L0'}),
                        'raw_mean_score':mean(rs,'raw_score'),'candidate_mean_score':mean(rs,'candidate_score'),
                        'compiled_outputs_gt96':sum(r['effective_level']!='L0' and r['candidate_output_tokens']>96 for r in rs),
                        'compiled_outputs_gt256':sum(r['effective_level']!='L0' and r['candidate_output_tokens']>256 for r in rs),
                        'compiled_outputs_gt512':sum(r['effective_level']!='L0' and r['candidate_output_tokens']>512 for r in rs)})
    comparisons=[]
    for study,model,policy in itertools.product(('single-session','template-fanout'),MODELS,('query-full','query-prefix')):
        rs=[r for r in pairs if (r['study'],r['model'],r['policy'])==(study,model,policy)]
        if not rs or {r['repeat'] for r in rs}!={1,2,3}: continue
        raw=[r for r in performance if (r['study'],r['model'],r['policy'])==(study,model,'raw-order')]
        candidate=[r for r in performance if (r['study'],r['model'],r['policy'])==(study,model,policy)]
        gains=[next(x for x in raw if x['repeat']==r['repeat'])['wall_s']/r['wall_s'] for r in candidate]
        lo,hi=clustered_ready_ci(rs)
        comparisons.append({'study':study,'model':model,'policy':policy,'pairs':len(rs),
                            'raw_ready_ttft_ms':mean(rs,'raw_ready_ttft_ms'),'ready_ttft_ms':mean(rs,'ready_ttft_ms'),
                            'ready_ttft_reduction_pct':100*(1-mean(rs,'ready_ttft_ms')/mean(rs,'raw_ready_ttft_ms')),
                            'ready_reduction_ci95_low':lo,'ready_reduction_ci95_high':hi,
                            'raw_full_wall_goodput_rps':sum(x['future_requests'] for x in raw)/sum(x['wall_s'] for x in raw),
                            'full_wall_goodput_rps':sum(x['future_requests'] for x in candidate)/sum(x['wall_s'] for x in candidate),
                            'full_wall_goodput_multiplier':sum(x['wall_s'] for x in raw)/sum(x['wall_s'] for x in candidate),
                            'goodput_multiplier_repeat_min':min(gains),'goodput_multiplier_repeat_max':max(gains),
                            'verification_ms_total':sum(x['verification_ms_total'] for x in candidate),
                            'actual_prefix_read_tokens':sum(x['actual_cached_prefix_read_tokens'] for x in candidate)})
    repeat_summary=[]
    for study,model in itertools.product(('single-session','template-fanout'),MODELS):
        rs=[r for r in repeats if (r['study'],r['model'])==(study,model)]
        if rs: repeat_summary.append({'study':study,'model':model,'comparisons':len(rs),'token_divergences':sum(r['token_diverged'] for r in rs),'score_abs_diff_gt0_03':sum(r['score_abs_diff']>.03 for r in rs)})
    files={'performance_by_cell_v1.csv':performance,'quality_pairs_v1.csv':pairs,'quality_summary_v1.csv':quality,
           'performance_comparison_v1.csv':comparisons,'raw_repeat_controls_v1.csv':repeat_summary,
           'verification_attempts_v1.csv':all_attempts}
    for name,rows in files.items():
        if rows: write(a.output/name,rows)
    audit={'schema_version':'tsc-r1r.validation-completion.v1','expected_cells':45,'complete_cells':len(cells),
           'expected_futures':28350,'measured_futures':sum(r['futures'] for r in audits),
           'missing_cells':missing,'cells':audits,'all_cell_invariants_pass':not any(r['findings'] for r in audits),
           'experimental_execution_complete':not missing and len(cells)==45 and sum(r['futures'] for r in audits)==28350 and not any(r['findings'] for r in audits),
           'scientific_success_is_separate':True,'freeze_sha256':freeze_sha,
           'model_and_package_identity_consistency_checked':True,
           'ci_estimand':'fixed model; joint paired repeats and source-template clusters; tenants remain within template; 5000 draws',
           'full_wall_uncertainty':'three fresh-run paired min/max, not a source-template confidence interval'}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('cells','missing_cells')}))
    if not a.allow_partial and not audit['experimental_execution_complete']: return 2
    return 0


if __name__=='__main__': raise SystemExit(main())
