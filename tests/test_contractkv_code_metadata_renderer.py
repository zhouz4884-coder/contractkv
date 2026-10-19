from copy import deepcopy
from scripts.contractkv_code_metadata_renderer import ordered_text_code_metadata_comments as clean
from scripts.tsc_revision_r4_fidelity_adapter_v2 import ordered_text_preserving_segments as current


def test_only_framework_heading_and_filename_metadata_change_code_body_is_exact():
    body = 'def f(x):\n    s = "[CODE_PREFIX:literal-inside-source]"\n    return x + 1\n'
    segments = [dict(segment_id='r', segment_type='REPO_CONTEXT', text='# Repository\ncontext'),
                dict(segment_id='c', segment_type='CODE_PREFIX', text='pkg/file.py\n' + body),
                dict(segment_id='q', segment_type='USER_QUERY', text='Complete the next line of code.')]
    before = deepcopy(segments)
    observed = clean(['r', 'c', 'q'], segments)
    expected = current(['r', 'c', 'q'], segments).replace('[CODE_PREFIX:c]\npkg/file.py\n', '# Path: pkg/file.py\n', 1)
    assert observed == expected and '# Path: pkg/file.py\n' + body in observed
    assert '[CODE_PREFIX:literal-inside-source]' in observed
    assert segments == before


def test_contiguous_piece_grouping_preserves_exact_original_code_text():
    segments = [dict(segment_id='c__p0', segment_type='CODE_PREFIX', text='path.py\nfoo('),
                dict(segment_id='c__p1', segment_type='CODE_PREFIX', text='\n    bar,\n'),
                dict(segment_id='c__p2', segment_type='CODE_PREFIX', text=')\n')]
    assert clean([s['segment_id'] for s in segments], segments) == '# Path: path.py\nfoo(\n    bar,\n)\n'


def test_later_nonconsecutive_code_piece_is_never_reclassified_as_metadata():
    segments = [dict(segment_id='c__p9', segment_type='CODE_PREFIX', text='data.py\nactual_source')]
    assert clean(['c__p9'], segments) == 'data.py\nactual_source'


def test_all_non_code_prompt_structure_is_byte_identical():
    segments = [dict(segment_id='s', segment_type='SYS_PROMPT', text='rules'),
                dict(segment_id='o', segment_type='TOOL_OBS', text='private metadata'),
                dict(segment_id='q', segment_type='USER_QUERY', text='question')]
    assert clean(['s', 'o', 'q'], segments) == current(['s', 'o', 'q'], segments)
