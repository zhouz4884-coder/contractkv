from types import SimpleNamespace
from scripts.tsc_revision_r4_cost_policy import decide,declared_reuses,build_gate,StagedRegistrar


def feature():
    return {'p_joint_lower':.3,'p_eligible_upper':.4,'p_pass_given_eligible_lower':.75,
            'save_per_reuse_ms':600,'gpu_registration_cost_ms':1000,'information_cost_ms':30,
            'minimum_net_ms':0,'baseline_ttft_p95_ms':500,'tail_budget_ms':2200,'tail_budget_enforced':True}


def test_information_cost_is_not_always_full_GPU_cost():
    pre=decide(feature(),3);post=decide(feature(),3,True)
    assert pre['allow_verification'] and pre['estimated_cost_ms']==430
    assert post['allow_verification'] and post['estimated_cost_ms']==1030
    assert pre['expected_net_ms']==110 and post['expected_net_ms']==320


def test_failure_probability_and_tail_budget_each_can_reject():
    f=feature();f['p_joint_lower']=.01
    assert not decide(f,3)['allow_verification']
    f=feature();f['tail_budget_ms']=1000
    assert decide(f,30)['reason']=='cold_online_tail_budget_rejected'
    f['tail_budget_enforced']=False
    assert decide(f,30)['allow_verification']


def test_declared_query_reuses_are_not_uniform_or_future_output_dependent():
    assert [declared_reuses(t,1) for t in range(3)]==[3,2,2]
    assert [declared_reuses(t,10) for t in range(3)]==[38,28,28]
    assert declared_reuses(7,10)==0


def test_coarse_rejection_performs_no_candidate_tokenization():
    state={'p_joint_lower':0,'p_eligible_upper':1,'p_pass_given_eligible_lower':0,
           'cost_quantiles':{'0.9':{'gpu_registration_ms':1000,'information_ms':20,'planning_ms':10,'raw_logprob_diagnostic_ms':9}}}
    cal={'level':'L3','prefix_states':{'cold':state,'warm':state},'save_per_reuse_median_ms':500,
         'raw_family_ttft_p95_ms':500,'raw_global_ready_p99_ms':2000}
    args=SimpleNamespace(protocol={'runtime':{'concurrency':2}},study='single-session')
    def forbidden(*args):raise AssertionError('No HTTP/tokenization after coarse rejection')
    gate=build_gate(args,({'segments':[]},),cal,'balanced','n',0,1,{},forbidden)
    assert not gate['allow_verification'] and gate['plan'] is None


def test_warm_hint_is_rechecked_against_actual_planned_prefix_hash():
    def state(cost):
        return {'p_joint_lower':1,'p_eligible_upper':1,'p_pass_given_eligible_lower':1,
                'cost_quantiles':{'0.9':{'gpu_registration_ms':cost,'information_ms':20,'planning_ms':10,'raw_logprob_diagnostic_ms':9}}}
    cal={'level':'L3','prefix_states':{'cold':state(1000),'warm':state(100)},
         'save_per_reuse_median_ms':500,'save_per_cached_token_median_ms':.5,
         'raw_native_prefix_p95_tokens':0,'calibrated_prefill_reduction_p95_tokens':4096,
         'raw_family_ttft_p95_ms':500,'raw_global_ready_p99_ms':2200}
    args=SimpleNamespace(protocol={'runtime':{'concurrency':2}},study='single-session')
    def planner(*args):return {'stable_content_hash':'different','stable_full_blocks':16,'cpu_http_preparation_ms':5}
    gate=build_gate(args,({'segments':[]},),cal,'balanced','n',0,1,{'n':{'old':'cert'}},planner)
    assert gate['prefix_state_hint']=='warm' and gate['prefix_state']=='cold'
    assert not gate['prefix_hash_match'] and not gate['allow_verification']
    assert gate['fine_cost_features']['gpu_registration_cost_ms']==1000


def test_post_reference_expected_loss_abstains_once_without_any_rpc():
    calls=[];registrar=StagedRegistrar(.0625,.125,lambda *args:calls.append(args))
    f=feature();f['p_pass_given_eligible_lower']=0
    gate={'allow_verification':True,'scope_case':{'segments':[{'segment_type':'CONTEXT','text':'Eliza preferred her son.'}]},
          'max_literal_answer_words':16,'nonliteral_ambiguity_boundary':.125,'output_contract':None,
          'fine_cost_features':f,'declared_remaining_reuse_hint':3,'pre_business_gate_cpu_ms':5,
          'plan':{'stable_prefix_end_token':16,'stable_content_hash':'h','cpu_http_preparation_ms':10}}
    business={'output_text':'Eliza favors her son.','reference_margins':[.5,1]}
    first=registrar.register(SimpleNamespace(),'n','q',business,gate)
    assert first['failure_reason']=='post_reference_expected_net_rejected' and calls==[]
    assert not first['attempts'] and not first['certificate_issued']
    assert first['complete_verification_ms']>=15
    assert registrar.register(SimpleNamespace(),'n','q',business,gate) is first
