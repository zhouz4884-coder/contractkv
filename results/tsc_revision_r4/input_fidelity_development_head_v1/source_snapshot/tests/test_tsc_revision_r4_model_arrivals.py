from scripts.tsc_revision_r4_make_arrivals_v2 import model_trace


def test_same_relative_jitter_but_model_specific_declared_load():
    samples=[{'revision_session_id':'a','revision_family':'A'},{'revision_session_id':'b','revision_family':'A'}]
    fast=model_trace(samples,'sha',1,{'A':1.},1,'fast')
    slow=model_trace(samples,'sha',1,{'A':4.},1,'slow')
    assert fast['common_across_policies_within_model'] and not fast['common_across_models_and_policies']
    assert fast['nominal_offered_load']==slow['nominal_offered_load']==.8
    assert fast['waves'][1]['ready_offset_s']*4==slow['waves'][1]['ready_offset_s']
    assert [w['session_ids'] for w in fast['waves']]==[w['session_ids'] for w in slow['waves']]
    assert fast==model_trace(samples,'sha',1,{'A':1.},1,'fast')
