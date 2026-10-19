"""Supplement descriptive family p99 uncertainty with readiness-wave clusters.

Primary frozen global intervals already use paired cold waves. The frozen
auxiliary family table uses individual sources, so its cold family intervals
must not be interpreted as preserving the two-request readiness dependency.
This post-freeze supplement preserves every original output and point estimate.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci
from scripts.tsc_revision_r2_select_policy import percentile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve family-tail supplement version')
    primary = args.root / 'analysis'
    if not json.loads((primary / 'completion_audit_v1.json').read_text())['execution_complete']:
        raise ValueError('Complete primary study evidence is required')
    config = json.loads((args.root / 'freeze.json').read_text())['protocol']
    sample_path = args.root / 'source_snapshot' / config['input_files']['single-session']
    samples = [json.loads(line) for line in sample_path.open(encoding='utf-8') if line.strip()]
    waves = {r['revision_source_group']: 'cold-wave-' + str(i // 2) for i, r in enumerate(samples)}
    request_path = primary / 'request_latency_pairs_v1.csv'
    original_path = primary / 'latency_strata_v1.csv'
    original = {(r['study'], r['model'], r['policy'], r['value']): r
                for r in csv_rows(original_path) if r['stratum'] == 'family'}
    groups = defaultdict(list)
    for row in csv_rows(request_path):
        if row['row_type'] != 'future':
            continue
        key = row['study'], row['model'], row['policy'], row['family']
        groups[key].append({**row, 'repeat': int(row['repeat']),
                            'ready_ttft_ms': float(row['ready_ttft_ms']),
                            'raw_ready_ttft_ms': float(row['raw_ready_ttft_ms'])})
    records = []
    for key, rows in sorted(groups.items()):
        study, model, policy, family = key
        resampled = [{**row, 'source_group': waves[row['source_group']]} for row in rows] if study == 'single-session' else rows
        clusters = len({row['source_group'] for row in resampled})
        old = original[key]
        raw_p99 = percentile([row['raw_ready_ttft_ms'] for row in rows], .99)
        policy_p99 = percentile([row['ready_ttft_ms'] for row in rows], .99)
        for measured, field in [(raw_p99, 'raw_ready_ttft_ms_p99'), (policy_p99, 'ready_ttft_ms_p99')]:
            if abs(measured - float(old[field])) > 1e-9:
                raise ValueError('Family point estimate changed unexpectedly')
        lo, hi = clustered_tail_ci(resampled) if clusters >= 2 else (None, None)
        records.append({
            'study': study, 'model': model, 'policy': policy, 'family': family,
            'paired_futures': len(rows), 'source_count': len({row['source_group'] for row in rows}),
            'readiness_dependency_clusters': clusters, 'fresh_repeats': len({row['repeat'] for row in rows}),
            'resampling_unit': 'two-source readiness wave' if study == 'single-session' else 'source template including all tenants',
            'raw_p99_ms': raw_p99, 'policy_p99_ms': policy_p99,
            'p99_reduction_pct': 100 * (1 - policy_p99 / raw_p99),
            'descriptive_wave_or_template_repeat_ci95_low': lo,
            'descriptive_wave_or_template_repeat_ci95_high': hi,
            'original_source_repeat_ci95_low': old.get('family_source_repeat_p99_ci95_low'),
            'original_source_repeat_ci95_high': old.get('family_source_repeat_p99_ci95_high'),
            'interval_not_reported_reason': 'fewer than two independent wave/template clusters' if clusters < 2 else '',
        })
    result = {
        'schema_version': 'tsc-r4.family-tail-readiness-dependency.v1',
        'analysis_added_after_primary_freeze': True, 'new_GPU_requests': 0,
        'primary_global_CIs_or_any_point_estimates_changed': False,
        'frozen_family_intervals_preserved_as_original': True,
        'source_sha256': sha(Path(__file__)),
        'request_pairs_sha256': sha(request_path), 'original_strata_sha256': sha(original_path),
        'frozen_source_order_sha256': sha(sample_path), 'records': records,
        'interpretation': [
            'Use these descriptive family intervals when discussing the shared readiness-wave protocol; the original per-source cold family intervals do not retain wave pairing.',
            'A one-template/wave family cannot estimate source-cluster variability; no degenerate interval is presented as evidence of precision.',
            'Few family clusters and only three fresh processes limit inference. One-process development rows do not estimate fresh-process variation.',
            'Fixed-arrival queueing also carries history between waves. These are descriptive fixed-trace cluster intervals, not a formal queueing-process guarantee, production interval or equivalence test.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'family_records': len(records), 'new_GPU_requests': 0,
                      'point_estimates_unchanged': True,
                      'insufficient_cluster_intervals': sum(r['readiness_dependency_clusters'] < 2 for r in records)}))


if __name__ == '__main__':
    main()
