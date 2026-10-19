"""Independent raw-log accounting of bounded authorization repair controls."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score

STUDY=Path('results/tsc_authorization_task_repair_20261019')


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(line) for line in f if line.strip()]
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def csvout(p,rows):
    if not rows:return
    with p.open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def q(v,f):
    if not v:return None
    x=sorted(v);i=(len(x)-1)*f;a=math.floor(i);b=math.ceil(i)
    return x[a]+(x[b]-x[a])*(i-a)
def dist(v):
    v=list(v)
    return dict(n=len(v),mean=statistics.fmean(v) if v else None,P95=q(v,.95),P99=q(v,.99))
def idmatch(actual,requested):return actual==requested or actual.startswith(requested+'-')


def analyze(root,output):
    assert not output.exists();output.mkdir(parents=True)
    study=root/STUDY
    state=read(study/'execution_state_v2.json')
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==9
    assert sha(study/'freeze_v2.json')=='b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3'
    freeze=read(study/'freeze_v2.json')
    for row in freeze['files']:assert sha(root/row['path'])==row['sha256'],row['path']
    cases_by_model=read(study/'inputs_v1/cases_by_model_v1.json')
    model_names={'qwen3-8b':'Qwen3-8B','mistral-7b':'Mistral-7B-Instruct-v0.3','llama-3.1-8b':'Llama-3.1-8B-Instruct'}
    requests,paired,checks,qualifications,phases,cells,inputs=[],[],[],[],[],[],[]
    for relative in state['completed_cells']:
        cell=study/relative;completion=read(cell/'completion_v1.json')
        for row in completion['files']:assert sha(cell/row['path'])==row['sha256']
        rr=lines(cell/'responses.jsonl');trace=lines(cell/'backend_trace.jsonl')
        assert rr[-1]['event']=='repair_cell_complete' and rr[-1]['counts']['business']==92
        model=rr[0]['model'];name=model_names[model];repeat=int(cell.parent.name.rsplit('_r',1)[1])
        cdict={c['case_id']:c for c in cases_by_model[name]['real_cases']+[cases_by_model[name]['synthetic_case']]}
        b=[x for x in rr if x['event']=='business'];assert len(b)==92
        native_before=[x for x in trace if x['event']=='lookup_before']
        native_after=[x for x in trace if x['event']=='lookup_return']
        publications=[x for x in trace if x['event']=='verification_cache_blocks_return']
        local={};native={};last_end=None
        for row in b:
            response=row['response'];case=cdict[row['case_id']];synthetic=row['case_id']=='synthetic_authorized_cache_identity'
            hit=None;lookup=None
            if response['success']:
                expected=case['candidate_prompt_token_ids'] if row['compiled_route'] else case['raw_prompt_token_ids']
                assert response['prompt_token_ids']==expected
                before=[t for t in native_before if idmatch(t['request_id'],response['request_id'])]
                assert before,'Missing actual initial native lookup'
                lookup=min(before,key=lambda t:t['seq'])
                after=[t for t in native_after if t['request_id']==lookup['request_id'] and t['seq']>lookup['seq']]
                assert after
                returned=min(after,key=lambda t:t['seq'])
                hit=returned['hit_tokens']
                assert lookup['backend_cache_salt']==row['actual_wire_cache_salt']
                assert lookup['prompt_tokens']==len(expected)
                native[row['case_id'],row['condition']]=dict(before=lookup,after=returned,lookup_calls=len(before))
            if synthetic:
                text=response.get('output_text','').replace('<think>','').replace('</think>','').strip()
                score=float(response['success'] and text=='ACK')
            else:
                score=standard_score(case['dataset'],case['task'],response.get('output_text',''),case['answer'])[0] if response['success'] else 0.
            assert score==row['output_score']
            # API TTFT is directly recorded. The serial closed-loop readiness
            # observation below starts at the previous actual business end;
            # no invented scheduled arrival or first-request timestamp.
            ready=(response['first_time']-last_end)*1000 if response['success'] and last_end is not None else None
            if response.get('end_time') is not None:last_end=response['end_time']
            slo=bool(ready<=11700 and response['tpot_ms']<=435) if ready is not None else None
            if ready is not None:assert ready>=0
            rec=dict(cell=cell.parent.name,model=model,repeat=repeat,case_id=row['case_id'],source_group=row['source_group'],
                family=row['family'],condition=row['condition'],synthetic=synthetic,success=response['success'],
                compiled=row['compiled_route'],domain=row['trusted_authorization_domain'],epoch=row['active_epoch'],
                score=score,finish=response['finish_reason'],output_tokens=len(response['output_token_ids']),
                prompt_tokens=len(response['prompt_token_ids']) if response.get('prompt_token_ids') is not None else None,
                initial_native_hit_tokens=hit,logical_new_prefill_tokens=len(response['prompt_token_ids'])-hit if hit is not None else None,
                API_TTFT_ms=response['ttft_ms'],E2E_stream_ms=response['latency_ms'],TPOT_ms=response['tpot_ms'],
                serial_ready_after_previous_business_TTFT_ms=ready,serial_ready_SLO=slo,
                wire_salt_SHA256=hashlib.sha256(str(row['actual_wire_cache_salt']).encode()).hexdigest())
            requests.append(rec);local[row['case_id'],row['condition']]=row
        assert len(local)==92
        for cid,case in cdict.items():
            synthetic=cid=='synthetic_authorized_cache_identity'
            comparisons=[('legacy_raw_witness','legacy_raw_repeat'),('legacy_raw_witness','legacy_post_decision'),
                ('authorized_raw_witness','authorized_raw_repeat'),('authorized_raw_witness','authorized_post_decision'),
                ('authorized_raw_witness','authorized_same_group_second_principal'),
                ('legacy_raw_witness','authorized_raw_witness')]
            for first,second in comparisons:
                a,b0=local[cid,first],local[cid,second];x,y=a['response'],b0['response']
                available=x['success'] and y['success'];delta=b0['output_score']-a['output_score']
                paired.append(dict(cell=cell.parent.name,model=model,repeat=repeat,case_id=cid,source_group=case.get('source_group','synthetic'),
                    synthetic=synthetic,first=first,second=second,available=available,
                    same_prompt_IDs=x.get('prompt_token_ids')==y.get('prompt_token_ids') if available else None,
                    output_IDs_equal=x['output_token_ids']==y['output_token_ids'] if available else None,
                    finish_equal=x['finish_reason']==y['finish_reason'] if available else None,
                    first_score=a['output_score'],second_score=b0['output_score'],score_delta=delta,
                    score_up=delta>.03,score_down=delta<-.03,compiled_second=b0['compiled_route']))
            for first,second,property_name,zero_expected in [
                ('legacy_raw_witness','legacy_cross_domain_fallback','legacy_cross_domain_reuse',False),
                ('legacy_raw_witness','legacy_stale_certificate_fallback','legacy_stale_binding_reuse',False),
                ('authorized_raw_witness','authorized_raw_repeat','authorized_A1_own_reuse',False),
                ('authorized_post_decision','authorized_same_group_second_principal','authorized_A1_group_reuse',False),
                ('authorized_raw_witness','authorized_cross_domain_fallback','authorized_cross_domain_separation',True),
                ('authorized_raw_witness','authorized_stale_certificate_fallback','authorized_new_epoch_separation',True),
                ('authorized_cross_domain_fallback','authorized_cross_domain_own_repeat','authorized_B_own_reuse',False),
                ('authorized_stale_certificate_fallback','authorized_new_epoch_repeat','authorized_A2_own_reuse',False)]:
                x,y=native.get((cid,first)),native.get((cid,second))
                a,b0=local[cid,first],local[cid,second]
                available=x is not None and y is not None
                same_ids=a['response'].get('prompt_token_ids')==b0['response'].get('prompt_token_ids') if available else None
                if available:
                    assert same_ids
                    left,right=x['before']['backend_hashes'],y['before']['backend_hashes']
                    assert left and right
                    disjoint=set(left).isdisjoint(right)
                    hits=y['after']['hit_tokens']
                    correct=(disjoint and hits==0) if zero_expected else (left==right and hits>0)
                    evicted={t['old_hash'] for t in trace if t['event']=='native_evict_return' and t.get('removed') and
                             x['before']['seq']<t['seq']<y['before']['seq']}
                    removed_left_blocks=len(set(left)&evicted)
                else:disjoint=hits=correct=removed_left_blocks=None
                checks.append(dict(cell=cell.parent.name,model=model,repeat=repeat,case_id=cid,synthetic=synthetic,
                    property=property_name,available=available,same_actual_prompt_IDs=same_ids,
                    all_block_hashes_disjoint=disjoint,second_actual_native_hits=hits,
                    expected_observation_supported=correct,first_prompt_blocks_evicted_between_lookups=removed_left_blocks,
                    interpretation='Primary namespace evidence; physical block IDs may be recycled after eviction.'))
        qrows=[r for r in rr if r['event']=='qualification'];assert len(qrows)==15
        actual_ids=[]
        for row in qrows:
            result=row['result'];detail=[d for d in rr if d['event']=='qualification_detail' and
                d['case_id']==row['case_id'] and d['phase']==row['phase'] and d.get('row_type')=='verification_request']
            assert len(detail)<=1
            actual_ids.extend(d['request_id'] for d in detail)
            pubs=[t for t in publications if detail and idmatch(t['request_id'],detail[0]['request_id'])]
            commit=int(result.get('committed_tokens',0));accepted=bool(result.get('certificate_issued'))
            uncertain=result.get('verification_status')=='indeterminate_request_failure'
            if accepted:
                assert commit>0 and commit%16==0 and commit<=row['plan']['stable_prefix_end_token']
                assert len(pubs)==1 and pubs[0]['requested_tokens']==commit
            elif not uncertain:assert commit==0 and not pubs,'Rejected candidate published new shared blocks'
            qualifications.append(dict(cell=cell.parent.name,model=model,repeat=repeat,case_id=row['case_id'],phase=row['phase'],
                inherited_level=row['plan']['level'],accepted=accepted,RPCs=len(result.get('attempts',[])),indeterminate=uncertain,
                reason=result.get('failure_reason',''),committed_tokens=commit,publication_events=len(pubs),
                actual_published_tokens=sum(p['requested_tokens'] for p in pubs),
                full_controller_ms=row['full_qualification_including_guard_ms'],output_contract=row['output_contract']))
        assert len(actual_ids)==len(set(actual_ids))
        denials=[r for r in rr if r['event']=='stale_identity_denied_before_backend']
        assert len(denials)==7 and all(not r['GPU_or_business_request_dispatched'] and not r['raw_fallback_dispatched'] for r in denials)
        phase_rows=[r for r in rr if r['event']=='phase_complete'];assert len(phase_rows)==14
        for row in phase_rows:
            phases.append(dict(cell=cell.parent.name,model=model,repeat=repeat,case_id=row['case_id'],
                phase=row['phase'],business=row['business'],full_wall_s=row['full_wall_s'],
                boundary='Different phase work counts; not an equal-workload speedup comparison.'))
        mine=[r for r in requests if r['cell']==cell.parent.name]
        ready=[r for r in mine if r['serial_ready_SLO'] is not None]
        wall=rr[-1]['full_serial_workflow_wall_s']
        cells.append(dict(cell=cell.parent.name,model=model,repeat=repeat,full_workflow_wall_s=wall,business=92,
            SLO_available_serial_business=len(ready),SLO_unavailable_first_or_failed_business=92-len(ready),
            serial_SLO_compliant=sum(r['serial_ready_SLO'] for r in ready),
            serial_SLO_compliant_per_full_workflow_wall=sum(r['serial_ready_SLO'] for r in ready)/wall,
            API_TTFT=dist(r['API_TTFT_ms'] for r in mine if r['success']),
            serial_ready_TTFT=dist(r['serial_ready_after_previous_business_TTFT_ms'] for r in ready),
            response_E2E=dist(r['E2E_stream_ms'] for r in mine if r['success']),
            TPOT=dist(r['TPOT_ms'] for r in mine if r['success']),
            actual_pool_blocks=sorted({t['pool_blocks'] for t in native_before}),
            native_eviction_events=sum(t['event']=='native_evict_return' and t.get('removed',False) for t in trace),
            stale_request_identity_denied=len(denials),new_GPU_requests_from_analysis=0))
        inputs.extend(dict(path=(cell/f['path']).relative_to(root).as_posix(),sha256=f['sha256']) for f in completion['files'])
    assert len(requests)==828 and len(qualifications)==135 and len(checks)==504 and len(paired)==378
    assertion_rows=[r for r in checks if r['property'].startswith('authorized_')]
    compiled=[r for r in paired if r['compiled_second'] and r['second'] in {'authorized_post_decision','authorized_same_group_second_principal'}]
    violation=[r for r in assertion_rows if r['available'] and not r['expected_observation_supported']]
    behavioral_changes=[r for r in compiled if r['available'] and (not r['output_IDs_equal'] or not r['finish_equal'])]
    summary=dict(status='COMPLETE_DATA_VALIDATED',formal_cells=9,business_requests=828,new_GPU_requests=0,
        primary_namespace_check_counts={k:dict(total=len(v),available=sum(x['available'] for x in v),
            supported=sum(x['expected_observation_supported'] is True for x in v),
            synthetic_supported=sum(x['synthetic'] and x['expected_observation_supported'] is True for x in v))
            for k,v in ((key,[x for x in checks if x['property']==key]) for key in sorted({x['property'] for x in checks}))},
        authorization_or_reuse_observation_violations=violation,
        authorized_compiled_vs_own_witness_pairs=len(compiled),authorized_compiled_output_or_finish_changes=behavioral_changes,
        actual_verification_RPCs=sum(r['RPCs'] for r in qualifications),accepted_qualifications=sum(r['accepted'] for r in qualifications),
        rejected_or_abstained_qualifications=sum(not r['accepted'] for r in qualifications),
        rejected_qualification_added_published_tokens=sum(r['actual_published_tokens'] for r in qualifications if not r['accepted']),
        stale_request_identities_denied=63,all_business_scores_independently_recomputed=True,
        no_claim_of_absolute_correctness_or_full_tenant_confidentiality=True,
        serial_clock_definition='Readiness for each request after the first is the previous real business completion. First request unavailable; no scheduled arrivals reconstructed. API TTFT is reported separately. No open-arrival/capacity or fair unequal-phase speedup claim.',
        cells=cells,inputs=inputs,analysis_source_sha256=sha(Path(__file__)))
    for filename,rows in [('requests_v1.csv',requests),('paired_quality_v1.csv',paired),('namespace_checks_v1.csv',checks),
                          ('qualifications_v1.csv',qualifications),('phases_v1.csv',phases)]:csvout(output/filename,rows)
    write(output/'summary_v1.json',summary)
    print(json.dumps({k:summary[k] for k in ['status','formal_cells','business_requests','actual_verification_RPCs',
        'accepted_qualifications','rejected_qualification_added_published_tokens','stale_request_identities_denied']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.root.resolve(),a.output.resolve())
