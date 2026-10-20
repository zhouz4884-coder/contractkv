"""Recompute Raw-only rate/SLO inputs from actual transport/engine records."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase20a_official_quality import standard_score

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(root,output):
    study=root/'results/tsc_template_task_serving_20261019';state=read(study/'calibration_execution_state_v1.json')
    assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS'
    protocol=read(study/'calibration_protocol_v1.json');samples={r['revision_source_group']:r for r in lines(study/'inputs_development_v2/sessions_v2.jsonl')}
    freeze=read(study/'calibration_freeze_v1/freeze.json')
    for row in freeze['files']:assert sha(root/row['path'])==sha(study/'calibration_freeze_v1/source_snapshot'/row['path'])==row['sha256']
    result=[]
    for job in protocol['jobs']:
        relative='runs/'+job['id']+'/attempt1';assert relative in state['completed_cells'];cell=study/relative
        s=read(cell/'summary_v1.json');complete=read(cell/'completion_v1.json');assert complete['summary_sha256']==sha(cell/'summary_v1.json')
        rr=lines(cell/'responses.jsonl');assert sha(cell/'responses.jsonl')==s['raw_file_sha256']
        business=[r for r in rr if r['row_type']=='business'];assert len(business)==80
        assert not [r for r in rr if r['row_type'] in {'reference_generation','verification_request','registration'}]
        native={r['request_id']:r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        joined={r['sequence']:r for r in rr if r['row_type']=='business_native'};assert len(joined)==80
        frames={r['sequence']:r for r in read(study/job['arrivals'])['requests']}
        shapes={(r['source_group'],r['tenant'],r['turn'],r['level']):r for r in lines(study/'inputs_development_v2/CPU_shapes_v2.jsonl') if r['model']==job['model']}
        salts={}
        for row in business:
            frame=frames[row['sequence']];response=row['result'];assert response['success'] and not row['compiled'] and row['level']=='L0'
            assert row['source_group']==frame['source_group'] and row['tenant']==frame['tenant'] and row['turn']==frame['turn']
            assert row['planned_ready_time']==s['service_begin_time']+frame['ready_offset_s']
            assert abs(row['ready_ttft_ms']-(response['first_time']-row['planned_ready_time'])*1000)<1e-5
            assert abs(row['ready_latency_ms']-(response['end_time']-row['planned_ready_time'])*1000)<1e-5
            assert row['controller_start_monotonic_s']<=response['first_time']-response['ttft_ms']/1000+1e-8
            shape=shapes[row['source_group'],row['tenant'],row['turn'],'L0']
            assert response['prompt_ids_sha256']==shape['prompt_ids_sha256'] and len(response['prompt_token_ids'])==shape['prompt_tokens']
            sample=samples[row['source_group']];score=standard_score(sample['dataset'],sample['task'],response['output_text'],sample.get('answer',''))[0]
            assert score==row['task_score']
            salt=response['actual_wire_cache_salt'];assert salt.startswith('ckv-auth-v1:')
            if row['source_group'] in salts:assert salts[row['source_group']]==salt
            salts[row['source_group']]=salt
            event=native[response['request_id']];n=joined[row['sequence']]
            assert event['prompt_tokens']==len(response['prompt_token_ids']) and n['prefix_hit_tokens']==event['prefix_hit_tokens']
            assert n['new_prefill_tokens']==event['prompt_tokens']-event['prefix_hit_tokens']
            assert response['end_time']<=s['service_end_time']
        assert len(set(salts.values()))==4
        for key,field in [('backend_TTFT_ms','ttft_ms'),('backend_e2e_ms','latency_ms')]:
            values=[r['result'][field] for r in business]
            assert s[key]==dict(mean=sum(values)/80,p95=percentile(values,.95),p99=percentile(values,.99))
        assert s['successful']==s['offered']==80 and s['actual_verification_RPCs']==0 and s['business_native_unavailable']==0
        assert s['wall_s']==s['service_end_time']-s['service_begin_time']
        assert sum(r['new_prefill_tokens'] for r in joined.values())==s['business_new_prefill_tokens']
        result.append(dict(model=job['model'],cell=relative,successful=80,Raw_rate=80/s['wall_s'],wall_s=s['wall_s'],
            backend_TTFT_ms=s['backend_TTFT_ms'],backend_e2e_ms=s['backend_e2e_ms'],all_actual_prompt_IDs_and_native_observations_checked=80,
            raw_sha256=sha(cell/'responses.jsonl'),summary_sha256=sha(cell/'summary_v1.json')))
    assert not output.exists()
    output.write_text(json.dumps(dict(status='PASS',results=result,new_GPU_requests=0,actual_business=80*len(result),
        source_sha256=sha(Path(__file__)),no_Contract_outcomes_used=True),indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
