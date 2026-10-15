import pytest
from scripts.tsc_revision_r2_margin_policy import minimum_margin_gate


def test_a_single_weak_raw_position_cannot_hide_behind_q05():
    result=minimum_margin_gate([1.0]*12+[0.0]+[1.0]*87,[1.0]*100,2.0,.0625,.0625)
    assert not result['passed']
    assert result['raw_margin_min_index']==12
    assert result['reason']=='raw_token_margin_below_floor'


def test_candidate_answer_and_stop_both_need_margin():
    assert not minimum_margin_gate([1.0]*2,[1.0,0.0],2.0,.0625,.0625)['passed']
    assert not minimum_margin_gate([1.0]*2,[1.0,1.0],0.0,.0625,.0625)['passed']
    assert minimum_margin_gate([.0625]*2,[.0625]*2,.0625,.0625,.0625)['passed']


@pytest.mark.parametrize('raw,candidate,stop', [([],[],1.0),([1.0],[1.0,1.0],1.0),([float('nan')],[1.0],1.0),([1.0],[float('inf')],1.0),([1.0],[1.0],float('nan'))])
def test_incomplete_or_nonfinite_evidence_is_rejected(raw,candidate,stop):
    assert not minimum_margin_gate(raw,candidate,stop)['passed']


def test_disabled_floors_preserve_finite_near_tie_control():
    assert minimum_margin_gate([0.0],[0.0],0.0)['passed']
