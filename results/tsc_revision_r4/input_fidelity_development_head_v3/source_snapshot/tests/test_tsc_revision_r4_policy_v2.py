from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract

CASE={'segments':[{'segment_id':'s1','segment_type':'CONTEXT','text':'Eliza preferred spending time with her son. The daughter was neglected.'},
                  {'segment_id':'s2','segment_type':'TOOL_OBS','text':'turn=1'}]}


def test_short_supported_inference_is_not_forced_to_be_verbatim():
    answer='Eliza favors her son over her daughter.'
    result=reference_scope_contract(CASE,answer,raw_margins=[.5,1,2])
    assert result['shareable_query_scope'] and result['matched_context_span'] is None
    assert not result['served_output_rewritten'] and not result['uses_gold_labels']


def test_nonliteral_ambiguous_and_generic_denial_remain_observation_scoped():
    for margins in ([.125,.4],[.1,.4],None):
        assert not reference_scope_contract(CASE,'Eliza favors her son.',raw_margins=margins)['shareable_query_scope']
    for answer in ('The character Virgil is not mentioned in the provided context.',
                   'The answer is not available in the given context.',
                   'I cannot determine this from the context.'):
        assert not reference_scope_contract(CASE,answer,raw_margins=[5,6])['shareable_query_scope']


def test_literal_answer_does_not_silently_raise_original_backend_floor():
    result=reference_scope_contract(CASE,'Eliza',raw_margins=[.09375,1])
    assert result['shareable_query_scope']
    # The separate original raw minimum/EOS gate still applies before publication.
