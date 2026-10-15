"""Prospective single-attempt benefit admission in explicit millisecond units."""
import math


def prospective_benefit(reusable_full_blocks,block_size,expected_remaining_reuses,
                        prefill_ms_per_token,verification_cost_p95_ms,preparation_ms,safety_factor,
                        complete_cost_p95_ms=None):
    result={'allow_verification':False,'reason':'invalid_or_incomplete_cost_features',
            'estimated_saved_ms':0.0,'estimated_cost_ms':0.0,'safety_adjusted_cost_ms':0.0,
            'online_verification_attempt_limit':1,'prediction_is_not_realized_saving':True}
    values=[reusable_full_blocks,block_size,expected_remaining_reuses,prefill_ms_per_token,
            verification_cost_p95_ms,preparation_ms,safety_factor]
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values): return result
    if int(reusable_full_blocks)!=reusable_full_blocks or reusable_full_blocks<0 or int(block_size)!=block_size or block_size<=0:
        return result
    if expected_remaining_reuses<0 or prefill_ms_per_token<=0 or verification_cost_p95_ms<=0 or preparation_ms<0 or safety_factor<1:
        return result
    if complete_cost_p95_ms is not None and (not isinstance(complete_cost_p95_ms,(int,float)) or not math.isfinite(complete_cost_p95_ms) or complete_cost_p95_ms<=0):
        return result
    saved=reusable_full_blocks*block_size*expected_remaining_reuses*prefill_ms_per_token
    cost=verification_cost_p95_ms+preparation_ms
    if complete_cost_p95_ms is not None: cost=max(cost,complete_cost_p95_ms)
    result.update(estimated_saved_ms=saved,estimated_cost_ms=cost,safety_adjusted_cost_ms=cost*safety_factor)
    if reusable_full_blocks==0: result['reason']='no_full_reusable_block'
    elif saved<=cost*safety_factor: result['reason']='estimated_reuse_not_profitable'
    else: result.update(allow_verification=True,reason='prospective_benefit_pass')
    return result
