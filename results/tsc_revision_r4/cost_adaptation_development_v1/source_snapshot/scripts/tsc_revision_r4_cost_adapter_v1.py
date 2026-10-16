"""One bounded controller-only cost adaptation; original certification intact."""
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from scripts import tsc_revision_r4_cost_policy as original_cost
from scripts.tsc_revision_r4_build_cost_profile_v1 import forecast
from scripts.tsc_revision_build_inputs import family as task_family

PROFILE_SHA256='be21959e9bde139b7fd0ecdec7f64bea089f9858b929f737accc232882ce4c8f'


@lru_cache(maxsize=4)
def load_profile(path):
    path=Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=PROFILE_SHA256:
        raise ValueError('Preserve the one DEV-selected candidate profile')
    value=json.loads(path.read_text(encoding='utf-8'))
    assert not value['new_independent_outputs_used']
    return value


def adapted_features(base,profile,model,resolve_family):
    def features(calibration,pname,prefix_state,study,plan=None):
        value=base(calibration,pname,prefix_state,study,plan)
        if model not in profile['active_candidate_models'] or study!='template-fanout':
            return value
        if pname!='balanced':raise ValueError('Only the frozen balanced DEV calibration is supported')
        cold=calibration['prefix_states']['cold']['cost_quantiles']['0.9']['gpu_registration_ms']
        allowance=value['tail_budget_ms']
        if plan is None:
            value['gpu_registration_cost_ms']=max(cold,value['gpu_registration_cost_ms'])
            value['tail_budget_ms']=value['baseline_ttft_p95_ms']+allowance
            value['tail_budget_enforced']=True
            value['additional_sync_controller_allowance_ms']=allowance
            value['cost_profile_version']='DEV-monotone-cold-envelope-v1'
            value['cost_profile_stage']='coarse_before_prompt_shape'
            return value
        result=forecast(profile,model,resolve_family(calibration),calibration['level'],len(plan['prompt_token_ids']),value)
        if result is None:
            value['gpu_registration_cost_ms']=max(cold,value['gpu_registration_cost_ms'])
            value['save_per_reuse_ms']=0.
            value['tail_budget_ms']=value['baseline_ttft_p95_ms']+allowance
            value['tail_budget_enforced']=True
            value['additional_sync_controller_allowance_ms']=allowance
            value['cost_profile_version']='DEV-monotone-cold-envelope-v1'
            value['cost_profile_support']='unsupported_model_family_level_length'
            return value
        result['cost_profile_support']='supported_empirical_bucket'
        return result
    return features


@contextmanager
def installed_cost_features(profile,model,resolve_family,audit_module=None):
    previous=original_cost.stage_features
    wrapped=adapted_features(previous,profile,model,resolve_family)
    previous_audit=audit_module.stage_features if audit_module is not None else None
    original_cost.stage_features=wrapped
    if audit_module is not None:audit_module.stage_features=wrapped
    try:yield
    finally:
        original_cost.stage_features=previous
        if audit_module is not None:audit_module.stage_features=previous_audit


def build_adapted_gate(args,prepared,calibration,profile,namespace,turn,tenants,prefixes):
    candidate=load_profile(args.cost_profile)
    if args.model_identity not in candidate['active_candidate_models']:
        raise ValueError('No long-input DEV cost calibration for this adapted model')
    family=task_family(prepared[0])
    with installed_cost_features(candidate,args.model_identity,lambda unused:family):
        return original_cost.build_gate(args,prepared,calibration,profile,namespace,turn,tenants,prefixes)
