"""Freeze bounded serving/Gate matrices after Raw-only calibration, before Contract."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__ in (None,''):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_raw_derive_v1 import arrivals,read,sha,write,STUDY,MODELS


def matrix(arrival_records,rates):
    jobs=[];wave=0
    def add(phase,model,repeat,load,policy,gate,lane):
        key=f'{load}_r{repeat}';arrival=arrival_records[key]
        ident=f'{phase}_{model.split("-")[0].lower()}_{load}_r{repeat}_{policy}_{gate.lower()}'
        jobs.append(dict(id=ident,phase=phase,model=model,repeat=repeat,load=load,policy=policy,economic_gate=gate,
            lane=lane,wave=wave,port=9700+len(jobs),arrival=arrival['path'],arrival_sha256=arrival['sha256'],
            offered_rate_requests_per_s=rates[load],client_timeout_s=max(3600,math.ceil(360/rates[load]+1800)),
            expected_business_requests=360,expected_future_requests=324,
            peer_regime='isolated' if phase=='gate' else 'paired colocated endpoints'))
    for repeat in (1,2,3):
        for policy in (('risk-tail','raw-order') if repeat==2 else ('raw-order','risk-tail')):
            for index,load in enumerate(('common','high')):add('qwen',MODELS[0],repeat,load,policy,'ON',1-index if repeat==2 else index)
            wave+=1
    for repeat in (1,2,3):
        for policy in (('risk-tail','raw-order') if repeat==2 else ('raw-order','risk-tail')):
            for index,model in enumerate(MODELS[1:]):add('cross',model,repeat,'common',policy,'ON',1-index if repeat==2 else index)
            wave+=1
    for repeat in (1,2,3):
        for gate in (('OFF','ON') if repeat==2 else ('ON','OFF')):
            add('gate',MODELS[0],repeat,'common','risk-tail',gate,0);wave+=1
    assert len(jobs)==30 and len({j['id'] for j in jobs})==len({j['port'] for j in jobs})==30
    for job in jobs:
        pair=[j for j in jobs if j['phase']==job['phase'] and j['model']==job['model'] and j['load']==job['load'] and j['repeat']==job['repeat']]
        assert len(pair)==2 and pair[0]['lane']==pair[1]['lane'] and pair[0]['arrival_sha256']==pair[1]['arrival_sha256']
    for number in range(wave):
        group=[j for j in jobs if j['wave']==number]
        assert len(group)==(1 if group[0]['phase']=='gate' else 2)
        assert len({j['lane'] for j in group})==len(group)
    return jobs


def prepare(root):
    study=root/STUDY;derived=read(study/'calibration/derived_profile_plan_v1.json')
    assert not (study/'formal_protocol_v1.json').exists() and not (study/'formal_freeze_v1.json').exists()
    CPU=read(study/'formal_CPU_controls_v3.json');Linux=read(study/'formal_Linux_CPU_controls_v2.json')
    assert CPU['all_passed'] and Linux['all_passed'] and CPU['sources']==Linux['sources']
    for row in CPU['sources']:assert sha(root/row['path'])==row['sha256']
    assert read(study/'calibration/profiles_exit_v1.json')['returncode']==0
    assert len(read(study/'calibration/profiles_execution_state_v1.json')['completed_cells'])==3
    raw_parent=read(study/'raw_calibration_freeze_v1.json')
    assert derived['source_freeze_sha256']==sha(study/'raw_calibration_freeze_v1.json')
    for row in raw_parent['files']:assert sha(root/row['path'])==row['sha256'],row['path']
    for job in derived['profile_jobs']:
        assert sha(study/job['arrival'])==job['arrival_sha256']
        cell=study/'calibration/cells'/job['id'];summary=read(cell/'summary.json')
        assert read(cell/'completion_v1.json')['status']=='complete'
        assert summary['execution_complete'] and summary['arrival_requests']==120
        assert summary['verification_calls']==summary['compiled_future_requests']==0
        assert summary['raw_file_sha256']==sha(cell/'raw.jsonl')
    sessions_path=study/'inputs_v1/faithful_selected_sessions_v1.jsonl'
    sessions=[json.loads(x) for x in sessions_path.read_text(encoding='utf-8').splitlines()]
    rates=dict(common=derived['formal_common_rate'],high=derived['Qwen_high_rate'])
    records={}
    for index,load in enumerate(('common','high')):
        for repeat in (1,2,3):
            key=f'{load}_r{repeat}';relative=f'formal/arrivals/{key}_v1.json'
            trace=arrivals(sessions,6,rates[load],202610181000+100*index+repeat,sha(sessions_path))
            write(study/relative,trace);records[key]=dict(path=relative,sha256=sha(study/relative))
    jobs=matrix(records,rates)
    protocol=dict(schema_version='contractkv.final-faithful-fixed-arrival.v1',jobs=jobs,
        parent_Raw_freeze_sha256=sha(study/'raw_calibration_freeze_v1.json'),
        derived_Raw_plan_sha256=sha(study/'calibration/derived_profile_plan_v1.json'),
        rates_requests_per_s=rates,SLO=derived['SLO'],
        source_count=6,source_families={'HotpotQA':3,'RepoBench':3},tenants_per_template=6,
        registered_tenant_identities=36,turns_per_tenant=10,requests_per_cell=360,futures_per_cell=324,
        formal_cells=24,isolated_gate_cells=6,actual_GPU_max_num_seqs=2,client_dispatch_concurrency=2,
        exogenous_two_request_wave_barrier_retained=True,full_service_clock_includes_planned_idle_and_final_drain=True,
        service_clock_excludes_fresh_server_startup_and_pre_begin_catalog_expansion=True,
        method='existing faithful R4 risk-tail, original calibration, one-shot scope/margin/EOS/output guard/PSTP; v5 incomplete-reference fail-closed catch',
        gate_OFF_changes_economic_decision_only=True,no_extra_load_or_threshold_selection=True,
        cross_model_extension_guard='All 12 Qwen cells complete and 6 paired compiled-subset ID/finish checks have no unexplained difference; stop and attribute if difference',
        statistics=dict(primary_goodput='ALL warm+future satisfy readiness TTFT <= frozen TTFT SLO AND TPOT <= frozen TPOT SLO, count / full direct service wall',
            secondary_goodput='TTFT-only on ALL business / full direct service wall',
            per_process='report all 3 independent fresh-server pairs, absolute values, mean paired ratios, pooled compliant-count/pooled wall, min/max',
            process_uncertainty='10000 paired-process bootstrap draws with fixed seed202610182000; only3 process pairs, report limited resolution',
            source_uncertainty='10000 stratified source-cluster bootstrap draws (3 source clusters/family) with seed202610182001 for quality/coverage; preserve tenant/turn correlations',
            no_source_cluster_wall_reconstruction=True,no_request_iid_binomial_CI=True,
            undefined_ratios='retain zero denominators as undefined, do not add pseudocount or discard cell',
            score_changes='delta > .03 up, delta < -.03 down, else no substantive change; also exact output-ID and finish changes',
            distribution='mean/median/P95/P99 of readiness TTFT, backend TTFT, queue-before-controller, controller-to-submit, average TPOT, readiness E2E; linear interpolation quantiles',
            TPOT_not_true_TBT_distribution=True,initial_new_prefill_is_logical_uncached_input_not_GPU_milliseconds=True,
            missing_telemetry='null with availability; sampled active/waiting maxima are not continuous peaks'),
        gate_comparison='3 isolated ON/OFF fresh-server pairs, no isolated Raw baseline and no Raw speedup borrowed from colocated matrix')
    write(study/'formal_protocol_v1.json',protocol)
    files=[study/'formal_protocol_v1.json',study/'calibration/derived_profile_plan_v1.json',study/'raw_calibration_freeze_v1.json',
        root/'scripts/tsc_revision_final_raw_derive_v1.py',root/'scripts/tsc_revision_final_serving_prepare_v1.py',
        root/'scripts/tsc_revision_final_serving_worker_v1.py',root/'scripts/tsc_revision_final_raw_worker_v1.py',
        root/'scripts/tsc_revision_final_phase_supervisor_v1.py',root/'scripts/tsc_revision_final_serving_analysis_v1.py',
        root/'scripts/tsc_revision_final_serving_CPU_v1.py',study/'formal_CPU_controls_v3.json',study/'formal_Linux_CPU_controls_v2.json',
        root/'scripts/tsc_revision_mechanism_worker_v3.py',root/'scripts/tsc_tableIII_fullcost_worker_v3.py']
    files += [study/x['path'] for x in records.values()]
    files += [root/x['path'] for x in raw_parent['files']]
    for job in read(study/'raw_calibration_protocol_v1.json')['baseline_jobs']+derived['profile_jobs']:
        files += [study/'calibration/cells'/job['id']/name for name in ('summary.json','completion_v1.json','client_audit_v2.json')]
    files += [study/'calibration'/f'{phase}_{kind}_v1.json' for phase in ('baseline','profiles') for kind in ('execution_state','exit')]
    freeze=dict(schema_version='contractkv.final-serving-freeze.v1',files=[dict(path=p.relative_to(root).as_posix(),sha256=sha(p)) for p in sorted(set(files))],
        parent_source_snapshot_sha256=sha(study/'raw_calibration_freeze_v1.json'),no_new_model_runtime_or_source_snapshot_copy=True,
        no_formal_Contract_outputs_before_this_freeze=True,formal_business_requests=24*360,gate_business_requests=6*360,
        bounded_matrix_no_outcome_driven_expansion=True)
    write(study/'formal_freeze_v1.json',freeze)
    print(json.dumps(dict(formal_freeze_sha256=sha(study/'formal_freeze_v1.json'),jobs=len(jobs),rates=rates,SLO=derived['SLO'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();prepare(args.root.resolve())
