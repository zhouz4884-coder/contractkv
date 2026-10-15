import pytest
from scripts.tsc_revision_r2_warm_summary import warm_pair


def sample(ids):
    return {'prompt_token_ids':ids,'output_token_ids':[8,9],'score':.5,'text':'answer'}


def test_same_salt_name_is_not_actual_reuse_evidence():
    row=sample([1,2]); q={'response':{'certificate_issued':True,'committed_tokens':16}}
    result=warm_pair(row,row,row,q,{'prefix_hit_tokens':0})
    assert not result['qualified_reuse_exercised']
    assert warm_pair(row,row,row,q,{'prefix_hit_tokens':16})['qualified_reuse_exercised']


def test_prompt_changes_cannot_be_attributed_to_cache_state():
    with pytest.raises(ValueError):
        warm_pair(sample([1]),sample([1]),sample([2]),{'response':{'certificate_issued':True}},{'prefix_hit_tokens':16})
