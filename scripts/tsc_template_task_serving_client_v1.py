"""Raw-only calibration and globally timed task-bearing deployment service."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
from threading import Lock
import time
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_template_task_protocol_v2 import prepared,candidate_plan,ServingAuthority,DeploymentRegistrar,budget
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_final_fixed_client_v2 import finish_after_backend_drain
from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase20a_official_quality import standard_score

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ready_latency(response,planned):
    return ((response['first_time']-planned)*1000 if response.get('first_time') is not None else None,
            (response['end_time']-planned)*1000 if response.get('end_time') is not None else None)

def stats(values):
    return dict(mean=sum(values)/len(values),p95=percentile(values,.95),p99=percentile(values,.99)) if values else dict(mean=None,p95=None,p99=None)

def main(args):
    begin=time.perf_counter();epoch=time.time()
    job=read(args.job);args.cell_id=job['id'];args.model_identity=job['model']
    assert not args.output.exists() and not args.summary.exists();args.output.touch()
    lock=Lock();recorded=[]
    def record(r):
        with lock:
            value=dict(record_monotonic_s=time.perf_counter(),**r)
            with args.output.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
            recorded.append(value)
    inputs=args.study/f'inputs_{job["input_set"]}_v2'
    samples=lines(inputs/'sessions_v2.jsonl');by_source={r['revision_source_group']:r for r in samples}
    shapes={(r['source_group'],r['tenant'],r['turn'],r['level']):r for r in lines(inputs/'CPU_shapes_v2.jsonl') if r['model']==args.model_identity}
    authority=ServingAuthority(args,read(args.identity),samples,8,job['qualification_hash'])
    trace=read(args.study/job['arrivals']);frames=trace['requests']
    expected=80 if job['phase']=='calibration' else 384
    assert len(frames)==expected and all(r['source_group'] in by_source for r in frames)
    record(dict(row_type='service_epoch',job=job,wall_begin_time=begin,wall_begin_epoch_s=epoch,
        arrivals_sha256=sha(args.study/job['arrivals']),reference='compiled deployment canary, Raw equivalence separately measured',
        zero_slack=True,all_business_cache_groups_template_authorized=True))
    certificates={};registrations=[]
    def register_one(sample,tenant):
        started=time.perf_counter();scope=('template' if tenant is None else f'session-tenant{tenant:02d}')
        object_id=sample['revision_session_id']+':'+scope
        plan=candidate_plan(args,sample,0,0)
        reference=authority.private_generate(sample,plan['messages'],budget(sample),f'{args.cell_id}-reference-{object_id}',True)
        shape=shapes[sample['revision_source_group'],0,0,'L3']
        assert reference['success'] and reference['prompt_ids_sha256']==shape['prompt_ids_sha256']==plan['prompt_ids_sha256']
        record(dict(row_type='reference_generation',object_id=object_id,source_group=sample['revision_source_group'],
            family=sample['revision_family'],result=reference,reference_kind='controller_private_compiled_canary'))
        check=python_statement_contract(reference['output_text']) if sample['revision_family']=='RepoBench' else dict(passed=True,reason='not_code')
        registrar=DeploymentRegistrar(authority.cache,authority.cache_identity(sample))
        result=registrar.register(args,object_id,'deployment',reference,
            dict(allow_verification=check['passed'],reason='frozen_qualified_deployment' if check['passed'] else 'compiled_reference_output_contract:'+check['reason'],plan=plan),record)
        assert result.get('verification_status')!='indeterminate_request_failure','Verification response unavailable; retain whole cell'
        bound=authority.bind(sample,plan,result,tenant) if result['certificate_issued'] else None
        row=dict(row_type='registration',object_id=object_id,source_group=sample['revision_source_group'],family=sample['revision_family'],
            tenant_scope='*' if tenant is None else tenant,plan=plan,certificate=result,bound=bound,
            started_monotonic_s=started,ended_monotonic_s=time.perf_counter(),reference_output_check=check)
        row['complete_controller_ms']=(row['ended_monotonic_s']-started)*1000
        record(row)
        return sample,tenant,row
    if job['policy']!='Raw-authorized':
        assert job['phase']=='formal'
        objects=[]
        for sample in samples:
            if sample['revision_family'] not in job['eligible_families']:
                record(dict(row_type='frozen_Raw_fallback',source_group=sample['revision_source_group'],family=sample['revision_family'],reason='development_family_not_qualified'))
                continue
            for tenant in ([None] if job['policy']=='Template-qualified' else range(8)):objects.append((sample,tenant))
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(register_one,*item) for item in objects]
            for future in as_completed(pending):
                sample,tenant,row=future.result();registrations.append(row)
                for member in (range(8) if tenant is None else [tenant]):certificates[sample['revision_source_group'],member]=row
    registration_end=time.perf_counter()
    record(dict(row_type='registration_barrier_complete',begin_time=begin,ready_monotonic_s=registration_end,
        global_epoch_not_reset=True,certificate_objects=len(registrations)))
    def business(frame,enqueued):
        started=time.perf_counter();sample=by_source[frame['source_group']];tenant=frame['tenant'];turn=frame['turn']
        cert=certificates.get((frame['source_group'],tenant));compiled=bool(cert and cert['certificate']['certificate_issued'])
        errors=[]
        if compiled:
            errors=authority.admit(sample,tenant,turn,cert['plan'],cert['certificate'],cert['bound'])
            assert not errors,'Frozen legitimate request binding mismatch: '+str(errors)
        level='L3' if compiled else 'L0'
        _,_,messages=prepared(sample,tenant,turn,level)
        result=authority.generate(sample,tenant,messages,budget(sample),f'{args.cell_id}-business-{frame["sequence"]}')
        shape=shapes[frame['source_group'],tenant,turn,level]
        if result['success']:
            assert result['prompt_ids_sha256']==shape['prompt_ids_sha256'] and len(result['prompt_token_ids'])==shape['prompt_tokens']
            score,metric,metric_source=standard_score(sample['dataset'],sample['task'],result['output_text'],sample.get('answer',''))
        else:score,metric,metric_source=0.,'incomplete','incomplete'
        planned=begin+frame['ready_offset_s'];ready_ttft,ready_e2e=ready_latency(result,planned)
        row=dict(row_type='business',sequence=frame['sequence'],source_group=frame['source_group'],family=sample['revision_family'],tenant=tenant,turn=turn,
            planned_ready_offset_s=frame['ready_offset_s'],planned_ready_time=planned,enqueued_monotonic_s=enqueued,controller_start_monotonic_s=started,
            client_queue_ms=max(0,(started-enqueued)*1000),client_total_precontroller_wait_ms=max(0,(started-planned)*1000),
            compiled=compiled,level=level,scope_binding_errors=errors,certificate_object=cert['object_id'] if cert else None,
            ready_ttft_ms=ready_ttft,ready_latency_ms=ready_e2e,result=result,task_score=score,task_metric=metric,metric_source=metric_source)
        record(row);return row
    responses=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[]
        for frame in frames:
            deadline=begin+frame['ready_offset_s'];remaining=deadline-time.perf_counter()
            if remaining>0:time.sleep(remaining)
            enqueued=time.perf_counter();pending.append(pool.submit(business,frame,enqueued))
        for future in as_completed(pending):responses.append(future.result())
    service_end=finish_after_backend_drain(args)
    observed={r['request_id']:r for r in lines(args.metrics_events) if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
    def native(result):
        event=observed.get(result['request_id'])
        if not result['success']:return dict(metric_join_success=bool(event),prefix_hit_tokens=None,new_prefill_tokens=None)
        assert event and event['prompt_tokens']==len(result['prompt_token_ids']),'Actual initial prefill observation missing'
        return dict(metric_join_success=True,prefix_hit_tokens=event['prefix_hit_tokens'],
            new_prefill_tokens=event['prompt_tokens']-event['prefix_hit_tokens'],prompt_tokens=event['prompt_tokens'],
            observed_physical_block_count=event['physical_block_count'])
    metrics=[]
    for row in responses:
        value=native(row['result']);metrics.append(dict(row_type='business_native',sequence=row['sequence'],request_id=row['result']['request_id'],**value))
    reference_metrics=[native(r['result']) for r in recorded if r['row_type']=='reference_generation']
    verification_metrics=[]
    for r in recorded:
        if r['row_type']=='verification_request':
            event=observed[r['request_id']];assert event['prompt_tokens']==len(r['payload']['prompt_token_ids'])
            verification_metrics.append(dict(request_id=r['request_id'],prompt_tokens=event['prompt_tokens'],prefix_hit_tokens=event['prefix_hit_tokens'],new_prefill_tokens=event['prompt_tokens']-event['prefix_hit_tokens']))
    for r in metrics:record(r)
    successful=[r for r in responses if r['result']['success']]
    assert len(responses)==expected and len({r['sequence'] for r in responses})==expected
    summary=dict(status='COMPLETE',job=job,execution_complete=True,offered=expected,successful=len(successful),compiled_business=sum(r['compiled'] for r in responses),
        service_begin_time=begin,service_end_time=service_end,wall_s=service_end-begin,last_arrival_offset_s=max(r['ready_offset_s'] for r in frames),
        registration_barrier_from_epoch_ms=(registration_end-begin)*1000,registration_controller_work_ms=sum(r['complete_controller_ms'] for r in registrations),
        certificate_objects=len(registrations),certificate_PASS=sum(r['certificate']['certificate_issued'] for r in registrations),
        actual_verification_RPCs=sum(len(r['certificate']['attempts']) for r in registrations),
        failed_verification_RPC_ms=sum(a['verification_ms'] for r in registrations for a in r['certificate']['attempts'] if not a.get('certificate_issued')),
        business_new_prefill_tokens=sum(r['new_prefill_tokens'] or 0 for r in metrics),reference_extra_new_prefill_tokens=sum(r['new_prefill_tokens'] or 0 for r in reference_metrics),
        verification_extra_new_prefill_tokens=sum(r['new_prefill_tokens'] for r in verification_metrics),verification_native=verification_metrics,
        backend_TTFT_ms=stats([r['result']['ttft_ms'] for r in successful]),
        backend_e2e_ms=stats([r['result']['latency_ms'] for r in successful]),
        ready_TTFT_ms=stats([r['ready_ttft_ms'] for r in successful]),
        ready_e2e_ms=stats([r['ready_latency_ms'] for r in successful]),
        business_native_unavailable=sum(r['prefix_hit_tokens'] is None for r in metrics),
        achieved_throughput=expected/(service_end-begin),all_successful_actual_prompt_IDs_checked=len(successful),
        arrivals_sha256=sha(args.study/job['arrivals']),generation_budgets={'HotpotQA':128,'RepoBench':384},
        boundary='Fixed global epoch includes preparation, registration and failed work. Arrivals never reset after registration; client concurrency2. Deployment attestation does not certify arbitrary Raw equivalence. Native new-prefill is actual prompt minus initial engine hit, not GPU time.')
    if job['phase']=='formal':
        slo=job['SLO'];n=sum(r['ready_ttft_ms']<=slo['TTFT_ms'] for r in successful)
        joint=sum(r['ready_ttft_ms']<=slo['TTFT_ms'] and r['ready_latency_ms']<=slo['E2E_ms'] for r in successful)
        summary.update(SLO_compliant=n,SLO_fraction=n/expected,absolute_SLO_goodput=n/(service_end-begin),joint_SLO_compliant=joint,joint_absolute_goodput=joint/(service_end-begin))
    summary['raw_file_sha256']=sha(args.output);summary['post_measurement_audit_s']=time.perf_counter()-service_end
    with args.summary.open('x',encoding='utf-8',newline='\n') as f:json.dump(summary,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    print(json.dumps(summary));return 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['study','job','identity','output','summary','metrics-events']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['base-url','model','policy-hash']:p.add_argument('--'+name,required=True)
    p.add_argument('--timeout',type=float,default=900);raise SystemExit(main(p.parse_args()))
