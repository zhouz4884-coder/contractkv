from copy import deepcopy
import pytest
from scripts.contractkv_exact_behavior import ExactBehaviorLedger,digest


def fixture():
    raw=dict(success=True,prompt_token_ids=[1,2],output_token_ids=[8,9,0],finish_reason='stop',
             witness_available=True,reference_margins=[.5,.5,.5])
    candidate={**raw,'prompt_token_ids':[2,1]}
    cert=dict(certificate_issued=True,minimum_margin_guard_passed=True,raw_margin_min=.5,
              candidate_margin_min=.5,terminal_stop_margin=.5,committed_tokens=16,
              certificate_hash='certificate',stable_prefix_hash='prefix')
    ledger=ExactBehaviorLedger({'model':'fixed','epoch':1,'budget':128})
    return ledger,raw,candidate,cert


def issue(ledger,raw,candidate,cert,kind='RAW_QUERY'):
    return ledger.issue(raw,candidate,cert,raw['prompt_token_ids'],candidate['prompt_token_ids'],kind,digest(raw['prompt_token_ids']))


def test_deployment_witness_is_never_strict_Raw_evidence():
    ledger,raw,candidate,cert=fixture()
    with pytest.raises(ValueError,match='not_Raw'):issue(ledger,raw,candidate,cert,'COMPILED_DEPLOYMENT')
    assert ledger.errors([1,2],[2,1],cert,None)==['exact_Raw_behavior_evidence_missing']


@pytest.mark.parametrize('field',['output','EOS','prompt','floor','commit','witness'])
def test_qualification_fails_closed(field):
    ledger,raw,candidate,cert=fixture()
    if field=='output':candidate['output_token_ids']=[8,7,0]
    if field=='EOS':candidate['finish_reason']='length'
    if field=='prompt':raw['prompt_token_ids']=[]
    if field=='floor':cert['terminal_stop_margin']=.124
    if field=='commit':cert['committed_tokens']=17
    if field=='witness':raw['witness_available']=False
    with pytest.raises(ValueError):issue(ledger,raw,candidate,cert)


def test_exact_repeat_allowed_other_observation_and_old_epoch_denied():
    ledger,raw,candidate,cert=fixture();bound=issue(ledger,raw,candidate,cert)
    assert not ledger.errors([1,2],[2,1],cert,bound)
    assert ledger.errors([1,3],[3,1],cert,bound)
    other=ExactBehaviorLedger({'model':'fixed','epoch':2,'budget':128})
    assert other.errors([1,2],[2,1],cert,bound)
    tampered=deepcopy(bound);tampered['evidence']['raw_prompt_sha256']=digest([1,3])
    assert 'behavior_signature_invalid' in ledger.errors([1,3],[2,1],cert,tampered)


def test_authorization_does_not_bypass_behavior_gate():
    from tests.test_tsc_template_task_v2 import context
    from scripts.tsc_behavior_scope_protocol_v1 import StrictServingAuthority
    old,args,sample,plan,cert,raw,gate=context()
    a=StrictServingAuthority(args,old.identity,[sample],2,'qualified')
    bound=a.bind(sample,plan,cert)
    assert 'actual_prompt_IDs_missing' in a.admit(sample,0,1,plan,cert,bound)


def test_known_doc107_regressions_rejected_without_reclassifying_scores():
    import json
    from pathlib import Path
    p=Path('results/tsc_behavior_scope_repair_20261020/prior_scope_audit_v1.json')
    audit=json.loads(p.read_text(encoding='utf-8'))
    assert audit['known_compiled_score_drop_events']==36 and audit['unique_bad_coordinates']==6
    ledger,_,_,cert=fixture()
    for event in audit['regression_events']:
        assert event['source']=='LongBench:hotpotqa:hotpotqa:doc:107' and event['turn']==6
        assert ledger.errors(event['compiled_prompt_ids'],event['compiled_prompt_ids'],cert,None)==['exact_Raw_behavior_evidence_missing']
