from types import SimpleNamespace
from scripts.tsc_revision_r4_policy import risk_adjusted_benefit,reference_scope_contract,ScopeContractRegistrar


def test_failed_verifications_are_priced_before_gpu_call():
    assert risk_adjusted_benefit(1,2,600,1000,500,3000)['allow_verification']
    result=risk_adjusted_benefit(.4,2,600,1000,500,3000)
    assert not result['allow_verification'] and result['reason']=='risk_adjusted_benefit_rejected'
    assert result['expected_net_ms']==-520


def test_profitable_work_must_also_fit_tail_budget():
    result=risk_adjusted_benefit(1,20,500,1200,1500,2200)
    assert result['expected_net_ms']>0 and result['reason']=='online_tail_budget_rejected'
    assert not result['allow_verification']


def test_invalid_or_zero_reuse_predictions_abstain():
    for value in (float('nan'),float('inf'),-1,True):
        assert not risk_adjusted_benefit(value,10,500,1000,500,3000)['allow_verification']
    assert risk_adjusted_benefit(1,0,500,1000,500,3000)['reason']=='no_declared_remaining_reuse'
    assert not risk_adjusted_benefit(1,2,500,1000,500,3000)['allow_verification']


def case(turn=1):
    return {'segments':[{'segment_id':'s0','segment_type':'SYS_PROMPT','text':'Secret gold answer'},
                        {'segment_id':'s1','segment_type':'TOOL_OBS','text':f'turn={turn}'},
                        {'segment_id':'s2','segment_type':'CONTEXT','text':'The author was Ada Lovelace, born in London.'},
                        {'segment_id':'s3','segment_type':'USER_QUERY','text':'A query can say unsupported words.'}]}


def test_literal_scope_uses_context_not_query_or_system_and_preserves_response():
    text='<think>\n\n</think>\n\nAda Lovelace.'
    assert reference_scope_contract(case(),text)['shareable_query_scope']
    assert not reference_scope_contract(case(),'Secret gold answer')['shareable_query_scope']
    assert not reference_scope_contract(case(),'unsupported words')['shareable_query_scope']
    assert not reference_scope_contract(case(),'he')['shareable_query_scope']
    assert text=='<think>\n\n</think>\n\nAda Lovelace.'


def test_free_form_denial_is_observation_scoped_without_case_id_or_gold():
    text='The context provided does not mention the police coming back for Falder after he left prison. Therefore, the answer is not available in the given context.'
    a=reference_scope_contract(case(1),text);b=reference_scope_contract(case(7),text)
    assert not a['shareable_query_scope'] and a['scope_type']=='exact_observation_only'
    assert a['exact_observation_hash']!=b['exact_observation_hash']
    assert not a['uses_gold_labels'] and not a['served_output_rewritten']


def test_unshareable_reference_has_no_gpu_call_and_no_retry():
    calls=[];registrar=ScopeContractRegistrar(.0625,.125,lambda *args:calls.append(args))
    gate={'allow_verification':True,'scope_case':case(),'output_contract':None,
          'plan':{'stable_prefix_end_token':16,'stable_content_hash':'h','cpu_http_preparation_ms':0}}
    business={'output_text':'This response is not present in the stable context.'}
    first=registrar.register(SimpleNamespace(),'n','q',business,gate)
    cost=first['complete_verification_ms']
    second=registrar.register(SimpleNamespace(),'n','q',business,gate)
    assert first is second and calls==[] and not first['certificate_issued'] and first['attempts']==[]
    assert first['failure_reason']=='observation_scope_has_no_declared_exact_reuse'
    assert first['complete_verification_ms']==cost
