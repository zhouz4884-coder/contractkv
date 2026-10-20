"""Task-fidelity renderer with contiguous original text inside each segment.

CALC's nodes, order, levels and dependencies are unchanged. Only consecutive
pieces of the same original segment share one external heading, so metadata is
not injected between code tokens or in the middle of a document paragraph.
"""
from contextlib import contextmanager
from importlib import import_module
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text as historical_ordered_text
from scripts.tsc_revision_r4_fidelity_adapter import build_faithful_case, historical_build_case


ADAPTER_VERSION = 'task-fidelity-contiguous-segment-text-v2'
RENDER_BINDINGS = ('scripts.tsc_revision_live', 'scripts.tsc_revision_r1r_live',
                   'scripts.tsc_revision_r4_live', 'scripts.tsc_revision_r2_candidate_plan')


def piece_identity(segment_id):
    base, separator, suffix = str(segment_id).rpartition('__p')
    return (base, int(suffix)) if separator and suffix.isdigit() else (str(segment_id), None)


def ordered_text_preserving_segments(order, segments):
    by_id = {str(segment['segment_id']): segment for segment in segments}
    blocks = []
    group = []

    def flush():
        if group:
            first = group[0]
            base, index = piece_identity(first['segment_id'])
            heading_id = base if index == 0 else first['segment_id']
            blocks.append(f"[{first['segment_type']}:{heading_id}]\n" + ''.join(segment['text'] for segment in group))
            group.clear()

    for segment_id in order:
        segment = by_id[str(segment_id)]
        base, index = piece_identity(segment_id)
        previous_base, previous_index = piece_identity(group[-1]['segment_id']) if group else (None, None)
        consecutive = bool(group and index is not None and previous_index is not None and
                           base == previous_base and index == previous_index + 1 and
                           segment['segment_type'] == group[-1]['segment_type'])
        if not consecutive:
            flush()
        group.append(segment)
    flush()
    return '\n\n'.join(blocks)


@contextmanager
def installed_adapter():
    modules = [import_module(name) for name in RENDER_BINDINGS]
    original = modules[0]
    if original.build_case is not historical_build_case or any(module._ordered_text is not historical_ordered_text for module in modules):
        raise RuntimeError('An undeclared renderer or builder adapter is already installed')
    original.build_case = build_faithful_case
    for module in modules:
        module._ordered_text = ordered_text_preserving_segments
    try:
        yield
    finally:
        for module in modules:
            module._ordered_text = historical_ordered_text
        original.build_case = historical_build_case
