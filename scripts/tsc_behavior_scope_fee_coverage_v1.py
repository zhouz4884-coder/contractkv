"""Cross-check actual HTTP, responses, Native events and full measurement clock."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
STUDY=Path('results/tsc_behavior_scope_repair_20261020')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def main(root,phases,output):
    study=root/STUDY;cells=[]
    for phase in phases:
        state=read(study/(phase+'_execution_state_v4.json'));assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS'
        for job in read(study/(phase+'_jobs_v4.json'))['jobs']:
            cell=study/'runs'/job['id']/'attempt1';rr=lines(cell/'responses.jsonl');summary=read(cell/'summary_v1.json')
            generated=[r for r in rr if r['row_type'] in ['business','reference_generation']]
            requests=[r for r in rr if r['row_type']=='verification_request']
            responses=[r for r in rr if r['row_type']=='verification_response']
            expected={r['result']['request_id'] for r in generated}|{r['request_id'] for r in requests}
            native=[r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')]
            actual=Counter(r['request_id'] for r in native)
            assert all(actual[r]==1 for r in expected),'Missing/duplicate actual initial Native observation'
            assert not set(actual)-expected,'Unaccounted GPU request; audit rather than omit'
            assert len(requests)==len(responses)==summary['actual_verification_RPCs']
            log=(cell/'server.log').read_text(encoding='utf-8',errors='replace')
            http=Counter(re.findall(r'"POST (/v1/chat/completions|/v1/contractkv/verify) HTTP/[^"\s]+" (\d{3})',log))
            assert http['/v1/chat/completions','200']==len(generated)
            assert http['/v1/contractkv/verify','200']==len(requests)
            assert sum(http.values())==len(generated)+len(requests),'Unexpected backend HTTP result retained'
            assert abs(summary['wall_s']-(summary['service_end_time']-summary['service_begin_time']))<1e-9
            assert all(summary['service_begin_time']<=r['record_monotonic_s']<=summary['service_end_time'] for r in rr if r['row_type'] in ['registration','reference_generation','business','verification_request','verification_response'])
            # The client's postmeasurement Native joins are excluded from the
            # service wall; original preparation, qualification and response
            # writes above must all precede the measured backend drain.
            assert read(cell/'measured_backend_drain_v1.json')['included_in_measured_service_clock']
            actual_new=sum(r['prompt_tokens']-r['prefix_hit_tokens'] for r in native)
            recorded_new=sum(summary['native_new_prefill_by_kind'].values());assert actual_new==recorded_new
            cells.append(dict(job=job['id'],business=sum(r['row_type']=='business' for r in rr),
                actual_generated_HTTP=len(generated),actual_verification_HTTP=len(requests),
                actual_Native_initial_requests=len(native),unaccounted_GPU_requests=0,
                actual_all_request_new_prefill_tokens=actual_new,all_online_records_inside_direct_wall=True,
                startup_model_loading_outside_measured_service_wall=True,
                semantic_rejection_HTTP_count=sum(not r['response'].get('certificate_issued') for r in responses)))
    result=dict(status='PASS',cells=cells,all_HTTP_and_initial_Native_requests_accounted=True,
        total_actual_generated_HTTP=sum(r['actual_generated_HTTP'] for r in cells),
        total_actual_verification_HTTP=sum(r['actual_verification_HTTP'] for r in cells),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cells'}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--phases',nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.phases,a.output)
