"""Measured raw, legacy-descent, and prospective single-shot serving conditions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from threading import Lock
import time
from types import SimpleNamespace
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r1r_live as legacy
from scripts import tsc_revision_live as original
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_r2_admission import SingleShotRegistrar
from scripts.tsc_revision_r2_candidate_plan import candidate_plan
from scripts.tsc_revision_r2_benefit_policy import prospective_benefit
from scripts.phase17_live_common import digest,post_json
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase20a_official_quality import standard_score

def main():
    p=argparse.ArgumentParser()
    for name in ('protocol','sessions','catalog','output','summary','metrics-events'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('model','model-identity','base-url','cell-id','policy-hash','study'):p.add_argument('--'+name,required=True)
    p.add_argument('--policy',choices=('raw-order','legacy-prefix','margin-benefit'),required=True)
    p.add_argument('--repeat',type=int,required=True);p.add_argument('--tenants-per-template',type=int,default=1)
    p.add_argument('--timeout',type=float,default=600);a=p.parse_args()
    protocol_path=a.protocol;a.protocol=json.loads(a.protocol.read_text(encoding='utf-8'));a.experiment='free-generation';a.output_budget=0
    catalog=json.loads(a.catalog.read_text(encoding='utf-8'));samples=original.read_jsonl(a.sessions)
    if a.output.exists():raise RuntimeError('Preserve every attempted cell')
    a.output.parent.mkdir(parents=True,exist_ok=True);rows=[];certificates={};gates={};lock=Lock()
    registrar=SingleShotRegistrar(catalog['raw_token_margin_floor'],catalog['candidate_token_margin_floor'])
    if a.tenants_per_template>1:
        expanded=[]
        for sample in samples:
            for tenant in range(a.tenants_per_template):
                clone=deepcopy(sample);clone['shared_template_id']=sample['revision_session_id']
                clone['revision_session_id']+=f'-tenant{tenant:02d}';expanded.append(clone)
        samples=expanded
    def append(row):
        with lock:
            rows.append(row)
            with a.output.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    def observed_legacy_post(url,payload,timeout):
        append({'row_type':'verification_request','request_id':payload['request_id'],'payload':payload,
                'prompt_ids_sha256':digest(payload['prompt_token_ids']),'request_hash_computed_before_dispatch':True})
        response=post_json(url,payload,timeout)
        append({'row_type':'verification_response','request_id':payload['request_id'],'response':response})
        return response
    legacy.post_json=observed_legacy_post
    legacy_args=SimpleNamespace(**{**vars(a),'policy':'query-prefix'})
    begin=time.perf_counter()
    for start in range(0,len(samples),a.protocol['runtime']['concurrency']):
        cohort=samples[start:start+a.protocol['runtime']['concurrency']];ready=time.perf_counter()
        for turn in range(10):
            jobs=[];pending=[]
            for sample in cohort:
                prepared=legacy.prepare(a,sample,turn);case,raw,maximum,budget,scope=prepared
                namespace=sample.get('shared_template_id',sample['revision_session_id']);key=(namespace,scope)
                calibration=catalog['models'][a.model_identity][sample['revision_family']]
                if a.policy=='margin-benefit' and key not in gates:
                    gate={'allow_verification':False,'reason':'inherited_family_L0','plan':None}
                    if calibration['level']!='L0':
                        plan=candidate_plan(a,prepared,calibration['level'])
                        reuses=catalog['expected_query_repetitions_per_registered_tenant_hint']*a.tenants_per_template-min(a.protocol['runtime']['concurrency'],a.tenants_per_template)
                        gate={**prospective_benefit(max(0,plan['stable_full_blocks']-calibration['raw_native_prefix_full_blocks_p95']),16,reuses,calibration['prefill_ms_per_token'],calibration['verification_rpc_p95_ms'],plan['cpu_http_preparation_ms'],catalog['benefit_safety_factor'],calibration['complete_qualification_p95_ms']),'plan':plan,'declared_remaining_reuse_hint':reuses,'native_prefix_discount_blocks':calibration['raw_native_prefix_full_blocks_p95']}
                    gates[key]=gate
                    append({'row_type':'prospective_plan','certificate_namespace':namespace,'query_scope':scope,'family':sample['revision_family'],'turn_id':turn,**gate})
                cert=certificates.get(key);compiled=a.policy!='raw-order' and bool(cert and cert['certificate_issued'])
                level=cert['selected_level'] if compiled else 'L0';messages=raw
                if compiled:
                    order=layout_for_level(case,level,a.protocol['layout']['ladder'])['topological_order']
                    messages=[raw[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
                first=a.policy!='raw-order' and cert is None and maximum!='L0'
                witness=first and (a.policy=='legacy-prefix' or gates[key]['allow_verification'])
                jobs.append((sample,prepared,messages,compiled,level,witness,first,key))
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                outputs=list(pool.map(lambda j:business_generate(a,j[2],j[1][3],f'{a.cell_id}-{j[0]["revision_session_id"]}-t{turn}',j[5],a.policy_hash+':'+j[7][0] if j[3] else None),jobs))
            wave_end=max(o['end_time'] for o in outputs)
            for job,out in zip(jobs,outputs):
                sample,prepared,messages,compiled,level,witness,first,key=job
                score,metric,source=standard_score(sample['dataset'],sample['task'],out['output_text'],sample.get('answer',''))
                invalid=False
                if compiled:
                    cert=certificates[key];n=int(cert.get('committed_tokens',0))
                    invalid=n<=0 or digest(out['prompt_token_ids'][:cert['stable_prefix_tokens']])!=cert['stable_prefix_hash']
                row={'row_type':'warm' if turn==0 else 'future','session_id':sample['revision_session_id'],'source_group':sample['revision_source_group'],'family':sample['revision_family'],'model':a.model_identity,'policy':a.policy,'repeat':a.repeat,'turn_id':turn,'study':a.study,'query_scope':prepared[4],'scope_previously_certified':compiled,'scope_first_raw_business':witness,'scope_first_decision_business':first,'certificate_namespace':key[0],'tenant_id':sample['revision_session_id'],'effective_level':level,'scope_invalid_admission':invalid,'output_budget':prepared[3],'task_score':score,'task_metric':metric,'metric_source':source,**out,'ready_ttft_ms':(out['first_time']-ready)*1000 if out['first_time'] else 0,'reference_source':'actual business stream' if witness else 'not_requested'}
                append(row)
                if not out['success'] or invalid:raise RuntimeError('Business/evidence/admission failure; preserve cell')
                if first and not any(j[3]==key for j in pending):pending.append((sample,prepared,out,key))
            ready=wave_end
            if pending:
                def register(job):
                    sample,prepared,out,key=job
                    if a.policy=='legacy-prefix':return legacy.register(legacy_args,sample,prepared,out,turn)
                    return registrar.register(a,key[0],key[1],out,gates[key],record=append)
                with ThreadPoolExecutor(max_workers=len(pending)) as pool:results=list(pool.map(register,pending))
                for (sample,prepared,_,key),cert in zip(pending,results):
                    if cert.get('verification_status')=='indeterminate_request_failure':raise RuntimeError('Indeterminate verification; cannot claim safe rejection')
                    if any(not x.get('certificate_issued') and int(x.get('committed_tokens',0)) for x in cert['attempts']):raise RuntimeError('Rejected publication')
                    certificates[key]=cert
                    append({'row_type':'verification','session_id':sample['revision_session_id'],'certificate_namespace':key[0],'family':sample['revision_family'],'turn_id':turn,**cert})
            print(json.dumps({'cell':a.cell_id,'cohort':start,'turn':turn,'futures':sum(r['row_type']=='future' for r in rows)}),flush=True)
    service_end=time.perf_counter()
    time.sleep(.5);metrics=original.load_metrics(a.metrics_events);joins=[]
    for row in rows:
        if row['row_type'] in {'warm','future'}:
            event=metrics.get(row['request_id'],{});row['metric_join_success']=bool(event) and event['prompt_tokens']==len(row['prompt_token_ids'])
            row['prefix_hit_tokens']=event.get('prefix_hit_tokens');row['new_prefill_tokens']=event['prompt_tokens']-event['prefix_hit_tokens'] if event else None
            joins.append(row['metric_join_success'])
        if row['row_type']=='verification_request':
            event=metrics.get(row['request_id'],{});joins.append(bool(event) and event['prompt_tokens']==len(row['payload']['prompt_token_ids']))
    a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    futures=[r for r in rows if r['row_type']=='future'];verification=[r for r in rows if r['row_type']=='verification']
    requested={r['request_id'] for r in rows if r['row_type']=='verification_request'}
    responded={r['request_id'] for r in rows if r['row_type']=='verification_response'}
    complete=len(futures)==len(samples)*9 and all(joins) and all(r['success'] for r in futures) and requested==responded
    result={'schema_version':'tsc-r2.single-shot-live.v1','cell':a.cell_id,'study':a.study,'policy':a.policy,'repeat':a.repeat,'execution_complete':complete,'futures':len(futures),'expected_futures':len(samples)*9,'successful_futures':sum(r['success'] for r in futures),'all_actual_metric_joins':len(joins),'sessions_sha256':hashlib.sha256(a.sessions.read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256(protocol_path.read_bytes()).hexdigest(),'catalog_sha256':hashlib.sha256(a.catalog.read_bytes()).hexdigest(),'tenants_per_template':a.tenants_per_template,'wall_s_including_all_setup_and_verification':service_end-begin,'post_measurement_audit_wall_s':time.perf_counter()-service_end,'verification_calls':sum(len(r['attempts']) for r in verification),'verification_ms_total':sum(r['complete_verification_ms'] for r in verification),'compiled_future_requests':sum(r['effective_level']!='L0' for r in futures),'raw_file_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'boundary':'Service wall includes actual planning, business, scoring/logging and all synchronous qualification waits. Same two-request wave readiness barrier as legacy. Post-measurement flush/audit is reported separately, excluded for all policies. Reference is the real first raw business output.'}
    a.summary.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));return 0 if complete else 2

if __name__=='__main__':raise SystemExit(main())
