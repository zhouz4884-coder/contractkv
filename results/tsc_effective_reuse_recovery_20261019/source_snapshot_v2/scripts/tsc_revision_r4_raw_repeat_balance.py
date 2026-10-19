"""All-request raw-repeat variability and matched L0 descriptive controls.

Unlike the selected-failure audit, this includes requests with improvements,
regressions and unchanged scores. Three pairwise raw comparisons are correlated.
"""
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(path):
    summary = json.loads((path/'summary.json').read_text(encoding='utf-8'))
    if not summary['execution_complete'] or sha(path/'raw.jsonl') != summary['raw_file_sha256']:
        raise ValueError('Complete immutable cell required')
    runtime = json.loads((path/'runtime_manifest.json').read_text(encoding='utf-8'))
    result = {}
    with (path/'raw.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['row_type'] not in ('warm', 'future'):
                continue
            if digest(row['prompt_token_ids']) != row['prompt_ids_sha256']:
                raise ValueError('Actual prompt-ID hash mismatch')
            result[row['session_id'], row['turn_id']] = {
                'source_group': row['source_group'], 'family': row['family'], 'row_type': row['row_type'],
                'prompt_hash': row['prompt_ids_sha256'], 'output_hash': digest(row['output_token_ids']),
                'output_tokens': len(row['output_token_ids']), 'score': row['task_score'],
                'finish': row['finish_reason'], 'route': row['effective_level'],
                'prefix_hit_tokens': row['prefix_hit_tokens']}
    return summary, runtime['declared_gpu_lane'], result


def summary(rows):
    return {'pairs': len(rows), 'sources': len({r['source_group'] for r in rows}),
            'output_ID_divergences': sum(r['output_IDs_differ'] for r in rows),
            'same_prefix_hit_count': sum(r['same_prefix_hit_count'] for r in rows),
            'first_length_stop': sum(r['first_finish'] == 'length' for r in rows),
            'second_length_stop': sum(r['second_finish'] == 'length' for r in rows),
            'second_large_length_inflations': sum(r['second_tokens'] >= 4*max(r['first_tokens'], 1) and r['second_tokens']-r['first_tokens'] >= 128 for r in rows),
            'first_large_length_inflations': sum(r['first_tokens'] >= 4*max(r['second_tokens'], 1) and r['first_tokens']-r['second_tokens'] >= 128 for r in rows),
            'thresholds': [{'threshold': threshold,
                            'second_score_higher': sum(r['delta_second_minus_first'] > threshold for r in rows),
                            'second_score_lower': sum(r['delta_second_minus_first'] < -threshold for r in rows),
                            'within_threshold': sum(abs(r['delta_second_minus_first']) <= threshold for r in rows)}
                           for threshold in (0., .01, .03, .05)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve raw-repeat audit versions')
    audit = json.loads((args.root/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']:
        raise ValueError('Full prespecified primary matrix first')
    config = json.loads((args.root/'freeze.json').read_text(encoding='utf-8'))['protocol']
    records = []
    sources = []
    repeat_records = []
    provenance = []
    for study, model in itertools.product(config['studies'], config['models']):
        cells = {}
        for policy, repeat in itertools.product(config['policies'], range(1, config['repeats']+1)):
            name = f'{study}_{model}_{policy}_r{repeat}'
            path = args.root/'cells'/name
            meta, lane, business = compact(path)
            cells[policy, repeat] = (lane, business)
            provenance.append({'cell': name, 'raw_sha256': meta['raw_file_sha256'], 'GPU_lane': lane})
        raw_keys = set(cells['raw-order', 1][1])
        if any(set(cells['raw-order', rep][1]) != raw_keys for rep in range(1, config['repeats']+1)):
            raise ValueError('Raw control request set differs')
        paired = []

        def append(first, second, kind, policy, repeats, lanes):
            if first['prompt_hash'] != second['prompt_hash']:
                raise ValueError('Raw/L0 matched input differs')
            paired.append({'population': kind, 'policy': policy, 'repeat_pair': repeats,
                           'GPU_lanes': lanes, 'source_group': first['source_group'], 'family': first['family'],
                           'row_type': first['row_type'], 'delta_second_minus_first': second['score']-first['score'],
                           'output_IDs_differ': first['output_hash'] != second['output_hash'],
                           'first_tokens': first['output_tokens'], 'second_tokens': second['output_tokens'],
                           'first_finish': first['finish'], 'second_finish': second['finish'],
                           'same_prefix_hit_count': first['prefix_hit_tokens'] == second['prefix_hit_tokens']})

        for one, two in itertools.combinations(range(1, config['repeats']+1), 2):
            lane1, first = cells['raw-order', one]; lane2, second = cells['raw-order', two]
            for key in raw_keys:
                append(first[key], second[key], 'all_raw_request_positions', 'raw-repeat', (one, two), (lane1, lane2))
        for policy in config['policies']:
            if policy == 'raw-order':
                continue
            common = set(raw_keys)
            for rep in range(1, config['repeats']+1):
                _, rows = cells[policy, rep]
                common &= {key for key, row in rows.items() if row['route'] == 'L0'}
                raw_lane, baseline = cells['raw-order', rep]
                lane, _ = cells[policy, rep]
                for key, row in rows.items():
                    if row['route'] == 'L0':
                        append(baseline[key], row, 'all_observed_policy_L0', policy, (rep, rep), (raw_lane, lane))
            for rep in range(1, config['repeats']+1):
                raw_lane, baseline = cells['raw-order', rep]
                lane, rows = cells[policy, rep]
                for key in common:
                    append(baseline[key], rows[key], 'same_positions_L0_in_every_policy_repeat', policy, (rep, rep), (raw_lane, lane))
            for one, two in itertools.combinations(range(1, config['repeats']+1), 2):
                lane1, first = cells['raw-order', one]; lane2, second = cells['raw-order', two]
                for key in common:
                    append(first[key], second[key], 'raw_at_same_positions_L0_in_every_policy_repeat', policy, (one, two), (lane1, lane2))
        grouped = defaultdict(list)
        by_source = defaultdict(list)
        by_repeat = defaultdict(list)
        for row in paired:
            for population in ('all_business', row['row_type']):
                for family in ('ALL', row['family']):
                    grouped[row['population'], row['policy'], population, family].append(row)
                    by_repeat[row['population'], row['policy'], row['repeat_pair'], row['GPU_lanes'], population, family].append(row)
                by_source[row['population'], row['policy'], population, row['family'], row['source_group']].append(row)
        for key, rows in sorted(grouped.items()):
            records.append({'study': study, 'model': model,
                            **dict(zip(('comparison', 'policy', 'population', 'family'), key)), **summary(rows)})
        for key, rows in sorted(by_source.items()):
            sources.append({'study': study, 'model': model,
                            **dict(zip(('comparison', 'policy', 'population', 'family', 'source_group'), key)), **summary(rows)})
        for key, rows in sorted(by_repeat.items()):
            repeat_records.append({'study': study, 'model': model,
                                   **dict(zip(('comparison', 'policy', 'repeat_pair', 'GPU_lanes', 'population', 'family'), key)), **summary(rows)})
    result = {'schema_version': 'tsc-r4.all-request-raw-repeat-balance.v1',
              'analysis_source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(args.root/'freeze.json'),
              'records': records, 'source_records': sources, 'repeat_records': repeat_records, 'cell_provenance': provenance,
              'new_GPU_requests': 0, 'scoring_changed': False,
              'limits': ['No selection on failure, quality or length in the all-position control tables.',
                         'Common-L0 tables select request positions routed L0 in every observed repeat of a policy, without filtering by outcome. This is a descriptive selected route population, not randomized treatment.',
                         'Raw repeat pair directions are later minus earlier; matched policy L0 directions are policy minus same-repeat raw. Three pairwise raw comparisons reuse controls and are correlated.',
                         'Identical Prompt IDs, device labels or prefix-hit counts do not establish identical batch shapes, cache execution paths or floating-point trajectories. These frequencies do not prove policy causally unrelated.',
                         'Original per-source clusters, all initial/future requests, improvements, decreases and length stops remain retained.']}
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'records': len(records), 'source_records': len(sources), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
