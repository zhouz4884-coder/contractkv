import hashlib
import json
from scripts.tsc_revision_r4_make_arrivals import make_trace
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals


def test_trace_deterministic_and_bound_to_full_expanded_membership(tmp_path):
    samples=[{'revision_session_id':'a','revision_family':'A'},{'revision_session_id':'b','revision_family':'B'}]
    one=make_trace(samples,'abc',10,2,{'A':1.,'B':2.},1)
    assert one==make_trace(samples,'abc',10,2,{'A':1.,'B':2.},1)
    assert one!=make_trace(samples,'abc',10,2,{'A':1.,'B':2.},2)
    dest=tmp_path/'trace.json';dest.write_text(json.dumps(one))
    ids=[s['revision_session_id']+f'-tenant{t:02d}' for s in samples for t in range(10)]
    waves,_,_=load_arrivals(dest,'abc',ids,10,2)
    assert len(waves)==100 and one['actual_business_requests']==200
    assert waves[0,0]['ready_offset_s']==0


def test_slow_member_controls_mixed_cohort_gap():
    samples=[{'revision_session_id':'a','revision_family':'A'},{'revision_session_id':'b','revision_family':'B'}]
    trace=make_trace(samples,'abc',1,2,{'A':1.,'B':4.},1)
    assert all(r['nominal_service_s']==4 for r in trace['waves'])
    assert 4/.8*.9<=trace['waves'][1]['ready_offset_s']<=4/.8*1.1
