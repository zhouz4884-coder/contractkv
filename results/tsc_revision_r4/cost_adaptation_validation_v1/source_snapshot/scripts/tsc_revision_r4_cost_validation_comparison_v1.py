"""Preregistered paired cost-adapted versus original-policy comparison."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_live_summary import clustered_ci
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci
from scripts.tsc_revision_r2_select_policy import percentile


def read(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    audit = json.loads((a.root/'analysis/completion_audit_v1.json').read_text())
    assert audit['execution_complete'] and audit['complete_cells'] == 9
    rows = read(a.root/'analysis/request_latency_pairs_v1.csv')
    key = lambda r: (r['repeat'], r['session_id'], r['turn_id'], r['row_type'])
    original = {key(r): r for r in rows if r['policy'] == 'risk-tail'}
    adapted = {key(r): r for r in rows if r['policy'] == 'cost-adapted'}
    assert set(original) == set(adapted) and len(original) == 1800
    groups = defaultdict(list)
    for k, old in original.items():
        new = adapted[k]
        assert old['source_group'] == new['source_group'] and old['family'] == new['family']
        assert old['raw_ready_ttft_ms'] == new['raw_ready_ttft_ms']
        if old['row_type'] != 'future':
            continue
        row = {'repeat': int(old['repeat']), 'source_group': old['source_group'],
               'raw_ready_ttft_ms': float(old['ready_ttft_ms']),
               'ready_ttft_ms': float(new['ready_ttft_ms'])}
        for stratum, label in [('global', 'ALL'), ('family', old['family']), ('template', old['source_group'])]:
            groups[stratum, label].append(row)
    records = []
    for (stratum, label), values in sorted(groups.items()):
        mean_ci = clustered_ci(values)
        tail_ci = clustered_tail_ci(values)
        old = [r['raw_ready_ttft_ms'] for r in values]
        new = [r['ready_ttft_ms'] for r in values]
        records.append({'stratum': stratum, 'value': label, 'future_pairs': len(values),
                        'sources': len({r['source_group'] for r in values}),
                        'original_ready_p99_ms': percentile(old, .99),
                        'adapted_ready_p99_ms': percentile(new, .99),
                        'mean_reduction_pct': 100*(1-sum(new)/sum(old)),
                        'mean_reduction_source_repeat_ci95': list(mean_ci),
                        'p99_reduction_pct': 100*(1-percentile(new, .99)/percentile(old, .99)),
                        'p99_reduction_source_repeat_ci95': list(tail_ci)})
    perf = {(int(r['repeat']), r['policy']): r for r in read(a.root/'analysis/performance_by_cell_v1.csv')}
    repeat_ratios = [float(perf[r, 'risk-tail']['wall_s'])/float(perf[r, 'cost-adapted']['wall_s']) for r in (1, 2, 3)]
    wall = {policy: sum(float(perf[r, policy]['wall_s']) for r in (1, 2, 3))
            for policy in ('raw-order', 'risk-tail', 'cost-adapted')}
    scopes = read(a.root/'analysis/scope_decisions_v1.csv')
    work = {policy: sum(float(r['rejected_RPC_ms']) for r in scopes if r['policy'] == policy)
            for policy in ('risk-tail', 'cost-adapted')}
    result = {'schema_version': 'tsc-r4.independent-cost-vs-original.v1',
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'freeze_sha256': hashlib.sha256((a.root/'freeze.json').read_bytes()).hexdigest(),
              'future_latency_records': records, 'complete_service_wall_s': wall,
              'original_over_adapted_full_wall_multiplier': wall['risk-tail']/wall['cost-adapted'],
              'paired_repeat_full_wall_multipliers': repeat_ratios,
              'failed_GPU_RPC_work_ms': work, 'new_GPU_requests': 0,
              'limits': ['Six source clusters and three correlated process repeats, Qwen only.',
                         'Wall repeat min/max is descriptive, not a source-cluster confidence interval.',
                         'Original is the direct comparator here; both policies share the same raw controls in the primary tables.',
                         'No test-outcome-based selection or parameter update; all completed outcomes remain reported.']}
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'direct_future_pairs': 1620, 'strata': len(records), 'complete': True}))


if __name__ == '__main__':
    main()
