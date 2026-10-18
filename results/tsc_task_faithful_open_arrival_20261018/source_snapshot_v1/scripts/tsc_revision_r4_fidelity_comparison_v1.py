"""Post-hoc four-grid development accounting; no model calls or rule changes.

Compare raw/policy within each frozen input condition, then compare the two
raw input conditions by the same source/request positions. The latter changes
both packing and contiguous rendering, and cannot isolate their causal effects.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    with Path(path).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def empirical_percentile(values, fraction):
    values = sorted(values)
    offset = (len(values) - 1) * fraction
    lower = int(offset)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (offset - lower)


def score_summary(pairs):
    deltas = [second['task_score'] - first['task_score'] for first, second in pairs]
    return {
        'pairs': len(pairs),
        'first_mean_task_score': mean(first['task_score'] for first, _ in pairs),
        'second_mean_task_score': mean(second['task_score'] for _, second in pairs),
        'first_positive_score_answers': sum(first['task_score'] > 0 for first, _ in pairs),
        'second_positive_score_answers': sum(second['task_score'] > 0 for _, second in pairs),
        'thresholds': [
            {'threshold': threshold,
             'second_score_higher': sum(delta > threshold for delta in deltas),
             'second_score_lower': sum(delta < -threshold for delta in deltas),
             'within_threshold': sum(abs(delta) <= threshold for delta in deltas)}
            for threshold in (0, .01, .03, .05)],
        'first_output_tokens': sum(len(first['output_token_ids']) for first, _ in pairs),
        'second_output_tokens': sum(len(second['output_token_ids']) for _, second in pairs),
        'first_length_stops': sum(first['finish_reason'] == 'length' for first, _ in pairs),
        'second_length_stops': sum(second['finish_reason'] == 'length' for _, second in pairs),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=Path('results/tsc_revision_r4'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve every development analysis version')
    result = {'schema_version': 'tsc-r4.task-fidelity-four-grid-comparison.v1',
              'analysis_source_sha256': sha(__file__), 'new_GPU_requests': 0,
              'added_after_primary_freeze': True, 'scoring_or_admission_changed': False,
              'conditions': [], 'raw_input_condition_comparisons': [],
              'limitations': [
                  'Four previously observed sources, two per family, one fresh process per cell; development only.',
                  'Tenants and repeated query wrappers are correlated; no independent test or process confidence interval.',
                  'Input repair combines label-blind packing and contiguous segment rendering; their effects are not separated.',
                  'Raw/policy score differences do not establish strict behavioral equivalence, including improvements.',
                  'Full service wall is end-to-end; summed qualification RPC time is descriptive work, not additive critical path.',
              ]}
    tables = {}
    for condition in ('head', 'faithful'):
        root = args.base / f'input_fidelity_development_{condition}_v3'
        freeze = json.loads((root / 'freeze.json').read_text(encoding='utf-8'))
        audit = json.loads((root / 'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
        if not audit['execution_complete'] or audit['complete_cells'] != 2:
            raise ValueError('Complete both frozen paired cells before four-grid interpretation')
        config = freeze['protocol']
        cells = {}
        for policy in ('raw-order', 'risk-tail'):
            cell = root / 'cells' / f'template-fanout_qwen_{policy}_r1'
            summary = json.loads((cell / 'summary.json').read_text(encoding='utf-8'))
            if not summary['execution_complete'] or sha(cell / 'raw.jsonl') != summary['raw_file_sha256']:
                raise ValueError('Incomplete or changed cell')
            rows = read(cell / 'raw.jsonl')
            business = [row for row in rows if row['row_type'] in ('warm', 'future')]
            by_key = {(row['session_id'], row['turn_id']): row for row in business}
            if len(by_key) != len(business) or len(business) != config['expected_actual_generations'] // 2:
                raise ValueError('Complete unique business population required')
            cells[policy] = {'summary': summary, 'rows': rows, 'business': business, 'by_key': by_key}
        raw, policy = cells['raw-order'], cells['risk-tail']
        if set(raw['by_key']) != set(policy['by_key']):
            raise ValueError('Within-condition request populations differ')
        tables[condition] = cells
        entry = {
            'condition': condition, 'freeze_sha256': sha(root / 'freeze.json'),
            'raw_file_sha256': raw['summary']['raw_file_sha256'],
            'policy_file_sha256': policy['summary']['raw_file_sha256'],
            'raw_full_wall_s': raw['summary']['wall_s_including_all_setup_and_verification'],
            'policy_full_wall_s': policy['summary']['wall_s_including_all_setup_and_verification'],
            'full_wall_throughput_ratio': raw['summary']['wall_s_including_all_setup_and_verification'] / policy['summary']['wall_s_including_all_setup_and_verification'],
            'GPU_qualification_calls': policy['summary']['verification_calls'],
            'qualification_RPC_ms_sum': policy['summary']['verification_ms_total'],
            'scope_failure_reasons': dict(Counter(row['failure_reason'] for row in policy['rows'] if row['row_type'] == 'verification' and not row['certificate_issued'])),
            'pre_gate_denial_reasons': dict(Counter(row['reason'] for row in policy['rows'] if row['row_type'] == 'prospective_plan' and not row['allow_verification'])),
            'family_populations': [],
        }
        for family in sorted({row['family'] for row in raw['business']}):
            for population in ('all_business', 'future', 'warm'):
                pairs = [(first, policy['by_key'][key]) for key, first in raw['by_key'].items()
                         if first['family'] == family and (population == 'all_business' or first['row_type'] == population)]
                compiled = [(first, second) for first, second in pairs if second['effective_level'] != 'L0']
                entry['family_populations'].append({
                    'family': family, 'population': population, **score_summary(pairs),
                    'compiled_pairs': len(compiled),
                    'compiled_output_ID_divergences': sum(first['output_token_ids'] != second['output_token_ids'] for first, second in compiled),
                    'compiled_any_score_decrease': sum(second['task_score'] < first['task_score'] for first, second in compiled),
                    'raw_readiness_TTFT_p99_ms': empirical_percentile([first['ready_ttft_ms'] for first, _ in pairs], .99),
                    'policy_readiness_TTFT_p99_ms': empirical_percentile([second['ready_ttft_ms'] for _, second in pairs], .99),
                    'raw_new_prefill_tokens': sum(first['new_prefill_tokens'] for first, _ in pairs),
                    'policy_new_prefill_tokens': sum(second['new_prefill_tokens'] for _, second in pairs),
                })
        result['conditions'].append(entry)
    old, faithful = tables['head']['raw-order']['by_key'], tables['faithful']['raw-order']['by_key']
    if set(old) != set(faithful):
        raise ValueError('Cross-condition raw source/request populations differ')
    for key in old:
        assert old[key]['source_group'] == faithful[key]['source_group']
        assert old[key]['family'] == faithful[key]['family']
        assert old[key]['task_metric'] == faithful[key]['task_metric']
    for family in sorted({row['family'] for row in old.values()}):
        for population in ('all_business', 'future'):
            pairs = [(first, faithful[key]) for key, first in old.items()
                     if first['family'] == family and (population == 'all_business' or first['row_type'] == population)]
            result['raw_input_condition_comparisons'].append({
                'first_condition': 'head', 'second_condition': 'faithful',
                'family': family, 'population': population, **score_summary(pairs),
                'source_groups': sorted({first['source_group'] for first, _ in pairs}),
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'four_grid_complete': True, 'new_GPU_requests': 0,
                      'conditions': [{'condition': row['condition'], 'full_wall_ratio': row['full_wall_throughput_ratio']}
                                     for row in result['conditions']]}))


if __name__ == '__main__':
    main()
