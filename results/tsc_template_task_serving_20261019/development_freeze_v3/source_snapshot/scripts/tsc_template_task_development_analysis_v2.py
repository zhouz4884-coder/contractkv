"""Independent actual-engine development audit and preregistered go/no-go."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score

STUDY=Path('results/tsc_template_task_serving_20261019')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,r):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def main(root,model,output):
    study=root/STUDY;freeze=read(study/'development_freeze_v3/freeze.json')
    for r in freeze['files']:
        assert sha(root/r['path'])==sha(study/'development_freeze_v3/source_snapshot'/r['path'])==r['sha256'],r['path']
    state=read(study/'development_execution_state_v3.json');matches=[p for p in state['completed_cells'] if p.startswith(f'cells/{model}_r1/')]
    assert len(matches)==1;relative=matches[0]
    cell=study/relative
    for r in read(cell/'nested_completion_inventory_v1.json')['files']:assert sha(cell/r['path'])==r['sha256'],r['path']
    data=lines(cell/'responses.jsonl');assert data[-1]['event']=='template_task_development_complete'
    samples={r['revision_source_group']:r for r in lines(study/'inputs_development_v2/sessions_v2.jsonl')}
    shapes={(r['source_group'],r['tenant'],r['turn'],r['level']):r for r in lines(study/'inputs_development_v2/CPU_shapes_v2.jsonl') if r['model']==model}
    before,after,pubs={},{},[]
    with (cell/'backend_trace.jsonl').open(encoding='utf-8') as f:
        for s in f:
            r=json.loads(s)
            if r['event']=='lookup_before':before.setdefault(r['request_id'],r)
            elif r['event']=='lookup_return' and r['request_id'] in before:after.setdefault(r['request_id'],r)
            elif r['event']=='verification_cache_blocks_return':pubs.append(r)
    native={r['request_id']:r for r in lines(cell/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
    observed_native=[]
    def actual(response,source,kind,tenant=None,turn=None,level=None):
        rid=response['request_id'];found=[r for k,r in before.items() if k==rid or k.startswith(rid+'-')];assert found,rid
        b=min(found,key=lambda r:r['seq']);a=after[b['request_id']]
        assert b['backend_cache_salt']==response['actual_wire_cache_salt'] and b['backend_cache_salt'].startswith('ckv-auth-v1:')
        assert response['success'] and b['prompt_tokens']==len(response['prompt_token_ids']) and a['seq']>b['seq']
        n=native[rid];assert n['prompt_tokens']==len(response['prompt_token_ids']) and n['prefix_hit_tokens']==a['hit_tokens']
        if tenant is not None:
            shape=shapes[source,tenant,turn,level]
            assert len(response['prompt_token_ids'])==shape['prompt_tokens'] and response['prompt_ids_sha256']==shape['prompt_ids_sha256']
        row=dict(source=source,kind=kind,request_id=rid,prompt_tokens=b['prompt_tokens'],hit_tokens=a['hit_tokens'],
            new_prefill_tokens=b['prompt_tokens']-a['hit_tokens'],actual_salt_sha256=hashlib.sha256(b['backend_cache_salt'].encode()).hexdigest())
        observed_native.append(row);return b,a
    businesses=[r for r in data if r['event']=='development_business'];assert len(businesses)==48
    pairs=[];sources=[];registrations=[];used=set();main_salts={};compiled_native={}
    for r in businesses:
        source=r['source'];sample=samples[source];response=r['result']
        expected=standard_score(sample['dataset'],sample['task'],response['output_text'],sample.get('answer',''))[0]
        assert r['task_score']==expected
        b,a=actual(response,source,r['kind'],r['tenant'],r['turn'],r['level'])
        if r['kind']=='Raw':
            if source in main_salts:assert main_salts[source]==b['backend_cache_salt']
            main_salts[source]=b['backend_cache_salt']
        elif r['compiled_admitted']:
            assert b['backend_cache_salt']==main_salts[source]
            compiled_native[source,r['tenant'],r['turn']]=a['hit_tokens']
        else:assert b['backend_cache_salt']!=main_salts[source]
    refs={r['source']:r for r in data if r['event']=='deployment_compiled_canary'}
    regs={r['source']:r for r in data if r['event']=='deployment_registration'}
    assert len(refs)==len(regs)==4
    for source,sample in samples.items():
        rr=[r for r in businesses if r['source']==source];raw={(r['tenant'],r['turn']):r for r in rr if r['kind']=='Raw'}
        candidate=[r for r in rr if r['kind']=='candidate'];assert len(raw)==len(candidate)==6
        reference=refs[source]['reference'];b,_=actual(reference,source,'controller_private_canary',0,0,'L3')
        assert b['backend_cache_salt']!=main_salts[source]
        reg=regs[source];result=reg['result'];assert result['stable_prefix_hash']==reg['plan']['stable_content_hash']
        requests=[r['payload'] for r in reg['verification_rows'] if r['row_type']=='verification_request'];assert len(requests)==len(result['attempts'])<=1
        matched=[p for p in pubs if requests and (p['request_id']==requests[0]['request_id'] or p['request_id'].startswith(requests[0]['request_id']+'-'))]
        if requests:
            payload=requests[0]
            assert payload['cache_salt']==main_salts[source]
            assert payload['attestation_mode']=='prospective-qualified-deployment-compiled-witness-v2'
            n=native[payload['request_id']];assert n['prompt_tokens']==len(payload['prompt_token_ids'])
        issued=bool(result['certificate_issued']);commit=int(result.get('committed_tokens',0))
        if issued:
            assert commit>0 and commit%16==0 and commit<=reg['plan']['stable_prefix_end_token']
            assert len(matched)==1 and matched[0]['requested_tokens']==commit and matched[0]['backend_cache_salt']==main_salts[source]
            used.add(matched[0]['request_id'])
        else:assert commit==0 and not matched
        for r in candidate:
            ref=raw[r['tenant'],r['turn']];delta=r['task_score']-ref['task_score']
            pairs.append(dict(model=model,source=source,family=sample['revision_family'],tenant=r['tenant'],turn=r['turn'],
                admitted=issued,Raw_score=ref['task_score'],candidate_score=r['task_score'],delta=delta,score_up=delta>.03,score_down=delta<-.03,
                IDs_and_finish_equal=(ref['result']['output_token_ids'],ref['result']['finish_reason'])==(r['result']['output_token_ids'],r['result']['finish_reason'])))
        pp=[r for r in pairs if r['source']==source]
        full_hits=sum(compiled_native.get((source,t,k),0)>=commit for t,k in raw) if issued else 0
        raw_ttft=statistics.median(r['result']['ttft_ms'] for r in raw.values());candidate_ttft=statistics.median(r['result']['ttft_ms'] for r in candidate)
        gross=max(0,raw_ttft-candidate_ttft)*64;cost=reg['complete_controller_ms']
        quality=issued and all(r['delta']>=-.03 for r in pp) and sum(r['delta'] for r in pp)>=0
        physical=issued and full_hits>0
        economic=issued and gross>cost
        sources.append(dict(source=source,family=sample['revision_family'],issued=issued,failure_reason=result['failure_reason'],
            Raw_score_mean=statistics.fmean(r['Raw_score'] for r in pp),candidate_score_mean=statistics.fmean(r['candidate_score'] for r in pp),
            observed_ID_or_finish_changes=sum(not r['IDs_and_finish_equal'] for r in pp),score_up=sum(r['score_up'] for r in pp),score_down=sum(r['score_down'] for r in pp),
            actual_full_prefix_hits=full_hits,compiled_business=6 if issued else 0,committed_tokens=commit,
            Raw_median_backend_TTFT_ms=raw_ttft,candidate_median_backend_TTFT_ms=candidate_ttft,
            gross_64_reuse_TTFT_saving_projection_ms=gross,actual_controller_ms=cost,quality_pass=bool(quality),physical_pass=bool(physical),economic_screen_pass=bool(economic),
            complete_development_acceptance=bool(quality and physical and economic)))
        registrations.append(dict(source=source,family=sample['revision_family'],issued=issued,RPCs=len(requests),
            complete_controller_ms=cost,verification_RPC_ms=sum(a['verification_ms'] for a in result['attempts']),failure_reason=result['failure_reason'],committed_tokens=commit))
    assert {r['request_id'] for r in pubs}==used
    for r in data:
        if r['event']=='development_binding_controls':
            assert all((not x['errors'])==x['expected_admitted'] for x in r['controls'])
    assert len([r for r in data if r['event']=='development_stale_epoch_blocked'])==1
    eligible=[]
    for family in ('HotpotQA','RepoBench'):
        part=[r for r in sources if r['family']==family];assert len(part)==2
        if all(r['complete_development_acceptance'] for r in part) and any(r['Raw_score_mean']>0 for r in part):eligible.append(family)
    summary=dict(status='INDEPENDENT_DEVELOPMENT_AUDIT_COMPLETE',model=model,generations=52,Raw_candidate_pairs=24,
        compiled_admitted_pairs=sum(r['admitted'] for r in pairs),observed_ID_or_finish_changes=sum(not r['IDs_and_finish_equal'] for r in pairs),
        score_up=sum(r['score_up'] for r in pairs),score_down=sum(r['score_down'] for r in pairs),sources=sources,registrations=registrations,
        client_quality_only_eligible=data[-1]['eligible_families'],eligible_families=eligible,invariants_pass=True,
        actual_shared_PSTP_publications=len(pubs),rejected_candidate_shared_publications=0,independent_validation_model_outputs=0,new_GPU_requests=0,
        source_sha256=sha(Path(__file__)),boundary='Compiled deployment self-path attestation; Raw-equivalence not certified. This is new-source development, same-engine descriptive cost screening, not formal serving efficacy.')
    assert not output.exists();output.mkdir(parents=True)
    for name,rr in [('pairs',pairs),('native',observed_native),('registrations',registrations)]:
        with (output/(name+'_v2.csv')).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    write(output/'summary_v2.json',summary);print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--model',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.model,a.output.resolve())
