"""Apply the preregistered Raw calibration formulas without reading Contract outputs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics


STUDY='results/tsc_task_faithful_open_arrival_20261018'
MODELS=('Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2);handle.write('\n')


def percentile(values,q):
    values=sorted(float(x) for x in values)
    assert values and all(math.isfinite(x) and x>=0 for x in values)
    at=(len(values)-1)*q;low=math.floor(at);high=math.ceil(at)
    return values[low]+(values[high]-values[low])*(at-low)


def arrivals(sessions,tenants,rate,seed,sessions_sha):
    assert math.isfinite(rate) and rate>0 and tenants%2==0
    ids=[x['revision_session_id']+f'-tenant{tenant:02d}' for x in sessions for tenant in range(tenants)]
    count=len(ids)*10;wave_count=count//2;rng=random.Random(seed)
    spacings=[rng.expovariate(1.) for _ in range(wave_count-1)]
    target=(wave_count-1)*2/rate;scale=target/sum(spacings);offsets=[0.]
    for interval in spacings:offsets.append(offsets[-1]+interval*scale)
    offsets[-1]=target
    waves=[]
    for start in range(0,len(ids),2):
        for turn in range(10):
            waves.append(dict(cohort_start=start,turn=turn,ready_offset_s=offsets[len(waves)],
                session_ids=ids[start:start+2],wave_index=len(waves)))
    return dict(schema_version='tsc-r4.fixed-wave-arrivals.v1',sessions_sha256=sessions_sha,
        tenants_per_template=tenants,concurrency=2,actual_business_requests=count,waves=waves,
        fixed_seed=seed,offered_rate_requests_per_s=rate,offered_horizon_s=count/rate,
        rule='Exogenous fixed-count normalized exponential inter-wave spacings; original two-request wave barrier remains')


def derive(root):
    study=root/STUDY;calibration=study/'calibration'
    assert read(calibration/'baseline_exit_v1.json')['returncode']==0
    state=read(calibration/'baseline_execution_state_v1.json')
    assert state['status']=='COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==4
    protocol=read(study/'raw_calibration_protocol_v1.json')
    capacities={model:[] for model in MODELS};observations={model:[] for model in MODELS};sources=[]
    for job in protocol['baseline_jobs']:
        cell=study/'calibration/cells'/job['id'];summary=read(cell/'summary.json')
        complete=read(cell/'completion_v1.json');audit=read(cell/'client_audit_v2.json')
        assert complete['status']=='complete' and complete['job']==job
        assert summary['execution_complete'] and summary['arrival_requests']==120 and summary['futures']==108
        assert summary['verification_calls']==summary['compiled_future_requests']==0
        assert summary['raw_file_sha256']==sha(cell/'raw.jsonl')
        assert audit['result']=='completed' and audit['actual_business_prompt_ID_hashes_checked']==120
        rows=[json.loads(x) for x in (cell/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
        business=[r for r in rows if r['row_type'] in ('warm','future')]
        assert len(business)==120 and len(rows)==120
        assert all(r['success'] and r['policy']=='raw-order' and r['effective_level']=='L0' for r in business)
        assert all(r['metric_join_success'] for r in business)
        wall=summary['wall_s_including_all_setup_and_verification'];assert wall>0
        capacities[job['model']].append(120/wall);observations[job['model']]+=business
        sources.append(dict(cell=job['id'],model=job['model'],wall_s=wall,Raw_capacity_requests_per_s=120/wall,
            files=[dict(path=p.relative_to(study).as_posix(),sha256=sha(p)) for p in
                [cell/'summary.json',cell/'raw.jsonl',cell/'client_audit_v2.json',cell/'completion_v1.json']]))
    capacity={model:statistics.median(values) for model,values in capacities.items()}
    assert [len(capacities[m]) for m in MODELS]==[2,1,1]
    p95={}
    for model,rows in observations.items():
        intrinsic=[];tpot=[]
        for row in rows:
            assert row['controller_to_submit_ms'] is not None
            intrinsic.append(row['ttft_ms']+row['controller_to_submit_ms']);tpot.append(row['tpot_ms'])
        p95[model]=dict(requests=len(rows),intrinsic_TTFT_ms=percentile(intrinsic,.95),TPOT_ms=percentile(tpot,.95))
    slo=dict(TTFT_ms=max(100,100*math.ceil(1.25*max(x['intrinsic_TTFT_ms'] for x in p95.values())/100)),
        TPOT_ms=max(20,5*math.ceil(1.25*max(x['TPOT_ms'] for x in p95.values())/5)),
        basis='Linear-interpolation empirical P95 per model; max across models, preregistered 1.25 multiplier and upward rounding',
        upstream_burst_queue_excluded_from_SLO_calibration=True)
    q=capacity[MODELS[0]];common=.9*min(capacity.values());high=1.05*q
    inputs=study/'inputs_v1/faithful_selected_sessions_v1.jsonl'
    sessions=[json.loads(x) for x in inputs.read_text(encoding='utf-8').splitlines()]
    jobs=[]
    for index,(multiple,wave,lane,port) in enumerate(zip([.4,.7,1.05],[2,2,3],[0,1,0],[9604,9605,9606])):
        name=f'raw_profile_q_{index}';relative=f'calibration/arrivals/{name}_v1.json'
        trace=arrivals(sessions,2,multiple*q,202610180700+index,sha(inputs));write(study/relative,trace)
        jobs.append(dict(id=name,model=MODELS[0],lane=lane,wave=wave,port=port,arrival=relative,
            arrival_sha256=sha(study/relative),offered_rate_requests_per_s=multiple*q,
            client_timeout_s=max(3600,math.ceil(120/(multiple*q)+900))))
    out=dict(schema_version='contractkv.raw-derived-profile-plan.v1',source_freeze_sha256=sha(study/'raw_calibration_freeze_v1.json'),
        derivation_entry_sha256=sha(Path(__file__)),baseline_sources=sources,capacity_requests_per_s=capacity,
        per_model_intrinsic_P95=p95,SLO=slo,formal_common_rate=common,Qwen_high_rate=high,profile_jobs=jobs,
        no_Contract_outputs_used=True,no_model_or_source_selection_from_results=True,
        primary_goodput='all warm+future with readiness TTFT and average streaming TPOT within frozen SLO, divided by complete service wall',
        secondary_goodput='readiness TTFT-only',TPOT_is_average_not_token_interval_distribution=True)
    write(calibration/'derived_profile_plan_v1.json',out)
    print(json.dumps(dict(derived_sha256=sha(calibration/'derived_profile_plan_v1.json'),capacities=capacity,SLO=slo,
        formal_common_rate=common,Qwen_high_rate=high,profile_cells=3)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();derive(args.root.resolve())
