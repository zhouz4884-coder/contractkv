"""Two-stage value-of-information admission with observable prefix states."""
import math
import time
from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract
from scripts.tsc_revision_r3_output_contract import OutputContractRegistrar
from scripts.tsc_revision_r2_candidate_plan import candidate_plan

PROFILES={
    'balanced':{'cost_quantile':'0.9','saving_suffix':'median_ms','minimum_net_ms':0.,'cold_tail_multiplier':1.},
    'conservative':{'cost_quantile':'0.95','saving_suffix':'q25_ms','minimum_net_ms':100.,'cold_tail_multiplier':.9},
}


def declared_reuses(turn,tenants,concurrency=2):
    if type(turn) is not int or turn not in (0,1,2) or type(tenants) is not int or tenants<1:return 0
    return (4 if turn==0 else 3)*tenants-min(concurrency,tenants)


def stage_features(calibration,profile,prefix_state,study,plan=None):
    chosen=PROFILES[profile];states=calibration['prefix_states'];state=states[prefix_state]
    if state.get('fallback_to_cold'):state=states['cold'];prefix_state='cold'
    costs=state['cost_quantiles'][chosen['cost_quantile']]
    info=costs['information_ms']
    if plan is not None:
        info=max(costs['planning_ms'],plan['cpu_http_preparation_ms'])+costs['raw_logprob_diagnostic_ms']+1.
    saving=calibration['save_per_reuse_'+chosen['saving_suffix']]
    if plan is not None:
        tokens=max(0,plan['stable_full_blocks']*16-math.ceil(calibration['raw_native_prefix_p95_tokens']/16)*16)
        tokens=min(tokens,calibration['calibrated_prefill_reduction_p95_tokens'])
        saving=tokens*calibration['save_per_cached_token_'+chosen['saving_suffix']]
    return {'p_joint_lower':min(state['p_joint_lower'],state['p_eligible_upper']),
            'p_eligible_upper':state['p_eligible_upper'],'p_pass_given_eligible_lower':state['p_pass_given_eligible_lower'],
            'save_per_reuse_ms':saving,'gpu_registration_cost_ms':costs['gpu_registration_ms'],'information_cost_ms':info,
            'minimum_net_ms':chosen['minimum_net_ms'],'prefix_state':prefix_state,
            'baseline_ttft_p95_ms':calibration['raw_family_ttft_p95_ms'],
            'tail_budget_ms':calibration['raw_global_ready_p99_ms']*chosen['cold_tail_multiplier'],
            'tail_budget_enforced':study=='single-session','profile':profile}


def decide(features,reuses,post_reference=False):
    result={'allow_verification':False,'reason':'invalid_staged_cost_features','online_verification_attempt_limit':1,
            'tail_budget_is_forecast_not_runtime_guarantee':True,'prediction_is_not_realized_saving':True}
    values=[features.get(k) for k in ('p_joint_lower','p_eligible_upper','p_pass_given_eligible_lower','save_per_reuse_ms',
                                     'gpu_registration_cost_ms','information_cost_ms','minimum_net_ms',
                                     'baseline_ttft_p95_ms','tail_budget_ms')]+[reuses]
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values):return result
    if any(not 0<=features[k]<=1 for k in ('p_joint_lower','p_eligible_upper','p_pass_given_eligible_lower')) or reuses<0:return result
    if features['gpu_registration_cost_ms']<=0 or any(features[k]<0 for k in ('information_cost_ms','save_per_reuse_ms','minimum_net_ms','baseline_ttft_p95_ms')) or features['tail_budget_ms']<=0:return result
    probability=features['p_pass_given_eligible_lower'] if post_reference else features['p_joint_lower']
    gpu_probability=1. if post_reference else features['p_eligible_upper']
    saved=probability*reuses*features['save_per_reuse_ms']
    cost=gpu_probability*features['gpu_registration_cost_ms']+features['information_cost_ms']
    worst=features['baseline_ttft_p95_ms']+features['gpu_registration_cost_ms']+features['information_cost_ms']
    result.update(**features,stage='post_reference_GPU_admission' if post_reference else 'pre_reference_information_admission',
                  declared_remaining_reuses=reuses,estimated_saved_ms=saved,estimated_cost_ms=cost,
                  expected_net_ms=saved-cost,predicted_ready_bound_ms=worst)
    if not reuses:result['reason']='no_declared_remaining_reuse'
    elif saved-cost<=features['minimum_net_ms']:result['reason']='post_reference_expected_net_rejected' if post_reference else 'pre_reference_expected_net_rejected'
    elif features['tail_budget_enforced'] and worst>features['tail_budget_ms']:result['reason']='cold_online_tail_budget_rejected'
    else:result.update(allow_verification=True,reason='staged_benefit_and_tail_pass')
    return result


