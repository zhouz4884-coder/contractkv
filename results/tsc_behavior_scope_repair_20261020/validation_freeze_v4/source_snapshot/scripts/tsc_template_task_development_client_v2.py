"""Prospective original-deployment qualification; no held-out output access."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_template_task_protocol_v2 import prepared,candidate_plan,ServingAuthority,DeploymentRegistrar,MODELS,budget
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.contractkv_cache_identity import CacheAuthorizationError

def read(p):return json.loads(p.read_text(encoding='utf-8'))

def main(args):
    assert not args.output.exists();args.output.touch()
    def record(r):
        with args.output.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(dict(epoch_s=time.time(),monotonic_s=time.perf_counter(),model=args.model_identity,**r),ensure_ascii=False,allow_nan=False)+'\n')
    inputs=args.study/'inputs_development_v2'
    samples=[json.loads(s) for s in (inputs/'sessions_v2.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(samples)==4
    shapes={(r['source_group'],r['tenant'],r['turn'],r['level']):r for s in (inputs/'CPU_shapes_v2.jsonl').read_text().splitlines()
            if (r:=json.loads(s))['model']==args.model_identity}
    protocol=read(args.study/'protocol_v2.json');authority=ServingAuthority(args,read(args.identity),samples,2,digest(protocol['qualification']))
    record(dict(event='template_task_development_started',independent_validation_outputs_read=False))
    business_count=0;proofs=[]
    def generate(sample,tenant,turn,level,kind,certificate=None,plan=None,bound=None):
        nonlocal business_count
        _,_,messages=prepared(sample,tenant,turn,level)
        rid=f'{args.cell_id}-{kind}-{sample["revision_session_id"]}-tenant{tenant:02d}-t{turn}'
        if kind=='Raw':result=authority.generate(sample,tenant,messages,budget(sample),rid)
        elif certificate and certificate['certificate_issued']:
            errors=authority.admit(sample,tenant,turn,plan,certificate,bound);assert not errors,errors
            record(dict(event='business_binding_check',source=sample['revision_source_group'],tenant=tenant,turn=turn,errors=errors))
            result=authority.generate(sample,tenant,messages,budget(sample),rid)
        else:result=authority.private_generate(sample,messages,budget(sample),rid,kind='counterfactual')
        expected=shapes[sample['revision_source_group'],tenant,turn,level]
        assert result['success'] and result['prompt_ids_sha256']==expected['prompt_ids_sha256']
        assert len(result['prompt_token_ids'])==expected['prompt_tokens']
        score=standard_score(sample['dataset'],sample['task'],result['output_text'],sample.get('answer',''))[0]
        record(dict(event='development_business',source=sample['revision_source_group'],tenant=tenant,turn=turn,
            level=level,kind=kind,compiled_admitted=kind!='Raw' and bool(certificate and certificate['certificate_issued']),
            result=result,task_score=score));business_count+=1
        return result,score
    for sample in samples:
        baseline={}
        for tenant in range(2):
            for turn in range(3):baseline[tenant,turn]=generate(sample,tenant,turn,'L0','Raw')
        started=time.perf_counter();plan=candidate_plan(args,sample)
        reference=authority.private_generate(sample,plan['messages'],budget(sample),f'{args.cell_id}-compiled-canary-{sample["revision_session_id"]}',True)
        expected=shapes[sample['revision_source_group'],0,0,'L3']
        assert reference['success'] and reference['prompt_ids_sha256']==plan['prompt_ids_sha256']==expected['prompt_ids_sha256']
        record(dict(event='deployment_compiled_canary',source=sample['revision_source_group'],reference=reference,plan=plan));business_count+=1
        rows=[];reg=DeploymentRegistrar(authority.cache,authority.cache_identity(sample))
        from scripts.tsc_revision_r3_output_contract import python_statement_contract
        syntax=python_statement_contract(reference['output_text']) if sample['revision_family']=='RepoBench' else dict(passed=True,reason='not_code')
        certificate=reg.register(args,sample['revision_session_id'],'template',reference,
            dict(allow_verification=syntax['passed'],reason=('prospective_original_deployment_feasibility' if syntax['passed'] else 'compiled_reference_output_contract:'+syntax['reason']),plan=plan),rows.append)
        bound=authority.bind(sample,plan,certificate) if certificate['certificate_issued'] else None
        record(dict(event='deployment_registration',source=sample['revision_source_group'],result=certificate,plan=plan,
            verification_rows=rows,bound=bound,complete_controller_ms=(time.perf_counter()-started)*1000,
            reference_source='compiled_deployment_path',Raw_equivalence_not_attested=True))
        pairs=[]
        for tenant in range(2):
            for turn in range(3):
                observed,score=generate(sample,tenant,turn,'L3','candidate',certificate,plan,bound)
                raw,raw_score=baseline[tenant,turn]
                pairs.append(dict(tenant=tenant,turn=turn,Raw_score=raw_score,candidate_score=score,delta=score-raw_score,
                    IDs_and_finish_equal=(raw['output_token_ids'],raw['finish_reason'])==(observed['output_token_ids'],observed['finish_reason'])))
        controls=[]
        if bound:
            controls.append(dict(kind='template_authorized_other_tenant',errors=authority.admit(sample,1,1,plan,certificate,bound),expected_admitted=True))
            session=authority.bind(sample,plan,certificate,0)
            controls.append(dict(kind='session_wrong_tenant',errors=authority.admit(sample,1,1,plan,certificate,session),expected_admitted=False))
            tampered=deepcopy(bound);tampered['signature']='bad'
            controls.append(dict(kind='tampered_signature',errors=authority.admit(sample,0,1,plan,certificate,tampered),expected_admitted=False))
            changed=deepcopy(sample);next(s for s in changed['segments'] if s['type']=='USER_QUERY')['text']+=' changed'
            controls.append(dict(kind='unregistered_question',errors=authority.admit(changed,0,1,plan,certificate,bound),expected_admitted=False))
            changed=deepcopy(sample);next(s for s in changed['segments'] if s['type'] not in {'SYS_PROMPT','USER_QUERY'})['text']+=' changed'
            controls.append(dict(kind='changed_source_manifest',errors=authority.admit(changed,0,1,plan,certificate,bound),expected_admitted=False))
            assert all((not r['errors'])==r['expected_admitted'] for r in controls)
        record(dict(event='development_binding_controls',source=sample['revision_source_group'],controls=controls,new_GPU_requests=0))
        source_ok=bool(certificate['certificate_issued'] and all(p['delta']>=-.03 for p in pairs)
            and sum(p['delta'] for p in pairs)>=0)
        proofs.append(dict(source=sample['revision_source_group'],family=sample['revision_family'],compiled_canary_output_contract=syntax,certificate_issued=bool(certificate['certificate_issued']),
            failure_reason=certificate['failure_reason'],quality_qualified=source_ok,pairs=pairs,
            mean_Raw_score=sum(p['Raw_score'] for p in pairs)/len(pairs),mean_candidate_score=sum(p['candidate_score'] for p in pairs)/len(pairs)))
    old=authority.cache_identity(samples[0],0);authority.cache.advance_epoch(authority.domain,2)
    try:authority.cache.require(old)
    except CacheAuthorizationError:record(dict(event='development_stale_epoch_blocked',new_GPU_requests=0))
    else:raise AssertionError('Stale authorization identity accepted')
    eligible=[]
    for family in ('HotpotQA','RepoBench'):
        part=[p for p in proofs if p['family']==family];assert len(part)==2
        if all(p['quality_qualified'] for p in part) and any(p['mean_Raw_score']>0 for p in part):eligible.append(family)
    qualified=bool(eligible)
    assert business_count==52
    record(dict(event='template_task_development_complete',counts=dict(generations=52,paired_business=24,compiled_canaries=4),
        model_qualified=qualified,eligible_families=eligible,source_results=proofs,independent_validation_outputs_read=False))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('study','identity','output'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('base-url','model','model-identity','cell-id','policy-hash'):p.add_argument('--'+k,required=True)
    p.add_argument('--timeout',type=float,default=600);main(p.parse_args())
