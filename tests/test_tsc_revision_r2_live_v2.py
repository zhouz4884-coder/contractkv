from scripts.tsc_revision_r2_live_v2 import require_witness

def test_one_lp_witness_per_new_scope_keeps_other_business_requests():
    seen=set();key=('template','query')
    assert require_witness('margin-benefit',True,key,True,seen)
    assert not require_witness('margin-benefit',True,key,True,seen)
    assert require_witness('margin-benefit',True,('other','query'),True,seen)
    assert not require_witness('margin-benefit',True,('cold','unprofitable'),False,seen)
    assert not require_witness('margin-benefit',False,('already','certified'),True,seen)

def test_legacy_control_preserves_two_raw_lp_requests():
    seen=set();key=('template','query')
    assert require_witness('legacy-prefix',True,key,True,seen)
    assert require_witness('legacy-prefix',True,key,True,seen)
