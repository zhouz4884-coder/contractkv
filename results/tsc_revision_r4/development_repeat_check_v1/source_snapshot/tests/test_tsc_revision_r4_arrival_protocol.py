import copy
import json
import pytest
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals


def example():
    return {'schema_version':'tsc-r4.fixed-wave-arrivals.v1','sessions_sha256':'h','tenants_per_template':1,'concurrency':2,
            'actual_business_requests':20,'waves':[{'cohort_start':0,'turn':t,'session_ids':['a','b'],'ready_offset_s':float(t)} for t in range(10)]}


def test_schedule_binds_every_request_and_is_shared_independently_of_policy(tmp_path):
    p=tmp_path/'arrival.json';p.write_text(json.dumps(example()))
    waves,sha,_=load_arrivals(p,'h',['a','b'],1,2)
    assert len(waves)==10 and waves[0,7]['ready_offset_s']==7 and len(sha)==64


@pytest.mark.parametrize('change',('negative','reordered','different_session','wrong_hash','missing','duplicate'))
def test_invalid_schedules_fail_before_generation(tmp_path,change):
    d=copy.deepcopy(example())
    if change=='negative':d['waves'][3]['ready_offset_s']=-1
    if change=='reordered':d['waves'][3]['ready_offset_s']=.5
    if change=='different_session':d['waves'][3]['session_ids']=['a','x']
    if change=='wrong_hash':d['sessions_sha256']='other'
    if change=='missing':d['waves'].pop()
    if change=='duplicate':d['waves'][-1]=d['waves'][0]
    p=tmp_path/'arrival.json';p.write_text(json.dumps(d))
    with pytest.raises(ValueError):load_arrivals(p,'h',['a','b'],1,2)
