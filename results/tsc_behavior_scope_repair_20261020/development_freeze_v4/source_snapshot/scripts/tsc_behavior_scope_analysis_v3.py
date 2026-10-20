"""Frozen descriptive pairing, cost coverage and prospective development gate."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score

STUDY=Path('results/tsc_behavior_scope_repair_20261020')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def main(root,phase,output):
    study=root/STUDY;plan=read(study/(phase+'_jobs_v3.json'));state=read(study/(phase+'_execution_state_v3.json'))
    assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS' and read(study/(phase+'_exit_v3.json'))['returncode']==0
    cells=[];indexed={};registered={};physical=Counter();physical_by_model=defaultdict(Counter);extra_requests=0
    freeze=read(study/(phase+'_freeze_v3/freeze.json'))
    for r in freeze['files']:assert sha(root/r['path'])==r['sha256'],r['path']
    samples={s['revision_source_group']:s for s in lines(study/('inputs_'+plan['input_set']+'_v1/sessions_v1.jsonl'))}
    for job in plan['jobs']:
        cell=study/'runs'/job['id']/'attempt1';summary=read(cell/'summary_v1.json')
        assert read(cell/'completion_v1.json')['summary_sha256']==sha(cell/'summary_v1.json')
        assert summary['raw_file_sha256']==sha(cell/'responses.jsonl') and summary['offered']==job['expected_business']==summary['successful']
        assert read(cell/'measured_backend_drain_v1.json')['backend_request_counters_drained']
        rr=lines(cell/'responses.jsonl');byrequest={r['result']['request_id']:r for r in rr if r['row_type'] in ['business','reference_generation']}
        native={r['request_id']:r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        requests=[r for r in rr if r['row_type']=='verification_request']
        responses=[r for r in rr if r['row_type']=='verification_response']
        assert len(requests)==len(responses)==summary['actual_verification_RPCs']
        for r in responses:
            cert=r['response'];assert cert.get('certificate_issued') or not cert.get('committed_tokens',0)
        for r in rr:
            if r['row_type']=='registration':
                key=(job['model'],job['repeat'],job['policy'],r['source_group'],r['tenant'],r['turn']);registered[key]=r
                if job['policy']=='Strict-exact' and r['certificate']['certificate_issued']:
                    assert r['reference_kind']=='RAW_QUERY' and r['behavior']['evidence']['reference_kind']=='RAW_QUERY'
                    witness=next(x for x in rr if x['row_type']=='business' and x['source_group']==r['source_group'] and x['tenant']==r['tenant'] and x['turn']==r['turn'] and x['access']==0)
                    candidate=next(x for x in rr if x['row_type']=='reference_generation' and x['source_group']==r['source_group'] and x.get('tenant')==r['tenant'] and x.get('turn')==r['turn'])
                    assert witness['result']['output_token_ids']==candidate['result']['output_token_ids']
                    assert witness['result']['finish_reason']==candidate['result']['finish_reason']=='stop'
                    assert r['behavior']['evidence']['raw_prompt_sha256']==digest(witness['result']['prompt_token_ids'])
                    verification=next(x for x in requests if x['reference_prompt_ids_sha256']==witness['result']['prompt_ids_sha256'])
                    assert verification['payload']['attestation_mode']=='actual-business-raw-answer-eos-path'
                    assert verification['payload']['prompt_token_ids']==r['plan']['prompt_token_ids']+witness['result']['output_token_ids']
            elif r['row_type']=='business':
                result=r['result'];assert result['success'] and digest(result['prompt_token_ids'])==result['prompt_ids_sha256']
                sample=samples[r['source_group']];score,_,_=standard_score(sample['dataset'],sample['task'],result['output_text'],sample.get('answer',''))
                assert score==r['task_score'] and not r['scope_binding_errors']
                assert abs(r['ready_ttft_ms']-(result['first_time']-r['planned_ready_time'])*1000)<1e-6
                key=(job['model'],job['repeat'],job['policy'],r['source_group'],r['tenant'],r['turn'],r['access']);assert key not in indexed;indexed[key]=r
                event=native[result['request_id']];assert event['prompt_tokens']==len(result['prompt_token_ids'])
                if r['compiled']:
                    cert=next(x['certificate'] for x in rr if x['row_type']=='registration' and x['source_group']==r['source_group'] and
                              (job['policy']=='Deployment' or (x['tenant'],x['turn'])==(r['tenant'],r['turn'])))
                    hit_kind=job['policy']+':'+('full' if event['prefix_hit_tokens']>=cert['committed_tokens'] else 'partial' if event['prefix_hit_tokens'] else 'zero')
                    physical[hit_kind]+=1;physical_by_model[job['model']][hit_kind]+=1
            elif r['row_type']=='admission_negative_controls':
                assert r['changed_actual_suffix_errors'] and r['authorized_but_missing_Raw_evidence_errors']
        for result in byrequest.values():
            event=native[result['result']['request_id']];assert event['prompt_tokens']==len(result['result']['prompt_token_ids'])
        extra_requests+=sum(r['row_type']=='reference_generation' for r in rr)+len(requests)
        cells.append(summary)
    pairs=[];projections=[]
    for key,r in indexed.items():
        model,repeat,policy,source,tenant,turn,access=key
        if policy=='Raw-authorized':continue
        raw=indexed[model,repeat,'Raw-authorized',source,tenant,turn,access]
        same=(raw['result']['output_token_ids'],raw['result']['finish_reason'])==(r['result']['output_token_ids'],r['result']['finish_reason'])
        delta=r['task_score']-raw['task_score']
        pairs.append(dict(model=model,repeat=repeat,policy=policy,source=source,family=r['family'],tenant=tenant,turn=turn,access=access,
                          compiled=r['compiled'],IDs_and_EOS_equal=same,Raw_score=raw['task_score'],score=r['task_score'],delta=delta,
                          down=delta<-.03,up=delta>.03))
    model_results={}
    for model in plan['models']:
        pp=[r for r in pairs if r['model']==model and r['policy']=='Strict-exact'];cc=[r for r in pp if r['compiled']]
        for key,reg in registered.items():
            mm,rep,policy,source,tenant,turn=key
            if mm!=model or policy!='Strict-exact' or not reg['certificate']['certificate_issued']:continue
            raw=[r for k,r in indexed.items() if k[:4]==(model,rep,'Raw-authorized',source) and k[4:6]==(tenant,turn) and k[6]>0]
            compiled=[r for k,r in indexed.items() if k[:4]==(model,rep,policy,source) and k[4:6]==(tenant,turn) and k[6]>0 and r['compiled']]
            gain=statistics.mean(r['result']['latency_ms'] for r in raw)-statistics.mean(r['result']['latency_ms'] for r in compiled)
            rawfirst=indexed[model,rep,'Raw-authorized',source,tenant,turn,0]['result']['latency_ms']
            strictfirst=indexed[model,rep,policy,source,tenant,turn,0]['result']['latency_ms']
            cost=reg['full_controller_ms']+max(0,strictfirst-rawfirst)
            projections.append(dict(model=model,repeat=rep,source=source,tenant=tenant,turn=turn,
                mean_actual_business_latency_saving_ms=gain,measured_complete_qualification_ms=cost,
                eight_access_projected_net_ms=7*gain-cost,projection_not_independent_performance_result=True))
        positive=any(r['model']==model and r['eight_access_projected_net_ms']>0 for r in projections)
        hits=physical_by_model[model]['Strict-exact:full']>0
        model_results[model]=dict(compiled_pairs=len(cc),compiled_ID_or_EOS_changes=sum(not r['IDs_and_EOS_equal'] for r in cc),
            compiled_score_drops=sum(r['down'] for r in cc),allroute_score_drops=sum(r['down'] for r in pp),
            dev_eight_access_cost_space=positive,
            may_enter_frozen_validation=bool(cc) and not any(not r['IDs_and_EOS_equal'] for r in cc) and positive and hits)
    result=dict(status='PASS',phase=phase,cells=cells,models=model_results,pairs=pairs,scope_cost_projections=projections,
                physical_hits=dict(physical),extra_GPU_requests=extra_requests,source_sha256=sha(Path(__file__)),
                boundary='Exact-repeat workload; pair/score variation retained; projections are development screens, not formal measured effects.')
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','phase':phase,'cells':len(cells),'models':model_results,'physical':dict(physical)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--phase',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.phase,a.output)
