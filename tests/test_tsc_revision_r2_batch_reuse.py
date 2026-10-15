from copy import deepcopy
import pytest
from scripts.tsc_revision_r2_batch_reuse import twin_payload


def test_twin_changes_only_the_controlled_tenant_field_and_cold_namespace():
    payload={'request_id':'a-future-cold','cache_salt':'scope','messages':[
        {'role':'system','content':'same system'},
        {'role':'user','content':'context\n[PRIVATE_TOOL_OBS] revision_session=r1r-abc-tenant08; turn=9; status=ready; no additional answer evidence.\nquestion'}]}
    prior=deepcopy(payload); twin=twin_payload(payload)
    assert payload==prior
    assert 'tenant09' in twin['messages'][1]['content']
    assert twin['messages'][0]==payload['messages'][0]
    assert twin['cache_salt']=='scope-twin'
    payload['request_id']='a-future-certified_salt'
    assert twin_payload(payload)['cache_salt']=='scope'


def test_uncontrolled_metadata_is_rejected():
    with pytest.raises(ValueError):
        twin_payload({'request_id':'x','cache_salt':'s','messages':[{'content':'no controlled field'}]})
