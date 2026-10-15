from scripts.tsc_revision_r2_benefit_policy import prospective_benefit


def test_blocks_are_converted_to_tokens_and_ms_before_cost_comparison():
    low=prospective_benefit(100,16,2,.1,200,0,2)
    assert low['estimated_saved_ms']==320
    assert not low['allow_verification']
    assert prospective_benefit(100,16,3,.1,200,0,2)['allow_verification']


def test_equal_cost_and_missing_or_nonfinite_features_do_not_trigger_gpu_work():
    assert not prospective_benefit(100,16,1,.125,200,0,1)['allow_verification']
    assert not prospective_benefit(100,16,float('nan'),.1,200,0,1)['allow_verification']
    assert not prospective_benefit(0,16,100,.1,200,0,1)['allow_verification']


def test_complete_cost_envelope_prevents_using_a_partial_http_timer():
    result=prospective_benefit(100,16,1,.125,50,1,1,complete_cost_p95_ms=300)
    assert result['estimated_cost_ms']==300
    assert not result['allow_verification']
