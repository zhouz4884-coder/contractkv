"""Report both directions of frozen paired score changes and ID divergence."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import first_divergence


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_business(path):
    result = {}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['row_type'] in ('warm', 'future'):
                result[row['session_id'], row['turn_id']] = row
    return result


def balance(group, family):
    deltas = [r['delta_score_policy_minus_raw'] for r in group]
    result = {
        'pairs': len(group), 'source_groups': len({r['source_group'] for r in group}),
        'fresh_repeats': len({r['repeat'] for r in group}),
        'any_score_increase': sum(v > 0 for v in deltas),
        'any_score_decrease': sum(v < 0 for v in deltas),
        'exact_score_equal': sum(v == 0 for v in deltas),
        'output_ID_divergences': sum(r['first_output_ID_divergence'] != -1 for r in group),
        'ID_divergence_with_score_increase': sum(r['first_output_ID_divergence'] != -1 and r['delta_score_policy_minus_raw'] > 0 for r in group),
        'ID_divergence_with_score_decrease': sum(r['first_output_ID_divergence'] != -1 and r['delta_score_policy_minus_raw'] < 0 for r in group),
        'ID_divergence_with_equal_score': sum(r['first_output_ID_divergence'] != -1 and r['delta_score_policy_minus_raw'] == 0 for r in group),
        'raw_mean_score': statistics.fmean(r['raw_score'] for r in group) if family != 'ALL' else None,
        'policy_mean_score': statistics.fmean(r['policy_score'] for r in group) if family != 'ALL' else None,
        'thresholds': [],
    }
    for threshold in (.01, .03, .05):
        up = sum(v > threshold for v in deltas)
        down = sum(v < -threshold for v in deltas)
        result['thresholds'].append({'threshold': threshold, 'material_increase': up,
                                     'material_decrease': down, 'no_material_change': len(group) - up - down})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-partial', action='store_true')
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve score-balance supplement version')
    if not a.allow_partial:
        complete = json.loads((a.root / 'analysis/completion_audit_v1.json').read_text())
        if not complete['execution_complete']:
            raise ValueError('Complete primary study required')
    pairs = []
    provenance = []
    for path in sorted((a.root / 'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text(encoding='utf-8'))
        if summary['policy'] == 'raw-order':
            continue
        raw_name = path.parent.name.replace('_' + summary['policy'] + '_', '_raw-order_')
        raw_path = path.parent.parent / raw_name / 'raw.jsonl'
        if not raw_path.exists():
            if a.allow_partial:
                continue
            raise ValueError('Missing paired raw')
        policy_path = path.with_name('raw.jsonl')
        for file in (raw_path, policy_path):
            meta = json.loads(file.with_name('summary.json').read_text(encoding='utf-8'))
            if not meta['execution_complete'] or sha(file) != meta['raw_file_sha256']:
                raise ValueError('Changed or incomplete measured cell')
        raw, policy = read_business(raw_path), read_business(policy_path)
        if raw.keys() != policy.keys():
            raise ValueError('Incomplete paired business set')
        for key, row in policy.items():
            ref = raw[key]
            if row['effective_level'] == 'L0' and ref['prompt_token_ids'] != row['prompt_token_ids']:
                raise ValueError('Actual L0 prompt IDs differ')
            pairs.append({
                'study': summary['study'], 'model': row['model'], 'policy': summary['policy'],
                'repeat': summary['repeat'], 'row_type': row['row_type'],
                'source_group': row['source_group'], 'session_id': key[0], 'turn_id': key[1],
                'family': row['family'], 'route': 'compiled' if row['effective_level'] != 'L0' else 'L0',
                'raw_score': ref['task_score'], 'policy_score': row['task_score'],
                'delta_score_policy_minus_raw': row['task_score'] - ref['task_score'],
                'first_output_ID_divergence': first_divergence(ref['output_token_ids'], row['output_token_ids']),
                'raw_output_tokens': len(ref['output_token_ids']), 'policy_output_tokens': len(row['output_token_ids']),
                'raw_finish_reason': ref['finish_reason'], 'policy_finish_reason': row['finish_reason'],
            })
        provenance.append({'cell': path.parent.name, 'raw_sha256': sha(raw_path), 'policy_sha256': sha(policy_path)})
    groups = defaultdict(list)
    source_groups = defaultdict(list)
    for row in pairs:
        for population in ('all_business', row['row_type']):
            for family in ('ALL', row['family']):
                for route in ('ALL', row['route']):
                    groups[row['study'], row['model'], row['policy'], population, family, route].append(row)
        source_groups[row['study'], row['model'], row['policy'], row['source_group'], row['family'], row['route']].append(row)
    records = [dict(zip(('study', 'model', 'policy', 'population', 'family', 'route'), key), **balance(group, key[4]))
               for key, group in sorted(groups.items())]
    source_records = [dict(zip(('study', 'model', 'policy', 'source_group', 'family', 'route'), key), **balance(group, key[4]))
                      for key, group in sorted(source_groups.items())]
    result = {
        'schema_version': 'tsc-r4.paired-score-balance.v1', 'partial': a.allow_partial,
        'source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(a.root / 'freeze.json'),
        'new_GPU_requests': 0, 'scoring_changed': False,
        'paired_cells': len(provenance), 'all_business_pairs': len(pairs),
        'records': records, 'source_records': source_records, 'cell_provenance': provenance,
        'all_material_change_cases_gt0_03': [r for r in pairs if abs(r['delta_score_policy_minus_raw']) > .03],
        'interpretation': [
            'Delta is policy score minus matched raw score. Strict >tau and <-tau thresholds preserve the original material-effect convention.',
            'Both improvements and regressions are retained. No material change at tau does not imply identical outputs or behavioral equivalence.',
            'A compiled output-ID difference remains a behavioral divergence even when task score improves. Certification is not evaluated as an answer-optimization method.',
            'ALL-family score means are deliberately omitted because benchmark metrics differ. Per-family means use unchanged recorded scores checked in primary/all-business audits.',
            'All-business includes tenant turn-zero reuse; future primary outcomes remain separately identified. Source records preserve clustering and do not imply independent request events.',
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'paired_cells': len(provenance), 'business_pairs': len(pairs),
                      'material_increases': sum(r['delta_score_policy_minus_raw'] > .03 for r in pairs),
                      'material_decreases': sum(r['delta_score_policy_minus_raw'] < -.03 for r in pairs),
                      'partial': a.allow_partial, 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