def build_gate(args,prepared,calibration,profile,namespace,turn,tenants,prefixes,planner=candidate_plan):
    begin=time.perf_counter();case=prepared[0];known=prefixes.get(namespace,{})
    state_hint='warm' if known else 'cold';reuses=declared_reuses(turn,tenants,args.protocol['runtime']['concurrency'])
    common={'plan':None,'scope_case':{'segments':case['segments']},'max_literal_answer_words':16,
            'nonliteral_ambiguity_boundary':.125,'output_contract':'one_python_statement' if any(s.get('segment_type')=='CODE_FILE' for s in case['segments']) else None,
            'declared_remaining_reuse_hint':reuses,'profile':profile,'prefix_state_hint':state_hint}
    coarse=decide(stage_features(calibration,profile,state_hint,args.study),reuses)
    if not coarse['allow_verification']:
        return {**common,**coarse,'coarse_gate':coarse,'pre_business_gate_cpu_ms':(time.perf_counter()-begin)*1000}
    plan=planner(args,prepared,calibration['level'])
    state='warm' if plan['stable_content_hash'] in known else 'cold'
    features=stage_features(calibration,profile,state,args.study,plan);fine=decide(features,reuses)
    elapsed=(time.perf_counter()-begin)*1000
    return {**common,**fine,'plan':plan,'coarse_gate':coarse,'fine_cost_features':features,
            'prefix_hash_match':state=='warm','pre_business_gate_cpu_ms':max(0,elapsed-plan['cpu_http_preparation_ms'])}


class StagedRegistrar(OutputContractRegistrar):
    def register(self,args,namespace,scope,business,gate,record=lambda row:None):
        key=(namespace,scope)
        with self.lock:already=key in self.decisions or key in self.reserved
        if already:return super().register(args,namespace,scope,business,gate,record)
        started=time.perf_counter();check=None;post=None
        if gate.get('allow_verification'):
            check=reference_scope_contract(gate['scope_case'],business['output_text'],gate['max_literal_answer_words'],
                                           business.get('reference_margins'),gate['nonliteral_ambiguity_boundary'])
            record({'row_type':'reference_scope_contract','certificate_namespace':namespace,'query_scope':scope,'check':check})
            if not check['shareable_query_scope']:
                gate={**gate,'allow_verification':False,'reason':'observation_scope_has_no_declared_exact_reuse'}
            elif business.get('reference_margins') and min(business['reference_margins'])>=self.raw_floor:
                post=decide(gate['fine_cost_features'],gate['declared_remaining_reuse_hint'],True)
                record({'row_type':'post_reference_benefit_gate','certificate_namespace':namespace,'query_scope':scope,**post})
                if not post['allow_verification']:gate={**gate,'allow_verification':False,'reason':post['reason']}
        cpu=(time.perf_counter()-started)*1000
        result=super().register(args,namespace,scope,business,gate,record)
        extra=cpu+gate.get('pre_business_gate_cpu_ms',0)
        result['staged_admission_cpu_ms']=extra;result['reference_scope_contract']=check;result['post_reference_benefit']=post
        result['complete_verification_ms']+=extra
        result['post_business_registration_ms']+=cpu
        result['pre_business_gate_cpu_ms']=gate.get('pre_business_gate_cpu_ms',0)
        return result
