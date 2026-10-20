"""End-to-end CPU admission boundary, separate from actual GPU efficacy."""
from tests.test_tsc_template_task_v2 import context
from scripts.tsc_behavior_scope_protocol_v2 import StrictServingAuthority
from scripts.contractkv_exact_behavior import digest as exact_digest
from scripts.phase17_live_common import digest


def test_joint_authorization_actual_prefix_and_Raw_behavior_admission():
    old,args,sample,_,_,_,_=context()
    a=StrictServingAuthority(args,old.identity,[sample],2,'qualified')
    candidate_ids=list(range(40));raw_ids=list(range(40,80))
    plan=dict(prompt_token_ids=candidate_ids,prompt_ids_sha256=digest(candidate_ids),layout_hash='legal-layout')
    certificate=dict(certificate_issued=True,certificate_hash='GPU-certificate-fixture',stable_prefix_hash=digest(candidate_ids[:35]),
                     stable_prefix_tokens=35,committed_tokens=32,minimum_margin_guard_passed=True,
                     raw_margin_min=.5,candidate_margin_min=.5,terminal_stop_margin=.5)
    raw=dict(success=True,prompt_token_ids=raw_ids,output_token_ids=[8,9,0],finish_reason='stop',
             witness_available=True,reference_margins=[.5,.5,.5])
    candidate={**raw,'prompt_token_ids':candidate_ids}
    behavior=a.behavior.issue(raw,candidate,certificate,raw_ids,candidate_ids,'RAW_QUERY',exact_digest(raw_ids))
    authorization=a.bind(sample,plan,certificate)
    assert not a.admit(sample,0,1,plan,certificate,authorization,raw_ids=raw_ids,candidate_ids=candidate_ids,behavior=behavior)
    # Correct template authorization alone is insufficient.
    assert 'exact_Raw_behavior_evidence_missing' in a.admit(sample,0,1,plan,certificate,authorization,raw_ids=raw_ids,candidate_ids=candidate_ids)
    changed=list(candidate_ids);changed[3]=999
    errors=a.admit(sample,0,1,plan,certificate,authorization,raw_ids=raw_ids,candidate_ids=changed,behavior=behavior)
    assert 'actual_certified_prefix_hash_mismatch' in errors and 'exact_request_behavior_scope_mismatch' in errors
    # The same physical prefix may legally remain identical while a different
    # suffix still needs its own behavior evidence.
    changed=list(candidate_ids);changed[38]=999
    errors=a.admit(sample,0,1,plan,certificate,authorization,raw_ids=raw_ids,candidate_ids=changed,behavior=behavior)
    assert 'actual_certified_prefix_hash_mismatch' not in errors and 'exact_request_behavior_scope_mismatch' in errors
