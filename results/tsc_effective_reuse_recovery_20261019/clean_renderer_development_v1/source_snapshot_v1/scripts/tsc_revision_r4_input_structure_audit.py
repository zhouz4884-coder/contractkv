"""Offline segment/cursor retention audit of frozen head-capped inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve input-structure audit version')
    freeze_path = a.root / 'freeze.json'
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    config = freeze['protocol']
    source = Path('scripts/phase13b_fresh_policy_quality_replay.py')
    expected = next(r['sha256'] for r in freeze['files'] if r['path'] == source.as_posix())
    if sha(source) != expected:
        raise ValueError('Renderer differs from frozen source')
    generation = json.loads((a.root / 'source_snapshot' / config['generation_protocol']).read_text(encoding='utf-8'))
    input_path = a.root / 'source_snapshot' / config['input_files']['single-session']
    records = []
    for line in input_path.open(encoding='utf-8'):
        sample = json.loads(line)
        original = [r for r in sample['segments'] if r['type'] not in ('SYS_PROMPT', 'USER_QUERY')]
        case = build_case(sample, generation['layout']['stable_word_limit'])
        retained = [r for r in case['segments'] if r['segment_type'] not in ('SYS_PROMPT', 'USER_QUERY', 'TOOL_OBS')]
        if len(original) != len(retained):
            raise ValueError('Unexpected segment alignment')
        for index, (before, after) in enumerate(zip(original, retained)):
            if before['type'] != after['segment_type']:
                raise ValueError('Segment type alignment differs')
            text, kept = before['text'], after['text']
            words, kept_words = text.split(), kept.split()
            status = ('empty_after_cap' if words and not kept_words else
                      'partial_word_prefix' if len(kept_words) < len(words) else 'all_words_retained')
            tail = min(32, len(words))
            records.append({
                'source_group': sample['revision_source_group'], 'namespace': sample['revision_session_id'],
                'family': sample['revision_family'], 'segment_index': index, 'segment_type': before['type'],
                'original_words': len(words), 'retained_words': len(kept_words), 'retention_status': status,
                'original_newlines': text.count('\n'), 'retained_newlines': kept.count('\n'),
                'original_indented_nonempty_lines': sum(bool(row.strip()) and row[:1].isspace() for row in text.splitlines()),
                'retained_indented_nonempty_lines': sum(bool(row.strip()) and row[:1].isspace() for row in kept.splitlines()),
                'text_bytes_unchanged': text == kept,
                'last_up_to_32_words_equal': bool(tail and kept_words[-tail:] == words[-tail:]),
                'original_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'retained_text_sha256': hashlib.sha256(kept.encode()).hexdigest(),
            })
    code = [r for r in records if r['segment_type'] == 'CODE_PREFIX']
    result = {
        'schema_version': 'tsc-r4.frozen-input-segment-retention.v1',
        'source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(freeze_path),
        'input_sha256': sha(input_path), 'renderer_sha256': expected,
        'new_GPU_requests': 0, 'labels_used': False, 'input_changed': False,
        'sources': len({r['source_group'] for r in records}), 'segment_records': records,
        'code_prefix_records': len(code),
        'code_prefix_retention': dict(Counter(r['retention_status'] for r in code)),
        'code_prefixes_with_original_newlines_and_no_retained_newlines': sum(r['original_newlines'] > 0 and r['retained_newlines'] == 0 for r in code),
        'interpretation': [
            'The inherited cap is consumed sequentially by stored segments; later code prefixes can become empty or retain only their head. Full word retention still collapses original newlines and indentation.',
            'This records input adaptation, not a semantic task-correctness or causal generation diagnosis. No missing source is removed and no prompt is repaired.',
            'CODE_PREFIX byte/word retention is distinct from reference-answer presence: next-line completion targets need not already occur in the prefix.',
            'The frozen R4 cohort remains a benchmark-derived controlled workload; these structural losses limit claims about normal code-completion service utility.',
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ['sources', 'code_prefix_records', 'code_prefix_retention', 'code_prefixes_with_original_newlines_and_no_retained_newlines', 'new_GPU_requests']}))


if __name__ == '__main__':
    main()
