"""Regression from the real failed Llama reference, with recorded RPC stubs."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root,output):
    if output.exists():raise FileExistsError(output)
    os.environ['CUDA_VISIBLE_DEVICES']=''
    study=root/'results/tsc_revision_mechanism_controls_20261018';snapshot=study/'source_snapshot'
    sys.path.insert(0,str(snapshot))
    from scripts.tsc_revision_r2_admission import SingleShotRegistrar
    from scripts.contractkv_verifier import VerificationIncomplete
    path=root/'scripts/tsc_revision_incomplete_reference_fix_v5.py'
    spec=importlib.util.spec_from_file_location('fail_closed_fix_v5',path);fix=importlib.util.module_from_spec(spec);spec.loader.exec_module(fix)
    captured=study/'cells/Llama-3.1-8B-Instruct_r1/attempt2/responses.jsonl'
    rr=[json.loads(x) for x in captured.read_text(encoding='utf-8').splitlines() if x.strip()]
    business={}
    for x in rr:
        if x['event']=='business':business[x['case_id'],x['condition']]=x['response']
    bad=deepcopy(business['code_context_v1_order_risk','raw_witness'])
    assert bad['finish_reason']=='length' and len(bad['output_token_ids'])==64 and len(bad['reference_margins'])==64
    assert bad['witness_available'] and min(bad['reference_margins'])>=.0625
    args=SimpleNamespace(cell_id='Llama-3.1-8B-Instruct_r1',policy_hash=sha(study/'freeze_v3.json'),
                         base_url='http://127.0.0.1:1/v1',timeout=300)
    original=SingleShotRegistrar.register;patched=fix.repaired_register(original,VerificationIncomplete)
    spy=[]
    def no_rpc(*a,**k):spy.append((a,k));raise AssertionError('No RPC is legal without stop evidence')
    # A minimal pre-RPC plan is deliberate: the exception occurs before any
    # candidate payload is built. It is not claimed as an executed GPU layout.
    gate=dict(allow_verification=True,plan=dict(stable_prefix_end_token=0,stable_content_hash='',cpu_http_preparation_ms=0))
    before=SingleShotRegistrar(.0625,.125,poster=no_rpc);raised=None
    try:original(before,args,'actual-length-regression','scope',bad,gate)
    except VerificationIncomplete as e:raised=str(e)
    assert raised=='raw finish_reason=length' and not spy
    after=SingleShotRegistrar(.0625,.125,poster=no_rpc);records=[]
    result=patched(after,args,'actual-length-regression','scope',bad,gate,records.append)
    assert not spy and not result['certificate_issued'] and not result['attempts']
    assert result['verify_decision']=='INCOMPLETE' and result['committed_tokens']==0
    assert result['raw_eos_margin'] is None and result['verification_status']=='not_attempted'
    assert bad==business['code_context_v1_order_risk','raw_witness']
    assert len(after.decisions)==1 and records[-1]['GPU_RPC_dispatched'] is False

    normal=[]
    qualifications=[x for x in rr if x['event']=='qualification']
    for q in qualifications:
        raw=deepcopy(business[q['case_id'],'raw_witness']);plan=deepcopy(q['plan'])
        response_rows=[x['response'] for x in rr if x['event']=='qualification_detail' and x['case_id']==q['case_id'] and x.get('row_type')=='verification_response']
        emitted=[];calls=[]
        def poster(url,payload,timeout):
            calls.append(deepcopy(payload));assert len(response_rows)==1
            return deepcopy(response_rows[0])
        gate=dict(allow_verification=True,reason='predeclared mechanism diagnostic without economic screening',plan=plan)
        left=SingleShotRegistrar(.0625,.125,poster=poster)
        a=original(left,args,q['namespace'],plan['query_scope'],raw,gate,emitted.append)
        first_payload=deepcopy(calls);first_events=deepcopy(emitted);calls.clear();emitted.clear()
        right=SingleShotRegistrar(.0625,.125,poster=poster)
        b=patched(right,args,q['namespace'],plan['query_scope'],raw,gate,emitted.append)
        volatile={'complete_verification_ms','post_business_registration_ms','verification_ms'}
        def semantic(value):
            if isinstance(value,dict):return {k:semantic(v) for k,v in value.items() if k not in volatile}
            if isinstance(value,list):return [semantic(x) for x in value]
            return value
        assert semantic(a)==semantic(b),q['case_id']
        assert calls==first_payload and emitted==first_events,q['case_id']
        normal.append(dict(case_id=q['case_id'],same_decision=True,same_payload=True,same_recorded_events=True,
                           stub_RPC_calls=len(calls),recorded_certificate_issued=a['certificate_issued']))
    assert len(normal)==15
    report=dict(status='PASS',new_GPU_requests=0,captured_reference_sha256=sha(captured),
        original_incomplete_exception=raised,repaired_status=result['verify_decision'],raw_budget_unchanged=64,
        no_incomplete_RPC=True,no_incomplete_commit=True,original_raw_output_not_rewritten=True,
        complete_reference_cases_compared=len(normal),normal_cases=normal,
        all_complete_reference_public_decisions_payloads_events_identical=True,
        patch_sha256=sha(path),original_admission_sha256=sha(Path(sys.modules[SingleShotRegistrar.__module__].__file__)),
        classification='CPU control-flow regression using a real captured reference and recorded-response stubs, not a new GPU efficacy result')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:report[k] for k in ['status','new_GPU_requests','raw_budget_unchanged','complete_reference_cases_compared','no_incomplete_RPC']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
