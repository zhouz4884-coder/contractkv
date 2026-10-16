"""Recount both score directions in archived revision future-pair tables."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_score_balance import balance


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path('results/tsc_revision_r4/historical_score_balance_v1.json')
    if output.exists():
        raise ValueError('Preserve archived score-balance version')
    datasets = [
        ('R1', 'results/tsc_revision_r1/fresh_token_quality_pairs_v1.csv'),
        ('R1R', 'results/tsc_revision_r1r/validation/summary/quality_pairs_v1.csv'),
        ('R2', 'results/tsc_revision_r2/validation_v1/analysis/quality_pairs_v1.csv'),
        ('R3', 'results/tsc_revision_r3/validation_v1/analysis/quality_pairs_v1.csv'),
    ]
    results = []
    for stage, filename in datasets:
        path = Path(filename)
        with path.open(encoding='utf-8', newline='') as stream:
            original = list(csv.DictReader(stream))
        groups = defaultdict(list)
        for row in original:
            raw_score, policy_score = float(row['raw_score']), float(row['candidate_score'])
            if abs(float(row['quality_drop']) - (raw_score - policy_score)) > 1e-12:
                raise ValueError('Archived signed score mismatch')
            compiled = row.get('request_class') == 'admitted_compiled' if stage == 'R1' else row['effective_level'] != 'L0'
            study = row.get('study', row.get('experiment'))
            condition = 'budget_override_' + row['budget_override'] if stage == 'R1' else 'original_budget'
            policy = row.get('policy', 'original_contractkv')
            record = {'source_group': row.get('source_group', 'session_identifier:' + row['session_id']),
                      'repeat': int(row['repeat']), 'raw_score': raw_score, 'policy_score': policy_score,
                      'delta_score_policy_minus_raw': policy_score - raw_score,
                      'first_output_ID_divergence': int(row['first_diverging_token'])}
            for family in ('ALL', row['family']):
                for route in ('ALL', 'compiled' if compiled else 'L0'):
                    groups[study, row['model'], policy, condition, family, route].append(record)
        records = []
        for key, group in sorted(groups.items()):
            numbers = balance(group, key[4])
            numbers['recorded_source_or_session_identifiers'] = numbers.pop('source_groups')
            records.append(dict(zip(('study', 'model', 'policy', 'condition', 'family', 'route'), key), **numbers))
        results.append({'stage': stage, 'source_pairs_path': path.as_posix(), 'source_pairs_sha256': sha(path),
                        'paired_future_rows': len(original), 'records': records,
                        'source_identifier_boundary': 'R1 table lacks source-group column; session IDs are counted without claiming independence.' if stage == 'R1' else 'Original source-group identifiers retained; requests/repeats remain correlated.'})
    result = {
        'schema_version': 'tsc-revision.historical-paired-score-balance.v1',
        'source_sha256': sha(Path(__file__)),
        'shared_counter_source_sha256': sha(Path('scripts/tsc_revision_r4_score_balance.py')),
        'new_GPU_requests': 0, 'scoring_or_denominators_changed': False,
        'stages': results,
        'limits': [
            'These archived tables contain future-turn pairs, not exhaustive initial tenant turn-zero answers. R4 all-business accounting is separate.',
            'Original budgets, extended budgets, policies and sources remain separate; no pooled causal improvement curve is constructed.',
            'No ALL-family score mean is reported because metrics differ. A better task score does not establish behavioral certification success.',
            'R1 compile-route classification uses recorded admitted_compiled versus raw_fallback labels; later stages use actual effective levels.',
        ],
    }
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'archived_stage_tables': len(results), 'future_pair_rows': sum(r['paired_future_rows'] for r in results), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
