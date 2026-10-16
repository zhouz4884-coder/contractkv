from types import SimpleNamespace
from scripts.tsc_revision_r4_cost_policy import decide,declared_reuses,build_gate


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
