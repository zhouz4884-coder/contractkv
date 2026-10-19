"""Actual same-stack serving, paired task quality, and cluster sensitivity."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase20a_official_quality import standard_score

STUDY=Path('results/tsc_template_task_serving_20261019')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
def close(a,b):return abs(a-b)<1e-5

def main(root,output):
    study=root/STUDY;protocol=read(study/'formal_protocol_v1.json');state=read(study/'formal_execution_state_v1.json')
    assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS' and len(state['completed_cells'])==len(protocol['jobs'])
    frozen=study/'formal_freeze_v1';freeze=read(frozen/'freeze.json')
    for r in freeze['files']:assert sha(root/r['path'])==sha(frozen/'source_snapshot'/r['path'])==r['sha256'],r['path']
    samples={r['revision_source_group']:r for r in lines(study/'inputs_validation_v2/sessions_v2.jsonl')}
    shapes={(r['model'],r['source_group'],r['tenant'],r['turn'],r['level']):r for r in lines(study/'inputs_validation_v2/CPU_shapes_v2.jsonl')}
    cells=[];compact={};per_source=[];registrations=[]
    for job in protocol['jobs']:
        relative='runs/'+job['id']+'/attempt1';assert relative in state['completed_cells'];cell=study/relative
        summary=read(cell/'summary_v1.json');assert read(cell/'completion_v1.json')['summary_sha256']==sha(cell/'summary_v1.json')
        assert summary['raw_file_sha256']==sha(cell/'responses.jsonl') and summary['job']==job
        records=lines(cell/'responses.jsonl');business=[r for r in records if r['row_type']=='business'];assert len(business)==384
        byseq={r['sequence']:r for r in business};assert len(byseq)==384
        trace=read(study/job['arrivals']);assert summary['arrivals_sha256']==sha(study/job['arrivals'])
        actual={r['request_id']:r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        salts={};projected=[]
        for frame in trace['requests']:
            r=byseq[frame['sequence']];v=r['result'];sample=samples[r['source_group']]
            assert (r['source_group'],r['tenant'],r['turn'])==(frame['source_group'],frame['tenant'],frame['turn'])
            assert r['planned_ready_time']==summary['service_begin_time']+frame['ready_offset_s'] and r['planned_ready_offset_s']==frame['ready_offset_s']
            if v['success']:
                assert close(r['ready_ttft_ms'],(v['first_time']-r['planned_ready_time'])*1000)
                assert close(r['ready_latency_ms'],(v['end_time']-r['planned_ready_time'])*1000)
                shape=shapes[job['model'],r['source_group'],r['tenant'],r['turn'],r['level']]
                assert v['prompt_ids_sha256']==shape['prompt_ids_sha256'] and len(v['prompt_token_ids'])==shape['prompt_tokens']
                assert v['completion_tokens']==len(v['output_token_ids']) and v['end_time']<=summary['service_end_time']
                assert standard_score(sample['dataset'],sample['task'],v['output_text'],sample.get('answer',''))[0]==r['task_score']
                event=actual[v['request_id']];assert event['prompt_tokens']==len(v['prompt_token_ids'])
                hit=event['prefix_hit_tokens'];new=event['prompt_tokens']-hit
            else:hit,new=None,None
            salt=v['actual_wire_cache_salt'];assert salt.startswith('ckv-auth-v1:')
            if r['source_group'] in salts:assert salts[r['source_group']]==salt
            salts[r['source_group']]=salt
            assert not r['scope_binding_errors']
            slo=bool(v['success'] and r['ready_ttft_ms']<=job['SLO']['TTFT_ms'])
            projected.append(dict(model=job['model'],load=job['load'],repeat=job['repeat'],policy=job['policy'],sequence=r['sequence'],
                source=r['source_group'],family=r['family'],tenant=r['tenant'],turn=r['turn'],compiled=r['compiled'],success=v['success'],
                IDs=v['output_token_ids'],finish=v['finish_reason'],score=r['task_score'],ready_TTFT_ms=r['ready_ttft_ms'],ready_e2e_ms=r['ready_latency_ms'],
                backend_TTFT_ms=v['ttft_ms'],prompt_sha=v['prompt_ids_sha256'],output_tokens=len(v['output_token_ids']),
                SLO=slo,native_hit=hit,new_prefill=new))
        assert len(set(salts.values()))==6
        decisions=[r for r in records if r['row_type']=='registration'];requests=[r for r in records if r['row_type']=='verification_request'];responses=[r for r in records if r['row_type']=='verification_response']
        assert {r['request_id'] for r in requests}=={r['request_id'] for r in responses}
        server_rpc=len(re.findall(r'"POST /v1/contractkv/verify HTTP/1\.[01]" 200',(cell/'server.log').read_text(encoding='utf-8',errors='replace')))
        assert server_rpc==len(requests)==summary['actual_verification_RPCs']
        allowed=sum(s['revision_family'] in job['eligible_families'] for s in samples.values())
        expected=0 if job['policy']=='Raw-authorized' else allowed*(8 if job['policy']=='Session-qualified' else 1)
        assert len(decisions)==summary['certificate_objects']==expected
        reference_rows=[r for r in records if r['row_type']=='reference_generation'];assert len(reference_rows)==len(decisions)
        for r in reference_rows:assert r['result']['actual_wire_cache_salt']!=salts[r['source_group']]
        for r in requests:assert actual[r['request_id']]['prompt_tokens']==len(r['payload']['prompt_token_ids'])
        byobject={r['object_id']:r for r in decisions}
        for d in decisions:
            c=d['certificate'];commit=int(c.get('committed_tokens',0));plan=d['plan']
            canonical=shapes[job['model'],d['source_group'],0,0,'L3'];assert plan['prompt_ids_sha256']==canonical['prompt_ids_sha256']
            if c['certificate_issued']:
                assert commit>0 and commit%16==0 and commit<=plan['stable_prefix_end_token']
                assert c['minimum_margin_guard_passed'] and c['candidate_margin_min']>=.125 and c['terminal_stop_margin']>=.125 and c['raw_margin_min']>=.0625
            else:assert commit==0
            registrations.append(dict(model=job['model'],load=job['load'],repeat=job['repeat'],policy=job['policy'],source=d['source_group'],
                object_id=d['object_id'],issued=bool(c['certificate_issued']),RPCs=len(c['attempts']),complete_controller_ms=d['complete_controller_ms'],
                committed_tokens=commit,canonical_prompt_sha=plan['prompt_ids_sha256'],failure=c['failure_reason']))
        hit_classes=Counter()
        for raw,p in zip(sorted(business,key=lambda r:r['sequence']),projected):
            assert raw['sequence']==p['sequence']
            if p['compiled']:
                c=byobject[raw['certificate_object']]['certificate'];assert c['certificate_issued']
                hit_classes['full' if p['native_hit']>=c['committed_tokens'] else 'partial' if p['native_hit'] else 'zero']+=1
        count=sum(r['SLO'] for r in projected);assert count==summary['SLO_compliant']
        assert count/summary['wall_s']==summary['absolute_SLO_goodput']
        assert sum(r['new_prefill'] or 0 for r in projected)==summary['business_new_prefill_tokens']
        cells.append(dict(cell=job['id'],model=job['model'],load=job['load'],repeat=job['repeat'],policy=job['policy'],lane=job['lane'],
            offered=384,success=sum(r['success'] for r in projected),wall_s=summary['wall_s'],SLO_count=count,absolute_goodput=count/summary['wall_s'],
            mean_ready_TTFT_ms=summary['ready_TTFT_ms']['mean'],p95_ready_TTFT_ms=summary['ready_TTFT_ms']['p95'],p99_ready_TTFT_ms=summary['ready_TTFT_ms']['p99'],
            registration_objects=len(decisions),RPCs=len(requests),registration_controller_work_ms=summary['registration_controller_work_ms'],
            registration_barrier_ms=summary['registration_barrier_from_epoch_ms'],compiled=sum(r['compiled'] for r in projected),
            business_new_prefill=summary['business_new_prefill_tokens'],canary_extra_new_prefill=summary['reference_extra_new_prefill_tokens'],
            verification_extra_new_prefill=summary['verification_extra_new_prefill_tokens'],compiled_native_hits=dict(hit_classes)))
        compact[job['model'],job['load'],job['repeat'],job['policy']]=projected
        for source in samples:
            group=[r for r in projected if r['source']==source];assert len(group)==64
            per_source.append(dict(model=job['model'],load=job['load'],repeat=job['repeat'],policy=job['policy'],source=source,family=samples[source]['revision_family'],
                offered=64,SLO=sum(r['SLO'] for r in group),compiled=sum(r['compiled'] for r in group),score_mean=statistics.fmean(r['score'] for r in group),
                mean_ready_TTFT_ms=(statistics.fmean(r['ready_TTFT_ms'] for r in group if r['success']) if any(r['success'] for r in group) else None),native_new_prefill=sum(r['new_prefill'] or 0 for r in group)))
    pairs=[]
    for (model,load,repeat,policy),rr in compact.items():
        if policy=='Raw-authorized':continue
        baseline={r['sequence']:r for r in compact[model,load,repeat,'Raw-authorized']}
        for r in rr:
            b=baseline[r['sequence']];delta=r['score']-b['score'];assert (r['source'],r['tenant'],r['turn'])==(b['source'],b['tenant'],b['turn'])
            if not r['compiled'] and r['success'] and b['success']:assert r['prompt_sha']==b['prompt_sha']
            pairs.append(dict(model=model,load=load,repeat=repeat,policy=policy,source=r['source'],family=r['family'],tenant=r['tenant'],turn=r['turn'],
                compiled=r['compiled'],Raw_positive_score=b['score']>0,Raw_score=b['score'],score=r['score'],delta=delta,score_up=delta>.03,score_down=delta<-.03,
                IDs_and_finish_equal=(r['IDs'],r['finish'])==(b['IDs'],b['finish'])))
    source_SLO={(r['model'],r['load'],r['repeat'],r['policy'],r['source']):r['SLO'] for r in per_source}
    aggregates=[];comparisons=[];rng=random.Random(2026101999)
    for model,load in sorted({(r['model'],r['load']) for r in cells}):
        for policy in ['Raw-authorized','Session-qualified','Template-qualified']:
            part=[r for r in cells if (r['model'],r['load'],r['policy'])==(model,load,policy)];assert len(part)==3
            aggregates.append(dict(model=model,load=load,policy=policy,repeats=3,total_SLO=sum(r['SLO_count'] for r in part),total_requests=1152,
                absolute_goodput=sum(r['SLO_count'] for r in part)/sum(r['wall_s'] for r in part),
                mean_ready_TTFT_ms=statistics.fmean(r['mean_ready_TTFT_ms'] for r in part),p99_ready_TTFT_repeat_range=[min(r['p99_ready_TTFT_ms'] for r in part),max(r['p99_ready_TTFT_ms'] for r in part)],
                RPCs=sum(r['RPCs'] for r in part),registration_objects=sum(r['registration_objects'] for r in part),
                controller_ms_per_business=sum(r['registration_controller_work_ms'] for r in part)/1152,
                compiled=sum(r['compiled'] for r in part),business_new_prefill=sum(r['business_new_prefill'] for r in part),
                canary_plus_verification_new_prefill=sum(r['canary_extra_new_prefill']+r['verification_extra_new_prefill'] for r in part)))
        for candidate,reference in [('Session-qualified','Raw-authorized'),('Template-qualified','Raw-authorized'),('Template-qualified','Session-qualified')]:
            a={r['repeat']:r for r in cells if (r['model'],r['load'],r['policy'])==(model,load,candidate)}
            b={r['repeat']:r for r in cells if (r['model'],r['load'],r['policy'])==(model,load,reference)}
            assert all(a[k]['lane']==b[k]['lane'] for k in (1,2,3))
            def delta(repeats,source_draw=None):
                def count(policy,rep):
                    if source_draw is None:return (a if policy==candidate else b)[rep]['SLO_count']
                    return sum(source_SLO[model,load,rep,policy,s] for s in source_draw)
                return sum(count(candidate,k) for k in repeats)/sum(a[k]['wall_s'] for k in repeats)-sum(count(reference,k) for k in repeats)/sum(b[k]['wall_s'] for k in repeats)
            rep_boot=[delta([rng.choice([1,2,3]) for _ in range(3)]) for _ in range(5000)]
            source_boot=[delta([1,2,3],[rng.choice(list(samples)) for _ in range(6)]) for _ in range(5000)]
            loo=[delta([1,2,3],[s for s in samples if s!=excluded]) for excluded in samples]
            comparisons.append(dict(model=model,load=load,candidate=candidate,reference=reference,absolute_goodput_delta=delta([1,2,3]),
                paired_three_process_bootstrap_CI95=[percentile(rep_boot,.025),percentile(rep_boot,.975)],
                conditional_source_sensitivity_CI95=[percentile(source_boot,.025),percentile(source_boot,.975)],leave_one_source_delta_range=[min(loo),max(loo)],
                source_sensitivity_holds_observed_wall_fixed_not_counterfactual_workload=True))
    summary=dict(status='FORMAL_INDEPENDENT_ACCOUNTING_COMPLETE',actual_cells=len(cells),business=len(cells)*384,paired_future_business=len(pairs),
        aggregates=aggregates,comparisons=comparisons,compiled_pairs=sum(r['compiled'] for r in pairs),
        compiled_ID_or_finish_changes=sum(r['compiled'] and not r['IDs_and_finish_equal'] for r in pairs),
        compiled_score_down=sum(r['compiled'] and r['score_down'] for r in pairs),all_route_score_down=sum(r['score_down'] for r in pairs),
        all_route_score_up=sum(r['score_up'] for r in pairs),unique_source_clusters=6,qualified_task_families=['HotpotQA'],all_Repo_Raw_fallback=True,
        planned_time_clock_and_actual_prompt_native_RPC_checks_pass=True,new_GPU_requests=0,source_sha256=sha(Path(__file__)),
        boundary='Controlled marked-Poisson locality and registered repeated questions, zero slack. Deployment self-path attestation, independently measured Raw pairing. Six source clusters and three processes; repeated tenant requests are not independent safety trials. No universal quality or capacity claim.')
    assert not output.exists();output.mkdir(parents=True)
    for name,rr in [('cells',cells),('sources',per_source),('registrations',registrations),('paired_quality',pairs)]:
        with (output/(name+'_v1.csv')).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    write(output/'summary_v1.json',summary);print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
