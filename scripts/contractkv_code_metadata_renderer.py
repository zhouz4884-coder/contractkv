"""Task-aware metadata formatting; original code bytes stay in the manifest.

Only framework CODE_PREFIX headings and its leading filename metadata change
in model-visible text. All other headings, code, whitespace and order remain.
"""
import re
from scripts.tsc_revision_r4_fidelity_adapter_v2 import piece_identity


def ordered_text_code_metadata_comments(order, segments):
    by_id = {str(segment['segment_id']): segment for segment in segments}
    blocks, group = [], []
    def flush():
        if not group:
            return
        first = group[0]
        base, index = piece_identity(first['segment_id'])
        heading_id = base if index == 0 else first['segment_id']
        text = ''.join(segment['text'] for segment in group)
        if first['segment_type'] == 'CODE_PREFIX':
            # The extractor prepends filename metadata; do not mistake an
            # arbitrary later code fragment for a filename or regex-edit body.
            head, separator, rest = text.partition('\n')
            if index in (None, 0) and separator and re.fullmatch(r'[A-Za-z0-9_./\\-]+\.py', head.strip()):
                text = '# Path: ' + head + '\n' + rest
            blocks.append(text)
        else:
            blocks.append(f"[{first['segment_type']}:{heading_id}]\n" + text)
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
