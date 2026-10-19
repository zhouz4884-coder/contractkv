from copy import deepcopy
from types import SimpleNamespace
import pytest
from scripts.tsc_template_task_protocol_v2 import ServingAuthority,DeploymentRegistrar,prepared,deployment_request
from scripts.contractkv_cache_identity import CacheAuthorizationError
from tests.test_tsc_revision_r2_admission import fixture

def context():
    args,reference,gate=fixture();args.model_identity='Qwen3-8B'
    sample=dict(dataset='LongBench',task='hotpotqa',sample_id='cpu',revision_session_id='faq',revision_family='HotpotQA',
        revision_input_fidelity={'protocol':'structure-preserving-window-v2'},segments=[dict(type='SYS_PROMPT',text='Use context.'),
        dict(type='RAG_CHUNK',text='Alpha is a city.\nOriginal whitespace preserved.'),dict(type='USER_QUERY',text='What is Alpha?')])
    identity=dict(model_revision='weights',tokenizer='tok',chat_template_hash='chat',runtime_revision='runtime')
    authority=ServingAuthority(args,identity,[sample],2,'qualified')
    cert=dict(certificate_hash='c',stable_prefix_hash='h');plan=gate['plan']
    return authority,args,sample,plan,cert,reference,gate

def test_real_question_stays_task_and_only_declared_metadata_varies():
    a,_,sample,_,_,_,_=context()
    for level in ('L0','L3'):
        case,order,messages=prepared(sample,1,2,level)
        assert 'What is Alpha?' in messages[1]['content'] and 'Return exactly' not in messages[0]['content']
        assert 'Original whitespace preserved.' in messages[1]['content']
        assert 'authorized tenant=tenant01; turn=2' in messages[1]['content']

def test_session_and_template_granularity_never_changes_business_cache_group():
    a,_,sample,plan,cert,_,_=context()
    salts=[a.cache.require(a.cache_identity(sample,t)) for t in (None,0,1)]
    assert len(set(salts))==1
    private=a.cache.bind('controller',a.domain,1,'faq:controller-private-attestation')
    assert a.cache.require(private)!=salts[0]
    template=a.bind(sample,plan,cert)
    assert not a.admit(sample,1,2,plan,cert,template)
    session=a.bind(sample,plan,cert,0)
    assert 'session_membership_mismatch' in a.admit(sample,1,2,plan,cert,session)

@pytest.mark.parametrize('field',['question','document','signature','generation','layout'])
def test_signed_request_binding_rejects_actual_scope_mutations(field):
    a,_,sample,plan,cert,_,_=context();bound=a.bind(sample,plan,cert)
    changed=deepcopy(sample);newplan=deepcopy(plan)
    if field=='question':changed['segments'][-1]['text']+=' changed'
    elif field=='document':changed['segments'][1]['text']+=' changed'
    elif field=='signature':bound['signature']='bad'
    elif field=='generation':a.args.policy_hash='changed'
    else:newplan['layout_hash']='different'
    assert a.admit(changed,0,1,newplan,cert,bound)

def test_deployment_attestation_keeps_exact_original_answer_EOS_and_floors():
    a,args,sample,plan,_,reference,gate=context();rows=[];reg=DeploymentRegistrar(a.cache,a.cache_identity(sample))
    def fail(url,payload,timeout):
        assert rows[-1]['payload']==payload
        assert payload['cache_salt']==a.cache.require(a.cache_identity(sample))
        assert payload['attestation_mode']=='prospective-qualified-deployment-compiled-witness-v2'
        assert payload['prompt_token_ids']==plan['prompt_token_ids']+[99,2]
        return dict(certificate_issued=False,committed_tokens=0,failure_reason='test_margin_fail')
    reg.poster=fail;result=reg.register(args,'faq','session0',reference,gate,rows.append)
    assert not result['certificate_issued'] and len(result['attempts'])==1
    reference['reference_margins'][0]=.01
    result=reg.register(args,'faq','session1',reference,gate,rows.append)
    assert not result['attempts'] and result['failure_reason']=='pointwise_raw_answer_or_eos_margin_below_floor'

def test_stale_epoch_denied_before_any_generation():
    a,_,sample,_,_,_,_=context();identity=a.cache_identity(sample,0);a.cache.advance_epoch(a.domain,2)
    with pytest.raises(CacheAuthorizationError):a.cache.require(identity)


def test_repo_prefix_whitespace_and_family_budget_are_protected():
    from scripts.tsc_template_task_protocol_v2 import budget
    a,_,sample,plan,cert,_,_=context()
    sample["dataset"]="RepoBench";sample["task"]="python_repository_completion";sample["revision_family"]="RepoBench"
    sample["segments"].insert(-1,dict(type="CODE_PREFIX",text="file.py\ndef f():\n    x = 1\n"))
    _,_,messages=prepared(sample,7,8,"L3")
    assert "file.py\ndef f():\n    x = 1\n" in messages[1]["content"] and budget(sample)==384
    bound=a.bind(sample,plan,cert)
    assert a.admit(sample,0,9,plan,cert,bound)==["observation_outside_frozen_schema"]
    assert not a.admit(sample,0,8,plan,cert,bound)
