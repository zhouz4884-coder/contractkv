from copy import deepcopy
from scripts.tsc_revision_r2_select_policy import select
from scripts.tsc_revision_live import FROZEN_LEVELS


def test_development_selector_excludes_unsafe_level_and_zero_floor_controls():
    plan={'raw_answer_minimum_margin_grid':[0,.0625],'candidate_answer_and_eos_minimum_margin_grid':[0,.0625],
          'benefit_safety_factor_grid':[1],'selection_declared_tenant_scenarios':[1,10],
          'selection_scenario_weights':[.5,.5],'expected_query_repetitions_per_registered_tenant_hint':3,
          'new_heldout_sessions_sha256':'unseen'}
    data={'slots':[],'latency_predictor_observations':[]}
    mapping={'qwen':'Qwen3-8B','mistral':'Mistral-7B-Instruct-v0.3','llama':'Llama-3.1-8B-Instruct'}
    for key,model in mapping.items():
        for family,maximum in FROZEN_LEVELS[model].items():
            if maximum=='L0':continue
            data['latency_predictor_observations'].append({'model_key':key,'family':family,'native_prefix_hit_tokens':0,'ttft_per_new_prefill_token_ms':1.})
            for level in range(1,int(maximum[1:])+1):
                data['slots'].append({'model_key':key,'family':family,'level':f'L{level}',
                    'verification_rpc_ms':1.,'complete_qualification_ms':2.,'stable_full_blocks':100*level,
                    'planning_ms':.1,'raw_full_min_including_eos':1.,'rank_path_certificate_issued':True,
                    'candidate_answer_min':1.,'candidate_eos_margin':1.,'observed_material_drops':int(level>1)})
    chosen,grid=select(plan,data)
    assert chosen['raw_token_margin_floor']==.0625 and chosen['candidate_token_margin_floor']==.0625
    assert all(c['level'] in ('L0','L1') for families in chosen['models'].values() for c in families.values())
    assert all(not g['eligible_final'] for g in grid if g['raw_floor']==0 or g['candidate_floor']==0)
