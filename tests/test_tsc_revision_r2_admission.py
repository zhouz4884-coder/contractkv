from types import SimpleNamespace
from scripts.phase17_live_common import digest
from scripts.tsc_revision_r2_admission import SingleShotRegistrar


def fixture():
    args=SimpleNamespace(cell_id='test',base_url='http://127.0.0.1:1/v1',policy_hash='p',timeout=1)
    business={'witness_available':True,'output_token_ids':[99,2],'reference_margins':[1.,2.],
              'finish_reason':'stop','prompt_ids_sha256':digest([7])}
    plan={'level':'L2','prompt_token_ids':list(range(32)),'stable_prefix_end_token':16,
          'stable_content_hash':'h','layout_hash':'l','dependency_graph_hash':'d','cpu_http_preparation_ms':1.}
    return args,business,{'allow_verification':True,'reason':'pass','plan':plan}


def test_near_tie_and_unprofitable_scopes_make_no_gpu_call():
    calls=[];registrar=SingleShotRegistrar(.0625,.0625,lambda *args:calls.append(args))
    args,business,gate=fixture();business['reference_margins'][0]=0.
    result=registrar.register(args,'namespace','q1',business,gate)
    assert not result['certificate_issued'] and calls==[]
    args,business,gate=fixture();gate['allow_verification']=False
    result=registrar.register(args,'namespace','q2',business,gate)
    assert not result['certificate_issued'] and calls==[]


def test_failed_single_shot_never_descends_or_retries_same_scope():
    calls=[]
    def reject(*args):
        calls.append(args)
        return {'certificate_issued':False,'committed_tokens':0,'failure_reason':'test_reject'}
    registrar=SingleShotRegistrar(.0625,.0625,reject);args,business,gate=fixture()
    first=registrar.register(args,'namespace','q',business,gate)
    second=registrar.register(args,'namespace','q',business,gate)
    assert len(calls)==1
    assert first is second and first['selected_level']=='L0'
    assert len(first['attempts'])==1 and first['attempts'][0]['level']=='L2'


def test_raw_eos_near_tie_and_indeterminate_rpc_are_explicit():
    calls=[]
    def broken(*values):
        calls.append(values);raise TimeoutError('observation unavailable')
    args,business,gate=fixture();registrar=SingleShotRegistrar(.0625,.0625,broken)
    business['reference_margins'][-1]=0.
    assert registrar.register(args,'n','eos',business,gate)['attempts']==[]
    assert calls==[]
    business['reference_margins'][-1]=1.
    result=registrar.register(args,'n','rpc',business,gate)
    assert len(calls)==1 and result['verification_status']=='indeterminate_request_failure'


def test_unsafe_server_commit_is_fatal_and_full_request_precedes_post():
    import pytest
    log=[]
    def rejected_but_published(*values):
        assert log[-1]['row_type']=='verification_request'
        assert log[-1]['prompt_ids_sha256']==digest(values[1]['prompt_token_ids'])
        return {'certificate_issued':False,'committed_tokens':16}
    args,business,gate=fixture();registrar=SingleShotRegistrar(.0625,.0625,rejected_but_published)
    with pytest.raises(RuntimeError,match='published'):
        registrar.register(args,'n','q',business,gate,record=log.append)
