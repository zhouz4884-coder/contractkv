import pytest
from scripts.tsc_revision_r2_diagnose import check_prompt_ids, forced_rows


def test_actual_prompt_echo_is_required():
    with pytest.raises(ValueError):
        check_prompt_ids({'prompt_token_ids':[1,3]},[1,2],True)
    with pytest.raises(ValueError):
        check_prompt_ids({},[1,2],True)


def test_full_control_checks_answer_and_stop_positions():
    response={'choices':[{'prompt_token_ids':[7,8,9], 'prompt_logprobs':[
        None, {'8':{'rank':1,'logprob':-.1},'99':{'rank':2,'logprob':-.3}},
        {'9':{'rank':2,'logprob':-.4},'99':{'rank':1,'logprob':-.2}}]}]}
    rows=forced_rows(response,[7],[8],9)
    assert [r['position'] for r in rows]==[1,2]
    assert [r['rank'] for r in rows]==[1,2]
    assert rows[-1]['is_stop']
    assert rows[-1]['margin']<0


def test_missing_forced_rows_cannot_count_as_a_pass():
    with pytest.raises(ValueError):
        forced_rows({'choices':[{'prompt_token_ids':[7,8,9], 'prompt_logprobs':[]}]},[7],[8],9)
