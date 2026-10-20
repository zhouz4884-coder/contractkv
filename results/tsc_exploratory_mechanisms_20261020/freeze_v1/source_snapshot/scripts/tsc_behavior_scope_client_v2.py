"""Three-arm exact-repeat repair experiment; all online costs are measured."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_template_task_protocol_v2 import prepared,candidate_plan,budget,ServingAuthority,DeploymentRegistrar
from scripts.tsc_behavior_scope_protocol_v2 import StrictServingAuthority
from scripts.contractkv_authorized_requests import AuthorizedRegistrar
from scripts.contractkv_exact_behavior import digest as exact_digest
from scripts.phase17_live_common import digest,tokenize
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_template_task_serving_client_v1 import stats
from scripts.tsc_revision_final_fixed_client_v2 import finish_after_backend_drain

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(args):
    begin=time.perf_counter();job=read(args.job);args.cell_id=job['id'];args.model_identity=job['model']
    assert not args.output.exists() and not args.summary.exists()
    args.output.touch();recorded=[]
    def record(row):
        value=dict(record_monotonic_s=time.perf_counter(),**row);recorded.append(value)
        with args.output.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
    inputs=args.study/('inputs_'+job['input_set']+'_v1')
    samples=lines(inputs/'sessions_v1.jsonl')
    shapes={(r['source_group'],r['tenant'],r['turn'],r['level']):r for r in lines(inputs/'CPU_shapes_v1.jsonl') if r['model']==args.model_identity}
    cls=StrictServingAuthority if job['policy']=='Strict-exact' else ServingAuthority
    auth=cls(args,read(args.identity),samples,8,sha(args.study/'protocol_v2.json'))
    certificates={};exact_records={};registrations=[]
    record(dict(row_type='service_epoch',job=job,begin=begin,zero_slack=True,
                protocol_sha256=sha(args.study/'protocol_v2.json'),clock='serial closed backlog, includes all qualification waits'))

    def register(sample,tenant,turn,raw=None):
        started=time.perf_counter();source=sample['revision_source_group'];strict=job['policy']=='Strict-exact'
        plan=candidate_plan(args,sample,tenant if strict else 0,turn if strict else 0)
        namespace=sample['revision_session_id']+(':'+str(tenant)+':'+str(turn) if strict else ':deployment')
        result=dict(certificate_issued=False,committed_tokens=0,attempts=[],failure_reason='')
        bound=behavior=None;candidate=None;scope='deployment';reference=raw
        if strict:
            scope=auth.behavior.key(raw['prompt_token_ids'],plan['prompt_token_ids'])
            margins=raw.get('reference_margins',[])
            if not raw.get('witness_available') or not margins or min(margins)<.0625:
                result['failure_reason']='Raw_complete_token_EOS_margin_unavailable_or_below_unchanged_floor'
            elif raw['finish_reason']!='stop':result['failure_reason']='Raw_did_not_complete_EOS'
            else:
                candidate=auth.private_generate(sample,plan['messages'],budget(sample),args.cell_id+'-candidate-'+namespace,False,kind='strict-candidate')
                record(dict(row_type='reference_generation',source_group=source,tenant=tenant,turn=turn,
                    reference_kind='private_candidate_free_generation_NOT_Raw_witness',result=candidate))
                if not candidate['success'] or candidate['finish_reason']!='stop':result['failure_reason']='candidate_incomplete'
                elif (candidate['output_token_ids'],candidate['finish_reason'])!=(raw['output_token_ids'],raw['finish_reason']):
                    result['failure_reason']='Raw_candidate_free_generation_differs'
                else:
                    registrar=AuthorizedRegistrar(.0625,.125,auth.cache,auth.cache_identity(sample))
                    result=registrar.register(args,namespace,scope,raw,dict(allow_verification=True,reason='exact_repeat_Raw_witness_and_private_candidate_equal',plan=plan),record)
                    if result['certificate_issued']:
                        request=next(r for r in reversed(recorded) if r['row_type']=='verification_request')
                        assert request['reference_prompt_ids_sha256']==raw['prompt_ids_sha256']
                        behavior=auth.behavior.issue(raw,candidate,result,raw['prompt_token_ids'],plan['prompt_token_ids'],
                            'RAW_QUERY',exact_digest(raw['prompt_token_ids']))
                        bound=auth.bind(sample,plan,result)
        else:
            reference=auth.private_generate(sample,plan['messages'],budget(sample),args.cell_id+'-reference-'+namespace,True)
            record(dict(row_type='reference_generation',source_group=source,reference_kind='COMPILED_DEPLOYMENT',result=reference))
            registrar=DeploymentRegistrar(auth.cache,auth.cache_identity(sample))
            result=registrar.register(args,namespace,scope,reference,dict(allow_verification=True,reason='historical_deployment_comparator',plan=plan),record)
            if result['certificate_issued']:bound=auth.bind(sample,plan,result)
        assert result.get('verification_status')!='indeterminate_request_failure','Preserve whole cell on indeterminate RPC'
        row=dict(row_type='registration',source_group=source,tenant=tenant,turn=turn,scope=scope,
                 reference_kind='RAW_QUERY' if strict else 'COMPILED_DEPLOYMENT',plan=plan,certificate=result,bound=bound,behavior=behavior,
                 full_controller_ms=(time.perf_counter()-started)*1000)
        registrations.append(row);record(row)
        if strict and behavior:
            errors=auth.admit(sample,tenant,turn,plan,result,bound,raw_ids=raw['prompt_token_ids'],candidate_ids=plan['prompt_token_ids'],behavior=behavior)
            assert not errors
            mutated=raw['prompt_token_ids']+[0]
            negative=auth.admit(sample,tenant,turn,plan,result,bound,raw_ids=mutated,candidate_ids=plan['prompt_token_ids'],behavior=behavior)
            missing=auth.admit(sample,tenant,turn,plan,result,bound,raw_ids=raw['prompt_token_ids'],candidate_ids=plan['prompt_token_ids'])
            assert negative and missing
            record(dict(row_type='admission_negative_controls',source_group=source,tenant=tenant,turn=turn,
                        changed_actual_suffix_errors=negative,authorized_but_missing_Raw_evidence_errors=missing,new_GPU_requests=0))
        return row

    if job['policy']=='Deployment':
        for sample in samples:
            if sample['revision_family']=='HotpotQA':certificates[sample['revision_source_group']]=register(sample,0,0)
    responses=[];ready=begin
    for sample in samples:
        source=sample['revision_source_group']
        for access in range(job['accesses']):
            for tenant,turn in [(0,1),(1,1)]:
                started=time.perf_counter();key=(source,tenant,turn)
                first=key not in exact_records
                _,_,raw_messages=prepared(sample,tenant,turn,'L0')
                # Actual tokenizer, not an inferred count or a schema identity.
                raw_ids=tokenize(args.base_url,args.model,raw_messages,True,args.timeout)
                assert digest(raw_ids)==shapes[source,tenant,turn,'L0']['prompt_ids_sha256']
                cert=exact_records.get(key) if job['policy']=='Strict-exact' else certificates.get(source)
                compiled=bool(cert and cert['certificate']['certificate_issued']);errors=[]
                messages=raw_messages
                if compiled:
                    plan=candidate_plan(args,sample,tenant,turn)
                    if job['policy']=='Strict-exact':
                        errors=auth.admit(sample,tenant,turn,plan,cert['certificate'],cert['bound'],
                            raw_ids=raw_ids,candidate_ids=plan['prompt_token_ids'],behavior=cert['behavior'])
                    else:errors=auth.admit(sample,tenant,turn,plan,cert['certificate'],cert['bound'])
                    if errors:compiled=False
                    else:messages=plan['messages']
                witness=(job['policy']=='Strict-exact' and first and sample['revision_family']=='HotpotQA' and job['accesses']>1)
                result=auth.generate(sample,tenant,messages,budget(sample),args.cell_id+'-business-'+str(len(responses)),witness)
                assert result['success'],'Business failure preserved, no scientific auto-rerun'
                level='L3' if compiled else 'L0';assert result['prompt_ids_sha256']==shapes[source,tenant,turn,level]['prompt_ids_sha256']
                score,metric,scorer=standard_score(sample['dataset'],sample['task'],result['output_text'],sample.get('answer',''))
                row=dict(row_type='business',sequence=len(responses),source_group=source,family=sample['revision_family'],
                    tenant=tenant,turn=turn,access=access,compiled=compiled,level=level,scope_binding_errors=errors,
                    started=started,planned_ready_time=ready,ready_ttft_ms=(result['first_time']-ready)*1000,
                    ready_latency_ms=(result['end_time']-ready)*1000,task_score=score,task_metric=metric,metric_source=scorer,result=result)
                record(row);responses.append(row);ready=result['end_time']
                if first:
                    if witness:exact_records[key]=register(sample,tenant,turn,result)
                    else:exact_records[key]=None
    end=finish_after_backend_drain(args)
    events={r['request_id']:r for r in lines(args.metrics_events) if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
    native=[]
    for row in recorded[:]:
        if row['row_type'] in ['business','reference_generation']:
            result=row['result'];event=events.get(result['request_id']);assert event
            assert event['prompt_tokens']==len(result['prompt_token_ids'])
            item=dict(row_type='native',kind=row['row_type'],request_id=result['request_id'],source_group=row['source_group'],
                      prompt_tokens=event['prompt_tokens'],prefix_hit_tokens=event['prefix_hit_tokens'],
                      new_prefill_tokens=event['prompt_tokens']-event['prefix_hit_tokens'])
            if row['row_type']=='business':item.update(sequence=row['sequence'],compiled=row['compiled'])
            native.append(item);record(item)
        elif row['row_type']=='verification_request':
            event=events[row['request_id']];assert event['prompt_tokens']==len(row['payload']['prompt_token_ids'])
            item=dict(row_type='native',kind='verification',request_id=row['request_id'],prompt_tokens=event['prompt_tokens'],
                      prefix_hit_tokens=event['prefix_hit_tokens'],new_prefill_tokens=event['prompt_tokens']-event['prefix_hit_tokens'])
            native.append(item);record(item)
    assert len(responses)==len(samples)*2*job['accesses']
    summary=dict(status='COMPLETE',job=job,execution_complete=True,offered=len(responses),successful=len(responses),
        service_begin_time=begin,service_end_time=end,wall_s=end-begin,compiled_business=sum(r['compiled'] for r in responses),
        actual_verification_RPCs=sum(r['row_type']=='verification_request' for r in recorded),
        certificate_objects=len(registrations),certificate_PASS=sum(r['certificate']['certificate_issued'] for r in registrations),
        full_controller_ms=sum(r['full_controller_ms'] for r in registrations),
        ready_TTFT_ms=stats([r['ready_ttft_ms'] for r in responses]),
        backend_TTFT_ms=stats([r['result']['ttft_ms'] for r in responses]),
        native_new_prefill_by_kind={k:sum(r['new_prefill_tokens'] for r in native if r['kind']==k) for k in ['business','reference_generation','verification']},
        failed_reasons=dict(Counter(r['certificate'].get('failure_reason','') for r in registrations if not r['certificate']['certificate_issued'])),
        actual_prompt_IDs_checked=len(responses),raw_file_sha256=sha(args.output),
        boundary='Closed backlog; repeated exact scope, no arbitrary metadata equivalence or open-arrival Goodput claim')
    with args.summary.open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(summary));return 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['study','job','identity','output','summary','metrics-events']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['base-url','model','policy-hash']:p.add_argument('--'+name,required=True)
    p.add_argument('--timeout',type=float,default=900);raise SystemExit(main(p.parse_args()))
