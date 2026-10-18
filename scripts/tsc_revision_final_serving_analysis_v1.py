"""Independent request-level accounting of the bounded faithful serving study.

All results are descriptive unless an explicitly paired comparison is emitted.
Native initial new-prefill is logical work, not GPU time or total recomputation.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import re
import statistics

STUDY='results/tsc_task_faithful_open_arrival_20261018'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def lines(path):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():yield json.loads(line)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
def write_json(path,value):
    with path.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2,ensure_ascii=False,allow_nan=False);handle.write('\n')
def write_csv(path,rows):
    if not rows:return
    names=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=names);writer.writeheader();writer.writerows(rows)
def quantile(values,q):
    values=sorted(values)
    if not values:return None
    at=(len(values)-1)*q;low=math.floor(at);high=math.ceil(at)
    return values[low]+(values[high]-values[low])*(at-low)
def distribution(values):
    values=list(values)
    assert all(isinstance(x,(int,float)) and math.isfinite(x) for x in values)
    return dict(n=len(values),mean=statistics.fmean(values) if values else None,
        median=quantile(values,.5),P95=quantile(values,.95),P99=quantile(values,.99),max=max(values,default=None))
def ratio(a,b):return a/b if b else None
def changed(a,b):return (a['output_token_ids'],a['finish_reason'])!=(b['output_token_ids'],b['finish_reason'])
def first_divergence(one,two):
    for index,(a,b) in enumerate(zip(one,two)):
        if a!=b:return index
    return min(len(one),len(two)) if len(one)!=len(two) else -1
def key(row):return row['source_group'],row['session_id'],row['turn_id']


def registration_queue_bounds(duration_ms,previous_end,planned_ready,processing_begin):
    """Bound overlap of a registration contained in the observed inter-wave gap.

    Exact registration start/end stamps are unavailable. Do not invent them or
    assign the entire registration to a request that arrived after it finished.
    """
    gap=(processing_begin-previous_end)*1000
    queue=max(0.,(processing_begin-planned_ready)*1000)
    assert gap>=-1e-5 and duration_ms<=gap+2.
    lower=max(0.,duration_ms-max(0.,(planned_ready-previous_end)*1000))
    upper=min(duration_ms,queue)
    assert lower<=upper+2.
    return gap,lower,upper


def category(reason):
    if reason=='observation_scope_has_no_declared_exact_reuse':return 'exact_observation_scope_without_declared_reuse'
    if reason=='inherited_family_L0':return 'inherited_family_L0'
    if reason.startswith('raw_output_contract:'):return 'raw_output_contract'
    if 'margin' in reason:return 'raw_margin' if 'raw' in reason else 'candidate_or_EOS_margin'
    if any(x in reason for x in ('benefit','cost','tail','net','reuse')):return 'economic_gate'
    if 'incomplete' in reason or 'finish' in reason or 'EOS' in reason:return 'incomplete_reference_or_EOS'
    return 'other:'+reason


def telemetry(cell):
    path=cell/'telemetry_v1.jsonl';observations=list(lines(path))
    available=[x for x in observations if x['available']]
    names=sorted({name for x in available for name in x['values']})
    output=dict(samples=len(observations),available_samples=len(available),missing_samples=len(observations)-len(available),
        sampling_period_target_s=.5,sampled_maxima_are_not_continuous_peaks=True)
    for name in names:
        values=[x['values'][name] for x in available if x['values'].get(name) is not None]
        output[name]=dict(available_samples=len(values),min=min(values,default=None),max=max(values,default=None),
            first=values[0] if values else None,last=values[-1] if values else None)
    return output


def audit_cell(study,job,slo,phase,scorer,samples):
    cell=study/('calibration/cells' if phase=='calibration' else 'formal/cells')/job['id']
    complete=read(cell/'completion_v1.json');summary=read(cell/'summary.json');audit=read(cell/'client_audit_v2.json')
    assert complete['status']=='complete' and complete['job']==job
    assert summary['execution_complete'] and summary['raw_file_sha256']==sha(cell/'raw.jsonl')
    expected=120 if phase=='calibration' else 360
    assert summary['arrival_requests']==expected and summary['futures']==expected*9//10
    assert audit['result']=='completed' and audit['actual_business_prompt_ID_hashes_checked']==expected
    rows=list(lines(cell/'raw.jsonl'));business=[r for r in rows if r['row_type'] in ('warm','future')]
    assert len(business)==expected and len({key(r) for r in business})==expected
    for r in business:
        assert r['success'] and r['prompt_ids_sha256']==digest(r['prompt_token_ids']) and not r['scope_invalid_admission']
        assert len(r['prompt_token_ids'])==r['prompt_tokens'] and len(r['output_token_ids'])==r['completion_tokens']
        assert r['finish_reason'] in ('stop','length')
        assert abs(r['ready_ttft_ms']-r['queue_before_controller_ms']-r['controller_to_submit_ms']-r['ttft_ms'])<1e-5
        sample=samples[r['source_group']]
        score,metric,source=scorer(sample['dataset'],sample['task'],r['output_text'],sample.get('answer',''))
        assert abs(score-r['task_score'])<1e-12 and metric==r['task_metric'] and source==r['metric_source']
    request_rows={r['request_id']:r for r in rows if r['row_type']=='verification_request'}
    response_rows={r['request_id']:r for r in rows if r['row_type']=='verification_response'}
    assert request_rows.keys()==response_rows.keys()
    requested=set(request_rows);observed={}
    for m in lines(cell/'metrics.jsonl'):
        if m.get('event')=='prefix_cache_request_observation' and m.get('initial_prefill_observation'):
            assert m['request_id'] not in observed,'Repeated initial metric for one ID'
            observed[m['request_id']]=m
    assert set(r['request_id'] for r in business).issubset(observed)
    assert requested.issubset(observed)
    server_rpc=len(re.findall(r'"POST /v1/contractkv/verify HTTP/1\.[01]" 200', (cell/'server.log').read_text(encoding='utf-8',errors='replace')))
    assert server_rpc==len(requested),'Server HTTP log and request ledger disagree'
    decisions={};plans={};witnesses={};active={};registrations=[];wave_business=defaultdict(list)
    for r in rows:
        typ=r['row_type']
        if typ=='prospective_plan':
            k=(r['certificate_namespace'],r['query_scope']);assert k not in plans;plans[k]=r
        elif typ=='verification':
            k=(r['certificate_namespace'],r['query_scope']);assert k not in decisions;decisions[k]=r
        elif typ in ('warm','future'):wave_business[r['wave_index']].append(r)
    # Registration-to-wave association uses the actual session, not only turn.
    decision_wave={}
    for r in business:
        k=(r['certificate_namespace'],r['query_scope'])
        if r['scope_first_decision_business'] and k in decisions:decision_wave.setdefault(r['wave_index'],decisions[k])
    requests=[]
    for r in rows:
        typ=r['row_type']
        if typ=='verification':
            k=(r['certificate_namespace'],r['query_scope']);active[k]=r
            attempts=r['attempts'];assert len(attempts)<=1
            for attempt in attempts:
                assert not attempt.get('result_unavailable')
                if not attempt.get('certificate_issued'):assert int(attempt.get('committed_tokens',0))==0
            if not r['certificate_issued']:assert int(r.get('committed_tokens',0))==0
            registrations.append(dict(cell=job['id'],model=job['model'],phase=phase,execution_regime=job.get('phase',phase),load=job.get('load'),
                policy=summary['policy'],economic_gate=job.get('economic_gate','ON'),repeat=job.get('repeat',1),
                source_namespace=k[0],query_scope=k[1],family=r['family'],issued=r['certificate_issued'],
                failure_reason=r['failure_reason'],category='issued' if r['certificate_issued'] else category(r['failure_reason']),
                actual_RPCs=len(attempts),RPC_ms=sum(a['verification_ms'] for a in attempts),
                failed_RPC_ms=sum(a['verification_ms'] for a in attempts if not a.get('certificate_issued')),
                complete_controller_ms=r['complete_verification_ms'],post_business_registration_ms=r['post_business_registration_ms'],
                pre_business_planning_ms=r.get('pre_business_planning_ms'),
                committed_tokens=int(r.get('committed_tokens',0)),selected_level=r['selected_level'],
                pre_economic_reason=plans[k]['reason'],pre_economic_allowed=plans[k]['allow_verification'],
                post_economic_reason=(r.get('post_reference_benefit') or {}).get('reason')))
        elif typ in ('warm','future'):
            k=(r['certificate_namespace'],r['query_scope']);certificate=active.get(k);compiled=r['effective_level']!='L0'
            assert compiled==bool(certificate and certificate['certificate_issued'])
            if r['scope_first_raw_business']:witnesses.setdefault(k,r)
            final=decisions.get(k);plan=plans.get(k)
            if compiled:
                assert certificate and k in witnesses
                assert digest(r['prompt_token_ids'][:certificate['stable_prefix_tokens']])==certificate['stable_prefix_hash']
                route='compiled';committed=int(certificate['committed_tokens']);assert committed>0 and committed%16==0
                witness_change=changed(witnesses[k],r)
            else:
                route=('native_raw' if summary['policy']=='raw-order' else 'before_successful_scope_decision' if final and final['certificate_issued']
                    else category(final['failure_reason']) if final else category(plan['reason']) if plan else 'unexplained_L0')
                assert route!='unexplained_L0';committed=0;witness_change=None
            m=observed[r['request_id']]
            assert m['prompt_tokens']==r['prompt_tokens'] and m['prefix_hit_tokens']==r['prefix_hit_tokens']
            assert m['free_gpu_blocks']+m['used_gpu_blocks']==m['total_gpu_blocks']>0
            previous=decision_wave.get(r['wave_index']-1);previous_group=wave_business.get(r['wave_index']-1,[])
            previous_end=max((x['end_time'] for x in previous_group),default=None)
            d=float(previous['post_business_registration_ms']) if previous else 0.
            lower=upper=gap=0.
            if previous_end is not None:
                gap,lower,upper=registration_queue_bounds(d,previous_end,r['planned_ready_time'],r['wave_processing_begin_time'])
            compliant=r['ready_ttft_ms']<=slo['TTFT_ms'] and r['tpot_ms']<=slo['TPOT_ms']
            requests.append(dict(cell=job['id'],phase=phase,execution_regime=job.get('phase',phase),model=job['model'],load=job.get('load'),policy=summary['policy'],
                economic_gate=job.get('economic_gate','ON'),repeat=job.get('repeat',1),GPU_lane=job['lane'],
                request_id=r['request_id'],row_type=r['row_type'],source_group=r['source_group'],family=r['family'],
                session_id=r['session_id'],turn=r['turn_id'],wave_index=r['wave_index'],query_scope=r['query_scope'],
                effective_level=r['effective_level'],route=route,compiled=compiled,committed_tokens=committed,
                compiled_vs_actual_witness_ID_or_finish_change=witness_change,
                task_score=r['task_score'],task_score_positive=r['task_score']>0,
                output_tokens=r['completion_tokens'],finish_reason=r['finish_reason'],output_budget=r['output_budget'],
                at_length_limit=r['finish_reason']=='length',prompt_tokens=r['prompt_tokens'],
                readiness_TTFT_ms=r['ready_ttft_ms'],backend_TTFT_ms=r['ttft_ms'],
                queue_before_controller_ms=r['queue_before_controller_ms'],controller_to_submit_ms=r['controller_to_submit_ms'],
                readiness_E2E_ms=r['ready_latency_ms'],TPOT_ms=r['tpot_ms'],
                previous_wave_post_registration_ms=d,previous_registration_issued=previous['certificate_issued'] if previous else None,
                previous_registration_RPCs=len(previous['attempts']) if previous else 0,
                prior_interwave_gap_ms=gap,prior_registration_overlap_with_queue_lower_ms=lower,
                prior_registration_overlap_with_queue_upper_ms=upper,
                primary_SLO_compliant=compliant,TTFT_only_compliant=r['ready_ttft_ms']<=slo['TTFT_ms'],
                prefix_hit_tokens=m['prefix_hit_tokens'],initial_logical_new_prefill_tokens=m['prompt_tokens']-m['prefix_hit_tokens'],
                initial_native_new_prefill_this_iteration_tokens=m.get('new_prefill_tokens_this_iteration'),
                compiled_prefix_hit_class=('full' if m['prefix_hit_tokens']>=committed else 'partial' if m['prefix_hit_tokens'] else 'zero') if compiled else 'not_compiled',
                initial_native_scheduler_wait_ms=m['scheduler_wait_ms'],initial_scheduler_running=m['scheduler_running_requests'],
                initial_scheduler_waiting=m['scheduler_waiting_requests'],initial_used_GPU_blocks=m['used_gpu_blocks'],
                total_GPU_blocks=m['total_gpu_blocks'],native_block_size=m['block_size'],
                native_eviction_counter=m.get('prefix_cache_evictions'),native_GPU_timing_available=m.get('gpu_timing_availability')))
    assert len(requests)==expected
    assert sum(x['actual_RPCs'] for x in registrations)==server_rpc
    wall=summary['wall_s_including_all_setup_and_verification'];assert wall>0
    rates=dict(achieved_requests_per_s=expected/wall,primary_goodput_requests_per_s=sum(x['primary_SLO_compliant'] for x in requests)/wall,
        TTFT_only_goodput_requests_per_s=sum(x['TTFT_only_compliant'] for x in requests)/wall)
    verification_work=sum(observed[rid]['prompt_tokens']-observed[rid]['prefix_hit_tokens'] for rid in requested)
    facts=dict(cell=job['id'],phase=phase,execution_regime=job.get('phase',phase),peer_regime=job.get('peer_regime','Raw calibration'),
        model=job['model'],load=job.get('load'),policy=summary['policy'],
        economic_gate=job.get('economic_gate','ON'),repeat=job.get('repeat',1),GPU_lane=job['lane'],business_requests=expected,
        future_requests=sum(x['row_type']=='future' for x in requests),wall_s=wall,**rates,
        offered_rate_requests_per_s=job.get('offered_rate_requests_per_s'),
        compliant_requests=sum(x['primary_SLO_compliant'] for x in requests),TTFT_only_compliant_requests=sum(x['TTFT_only_compliant'] for x in requests),
        compiled_business=sum(x['compiled'] for x in requests),compiled_futures=sum(x['compiled'] and x['row_type']=='future' for x in requests),
        compiled_vs_witness_changes=sum(x['compiled_vs_actual_witness_ID_or_finish_change'] is True for x in requests),
        length_events=sum(x['at_length_limit'] for x in requests),qualifications=len(registrations),actual_verification_RPCs=server_rpc,
        failed_verification_RPCs=sum(x['actual_RPCs'] for x in registrations if not x['issued']),
        complete_controller_work_ms=sum(x['complete_controller_ms'] for x in registrations),
        verification_RPC_work_ms=sum(x['RPC_ms'] for x in registrations),failed_RPC_work_ms=sum(x['failed_RPC_ms'] for x in registrations),
        business_initial_logical_new_prefill_tokens=sum(x['initial_logical_new_prefill_tokens'] for x in requests),
        business_native_new_prefill_first_iteration_tokens=sum(x['initial_native_new_prefill_this_iteration_tokens'] for x in requests)
            if all(x['initial_native_new_prefill_this_iteration_tokens'] is not None for x in requests) else None,
        verification_initial_logical_new_prefill_tokens=verification_work,
        all_initial_logical_new_prefill_tokens=sum(x['initial_logical_new_prefill_tokens'] for x in requests)+verification_work,
        actual_prefix_hit_tokens=sum(x['prefix_hit_tokens'] for x in requests),
        routes=dict(Counter(x['route'] for x in requests)),compiled_hit_classes=dict(Counter(x['compiled_prefix_hit_class'] for x in requests if x['compiled'])),
        latencies={name:distribution(x[name] for x in requests) for name in ('readiness_TTFT_ms','backend_TTFT_ms','queue_before_controller_ms',
            'controller_to_submit_ms','readiness_E2E_ms','TPOT_ms','initial_native_scheduler_wait_ms')},
        telemetry=telemetry(cell),actual_GPU_pool_blocks=sorted({x['total_GPU_blocks'] for x in requests}),
        final_drain_ms=read(cell/'measured_backend_drain_v1.json')['elapsed_ms'])
    return dict(facts=facts,business={key(r):r for r in business},requests=requests,registrations=registrations,
        source_files=[dict(path=p.relative_to(study).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in
            [cell/'raw.jsonl',cell/'summary.json',cell/'completion_v1.json',cell/'client_audit_v2.json',cell/'metrics.jsonl',cell/'telemetry_v1.jsonl',cell/'server.log']])


def pair_rows(raw,contract):
    one=raw['business'];two=contract['business'];assert one.keys()==two.keys()
    output=[]
    for k,r in two.items():
        ref=one[k];delta=r['task_score']-ref['task_score'];compiled=r['effective_level']!='L0'
        if not compiled:assert r['prompt_token_ids']==ref['prompt_token_ids']
        output.append(dict(model=r['model'],repeat=r['repeat'],source_group=r['source_group'],family=r['family'],
            session_id=r['session_id'],turn=r['turn_id'],row_type=r['row_type'],compiled=compiled,
            raw_score=ref['task_score'],contract_score=r['task_score'],score_delta=delta,
            material_up=delta>.03,material_down=delta<-.03,raw_positive=ref['task_score']>0,
            output_ID_change=r['output_token_ids']!=ref['output_token_ids'],finish_change=r['finish_reason']!=ref['finish_reason'],
            first_output_ID_divergence=first_divergence(ref['output_token_ids'],r['output_token_ids']),
            raw_output_tokens=len(ref['output_token_ids']),contract_output_tokens=len(r['output_token_ids']),
            raw_finish=ref['finish_reason'],contract_finish=r['finish_reason']))
    return output


def bootstrap_ratios(pairs,seed):
    rng=random.Random(seed);metrics=['wall_speedup','primary_goodput_ratio','TTFT_only_goodput_ratio']
    output={}
    for metric in metrics:
        values=[x[metric] for x in pairs]
        if any(x is None for x in values):output[metric]=dict(mean=None,CI95=None,undefined_pairs=sum(x is None for x in values));continue
        draws=[statistics.fmean(rng.choices(values,k=len(values))) for _ in range(10000)]
        output[metric]=dict(mean=statistics.fmean(values),min=min(values),max=max(values),
            CI95=[quantile(draws,.025),quantile(draws,.975)],fresh_process_pairs=len(values),draws=10000,
            boundary='Only3 paired processes; limited bootstrap resolution, not a source-cluster causal wall interval')
    return output


def quality_statistics(rows,route):
    group=rows if route=='ALL' else [r for r in rows if r['compiled']==(route=='compiled')]
    positive=[r for r in group if r['raw_positive']]
    return dict(pairs=len(group),compiled=sum(r['compiled'] for r in group),
        ID_changes=sum(r['output_ID_change'] for r in group),finish_changes=sum(r['finish_change'] for r in group),
        material_up=sum(r['material_up'] for r in group),material_down=sum(r['material_down'] for r in group),
        no_material_score_change=sum(not r['material_up'] and not r['material_down'] for r in group),
        raw_positive_pairs=len(positive),raw_positive_ID_changes=sum(r['output_ID_change'] for r in positive),
        raw_mean_score=statistics.fmean(r['raw_score'] for r in group) if group else None,
        contract_mean_score=statistics.fmean(r['contract_score'] for r in group) if group else None,
        ID_change_rate=ratio(sum(r['output_ID_change'] for r in group),len(group)),
        material_down_rate=ratio(sum(r['material_down'] for r in group),len(group)),
        material_up_rate=ratio(sum(r['material_up'] for r in group),len(group)),
        coverage=ratio(sum(r['compiled'] for r in rows),len(rows)))


def quality_clusters(pairs):
    output=[]
    for model,load in sorted({(r['model'],r['load']) for r in pairs}):
        allrows=[r for r in pairs if (r['model'],r['load'])==(model,load)]
        for cohort in ('ALL_business','future'):
            selected=allrows if cohort=='ALL_business' else [r for r in allrows if r['row_type']=='future']
            for family in ('ALL','HotpotQA','RepoBench'):
                rows=selected if family=='ALL' else [r for r in selected if r['family']==family]
                groups=defaultdict(list);by_family=defaultdict(list)
                for r in rows:groups[r['source_group']].append(r)
                for source,group in groups.items():by_family[group[0]['family']].append(source)
                assert all(len(sources)==3 for sources in by_family.values())
                # Cluster all source-associated tenants, turns and observed repeats.
                # Gate and performance clocks are not reconstructed by resampling.
                selections=[];rng=random.Random(202610182001)
                for _ in range(10000):
                    selections.append([s for family_sources in by_family.values() for s in rng.choices(family_sources,k=3)])
                for route in ('ALL','compiled','L0'):
                    point=quality_statistics(rows,route);intervals={};counts={}
                    for source,cluster in groups.items():
                        subset=cluster if route=='ALL' else [r for r in cluster if r['compiled']==(route=='compiled')]
                        counts[source]=(len(cluster),sum(r['compiled'] for r in cluster),len(subset),
                            sum(r['output_ID_change'] for r in subset),sum(r['material_down'] for r in subset),sum(r['material_up'] for r in subset))
                    draws={metric:[] for metric in ('ID_change_rate','material_down_rate','material_up_rate','coverage')}
                    for sample in selections:
                        all_count=all_compiled=count=ID=down=up=0
                        for source in sample:
                            a,b,c,d,e,f=counts[source];all_count+=a;all_compiled+=b;count+=c;ID+=d;down+=e;up+=f
                        draws['coverage'].append(ratio(all_compiled,all_count))
                        if count:
                            draws['ID_change_rate'].append(ID/count);draws['material_down_rate'].append(down/count);draws['material_up_rate'].append(up/count)
                    for metric,values in draws.items():
                        intervals[metric]=dict(CI95=[quantile(values,.025),quantile(values,.975)] if values else None,
                            defined_draws=len(values),undefined_draws=10000-len(values))
                    output.append(dict(model=model,load=load,cohort=cohort,family=family,route=route,
                        source_clusters=len(groups),**point,source_cluster_uncertainty=intervals,
                        uncertainty_boundary='Stratified source-cluster bootstrap conditional on3 observed process repeats; preserve tenants/turns within source. Zero-event interval is not a general risk upper bound. Undefined compiled draws remain counted.'))
    return output


def main(root,output,phase):
    study=root/STUDY
    assert not output.exists(),'Preserve every completed or failed analysis attempt'
    derived=read(study/'calibration/derived_profile_plan_v1.json');slo=derived['SLO']
    parent=read(study/'raw_calibration_freeze_v1.json')
    score_source=study/'source_snapshot_v1/scripts/phase20a_official_quality.py'
    assert sha(score_source)==next(x['sha256'] for x in parent['snapshot_files'] if x['path']=='scripts/phase20a_official_quality.py')
    spec=importlib.util.spec_from_file_location('ckv_final_frozen_scoring',score_source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    samples={r['revision_source_group']:r for r in lines(study/'inputs_v1/faithful_selected_sessions_v1.jsonl')}
    assert len(samples)==6
    if phase=='calibration':
        assert read(study/'calibration/profiles_exit_v1.json')['returncode']==0
        jobs=read(study/'raw_calibration_protocol_v1.json')['baseline_jobs']+derived['profile_jobs']
    else:
        protocol=read(study/'formal_protocol_v1.json');jobs=protocol['jobs'];assert len(jobs)==30
        for name in ('qwen','cross','gate'):
            assert read(study/'formal'/f'{name}_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
    cells={job['id']:audit_cell(study,job,slo,phase,module.standard_score,samples) for job in jobs}
    requests=[r for data in cells.values() for r in data['requests']];registrations=[r for data in cells.values() for r in data['registrations']]
    per_source=[];per_tenant=[];tails=[]
    for name,data in cells.items():
        grouped=defaultdict(list)
        for r in data['requests']:grouped[r['source_group']].append(r)
        for source,group in grouped.items():
            per_source.append(dict(cell=name,model=data['facts']['model'],policy=data['facts']['policy'],load=data['facts']['load'],
                repeat=data['facts']['repeat'],source_group=source,family=group[0]['family'],requests=len(group),
                compiled=sum(x['compiled'] for x in group),task_score_positive=sum(x['task_score_positive'] for x in group),
                compliant=sum(x['primary_SLO_compliant'] for x in group),
                mean_score=statistics.fmean(x['task_score'] for x in group),
                mean_readiness_TTFT_ms=statistics.fmean(x['readiness_TTFT_ms'] for x in group),
                P99_readiness_TTFT_ms=quantile([x['readiness_TTFT_ms'] for x in group],.99),
                logical_new_prefill_tokens=sum(x['initial_logical_new_prefill_tokens'] for x in group)))
            tenants=defaultdict(list)
            for row in group:tenants[row['session_id']].append(row)
            for tenant,items in tenants.items():
                per_tenant.append(dict(cell=name,model=data['facts']['model'],policy=data['facts']['policy'],load=data['facts']['load'],
                    repeat=data['facts']['repeat'],source_group=source,family=items[0]['family'],session_id=tenant,requests=len(items),
                    compiled=sum(x['compiled'] for x in items),compliant=sum(x['primary_SLO_compliant'] for x in items),
                    mean_readiness_TTFT_ms=statistics.fmean(x['readiness_TTFT_ms'] for x in items),
                    P99_readiness_TTFT_ms=quantile([x['readiness_TTFT_ms'] for x in items],.99),
                    length_events=sum(x['at_length_limit'] for x in items)))
        threshold=quantile([r['readiness_TTFT_ms'] for r in data['requests']],.99)
        tails += [dict(r,per_cell_P99_threshold_ms=threshold) for r in data['requests'] if r['readiness_TTFT_ms']>=threshold]
    comparisons=[];pairs=[];gate_pairs=[];aggregated=[];raw_repeats=[];quality=[]
    if phase!='calibration':
        grouped=defaultdict(list)
        for job in jobs:grouped[job['phase'],job['model'],job['load'],job['repeat']].append(job)
        for (regime,model,load,repeat),group in grouped.items():
            assert len(group)==2
            baseline=next(j for j in group if j['economic_gate']=='OFF') if regime=='gate' else next(j for j in group if j['policy']=='raw-order')
            treatment=next(j for j in group if j!=baseline)
            one=cells[baseline['id']];two=cells[treatment['id']];a=one['facts'];b=two['facts']
            comparisons.append(dict(regime=regime,model=model,load=load,repeat=repeat,
                baseline=baseline['id'],treatment=treatment['id'],comparison='ON versus OFF' if regime=='gate' else 'Contract versus Raw',
                wall_speedup=a['wall_s']/b['wall_s'],primary_goodput_ratio=ratio(b['primary_goodput_requests_per_s'],a['primary_goodput_requests_per_s']),
                TTFT_only_goodput_ratio=ratio(b['TTFT_only_goodput_requests_per_s'],a['TTFT_only_goodput_requests_per_s']),
                baseline_goodput=a['primary_goodput_requests_per_s'],treatment_goodput=b['primary_goodput_requests_per_s'],
                baseline_wall_s=a['wall_s'],treatment_wall_s=b['wall_s'],
                baseline_P99_ms=a['latencies']['readiness_TTFT_ms']['P99'],treatment_P99_ms=b['latencies']['readiness_TTFT_ms']['P99'],
                baseline_RPCs=a['actual_verification_RPCs'],treatment_RPCs=b['actual_verification_RPCs']))
            if regime!='gate':pairs += [dict(r,regime=regime,load=load) for r in pair_rows(one,two)]
            else:
                for k,r in two['business'].items():
                    ref=one['business'][k];delta=r['task_score']-ref['task_score']
                    gate_pairs.append(dict(model=model,load=load,repeat=repeat,source_group=r['source_group'],family=r['family'],
                        session_id=r['session_id'],turn=r['turn_id'],row_type=r['row_type'],
                        ON_level=r['effective_level'],OFF_level=ref['effective_level'],ON_score=r['task_score'],OFF_score=ref['task_score'],
                        score_delta_ON_minus_OFF=delta,material_up=delta>.03,material_down=delta<-.03,
                        ID_or_finish_change=changed(ref,r),same_input_IDs=r['prompt_token_ids']==ref['prompt_token_ids']))
        for regime,model,load in sorted({(r['regime'],r['model'],r['load']) for r in comparisons}):
            group=[r for r in comparisons if (r['regime'],r['model'],r['load'])==(regime,model,load)]
            assert len(group)==3
            aggregated.append(dict(regime=regime,model=model,load=load,process_uncertainty=bootstrap_ratios(group,202610182000),
                pooled_direct_wall_ratio=sum(r['baseline_wall_s'] for r in group)/sum(r['treatment_wall_s'] for r in group),
                pooled_baseline_goodput=sum(cells[r['baseline']]['facts']['compliant_requests'] for r in group)/sum(r['baseline_wall_s'] for r in group),
                pooled_treatment_goodput=sum(cells[r['treatment']]['facts']['compliant_requests'] for r in group)/sum(r['treatment_wall_s'] for r in group)))
        # All same-input Raw repeat pairs, including r2 GPU swap; no causal claim.
        for model,load in sorted({(j['model'],j['load']) for j in jobs if j['policy']=='raw-order'}):
            group=sorted([j for j in jobs if j['model']==model and j['load']==load and j['policy']=='raw-order'],key=lambda j:j['repeat'])
            for index,a in enumerate(group):
                for b in group[index+1:]:
                    one=cells[a['id']]['business'];two=cells[b['id']]['business'];assert one.keys()==two.keys()
                    for k,r in one.items():
                        other=two[k];assert r['prompt_token_ids']==other['prompt_token_ids']
                        raw_repeats.append(dict(model=model,load=load,repeat1=a['repeat'],repeat2=b['repeat'],same_GPU=a['lane']==b['lane'],
                            source_group=r['source_group'],session_id=r['session_id'],turn=r['turn_id'],row_type=r['row_type'],
                            ID_or_finish_change=changed(r,other),score_delta=other['task_score']-r['task_score']))
        quality=quality_clusters(pairs)
    output.mkdir(parents=True)
    for name,rows in [('requests_v1.csv',requests),('qualifications_v1.csv',registrations),('source_summary_v1.csv',per_source),('tenant_summary_v1.csv',per_tenant),
        ('P99_requests_v1.csv',tails),('paired_performance_v1.csv',comparisons),('paired_quality_v1.csv',pairs),
        ('gate_ON_OFF_quality_pairs_v1.csv',gate_pairs),('Raw_repeat_controls_v1.csv',raw_repeats)]:write_csv(output/name,rows)
    result=dict(schema_version='contractkv.final-serving-analysis.v1',phase=phase,complete_cells=len(cells),SLO=slo,
        measured_business_requests=len(requests),measured_future_requests=sum(r['row_type']=='future' for r in requests),
        actual_verification_RPCs=sum(x['actual_verification_RPCs'] for x in (d['facts'] for d in cells.values())),
        compiled_business_requests=sum(r['compiled'] for r in requests),compiled_future_requests=sum(r['compiled'] and r['row_type']=='future' for r in requests),
        compiled_vs_witness_changes=sum(r['compiled_vs_actual_witness_ID_or_finish_change'] is True for r in requests),
        cells=[d['facts'] for d in cells.values()],paired_aggregates=aggregated,quality_by_family_route_and_cohort=quality,
        source_files=[x for d in cells.values() for x in d['source_files']],
        source_freeze_sha256=sha(study/('raw_calibration_freeze_v1.json' if phase=='calibration' else 'formal_freeze_v1.json')),
        all_costs_on_direct_wall=True,controller_and_RPC_sums_not_additive_critical_path=True,
        tail_registration_overlap_is_bounded_not_unique_causal_attribution=True,
        native_initial_tokens_are_not_total_GPU_work_or_GPU_time=True,
        actual_GPU_active_vs_registered_tenant_identity_separated=True,
        finite_sources_and_repeats_not_a_general_safety_guarantee=True)
    result['frozen_scorer_sha256']=sha(score_source)
    result['analysis_entry_sha256']=sha(Path(__file__))
    result['every_business_score_independently_recomputed']=True
    result['RepoBench_primary_metric_boundary']='Frozen repository SequenceMatcher similarity; not program execution, not an independent reproduction of official Levenshtein edit similarity. A positive similarity is not a correct-code guarantee.'
    write_json(output/'summary_v1.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('cells','source_files','paired_aggregates')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['calibration','formal'],required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output.resolve(),args.phase)
