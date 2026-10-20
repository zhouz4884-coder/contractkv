from scripts.tsc_behavior_scope_protocol_v2 import actual_prefix_errors
from scripts.phase17_live_common import digest


def test_actual_request_prefix_not_saved_plan_is_hashed():
    ids=list(range(40));cert=dict(stable_prefix_tokens=35,committed_tokens=32,stable_prefix_hash=digest(ids[:35]))
    assert not actual_prefix_errors(ids,cert)
    changed=list(ids);changed[12]=999
    assert actual_prefix_errors(changed,cert)==['actual_certified_prefix_hash_mismatch']
    # A changed private suffix preserves the physical prefix check; Raw
    # behavioral scope remains independently required by the other ledger.
    suffix=list(ids);suffix[38]=999
    assert not actual_prefix_errors(suffix,cert)
    assert actual_prefix_errors(ids,{**cert,'committed_tokens':36})==['actual_certified_prefix_boundary_invalid']


def test_actual_frozen_prefix_same_despite_72_different_business_prompts():
    from tests.test_tsc_template_task_v2 import context
    from scripts.tsc_template_task_protocol_v2 import make_case
    from scripts.phase22_llama_layout_ladder import layout_for_level
    from scripts.tsc_revision_r4_fidelity_adapter_v2 import ordered_text_preserving_segments
    _,_,sample,_,_,_,_=context();prefixes=set();full=set()
    for tenant in range(8):
        for turn in range(9):
            case=make_case(sample,tenant,turn);order=layout_for_level(case,'L3',{'L0':0,'L1':.25,'L2':.75,'L3':1})['topological_order']
            stable=[];byid={s['segment_id']:s for s in case['segments']}
            for sid in order:
                if byid[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}:break
                stable.append(sid)
            prefixes.add(ordered_text_preserving_segments(stable,case['segments']))
            full.add(ordered_text_preserving_segments(order,case['segments']))
    assert len(prefixes)==1 and len(full)==72
