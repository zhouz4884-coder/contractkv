"""Descriptive offered-load audit; never a measured GPU-utilization estimate.

This post-freeze supplement reads complete frozen-study outputs only. It does
not alter the preregistered main analyses, arrivals, policy or result selection.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results/tsc_revision_r4'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve prior descriptive load audit; use a new version')
    closed = args.root / 'validation_closed_v1'
    arrival = args.root / 'validation_arrival_v1'
    for base in (closed, arrival):
        audit = json.loads((base / 'analysis/completion_audit_v1.json').read_text())
        if not audit['execution_complete']:
            raise ValueError('Both complete formal studies are required')
    config = json.loads((arrival / 'freeze.json').read_text())['protocol']
    records = []
    for study, tenants in config['studies'].items():
        for model in config['models']:
            for repeat in range(1, config['repeats'] + 1):
                cell = f'{study}_{model}_raw-order_r{repeat}'
                closed_path = closed / 'cells' / cell / 'summary.json'
                closed_raw = json.loads(closed_path.read_text())
                arrival_paths = {
                    policy: arrival / 'cells' / f'{study}_{model}_{policy}_r{repeat}' / 'summary.json'
                    for policy in config['policies']
                }
                values = {key: json.loads(path.read_text()) for key, path in arrival_paths.items()}
                raw = values['raw-order']
                if not closed_raw['execution_complete'] or not all(s['execution_complete'] for s in values.values()):
                    raise ValueError('Incomplete cell')
                for field in ('arrival_trace_sha256', 'planned_last_arrival_offset_s', 'arrival_requests'):
                    if any(s[field] != raw[field] for s in values.values()):
                        raise ValueError('Unmatched frozen arrival declaration: ' + field)
                trace_path = args.root / 'arrivals_v2' / f'{study}_{model}_r{repeat}.json'
                if sha(trace_path) != raw['arrival_trace_sha256']:
                    raise ValueError('Arrival trace identity mismatch')
                trace = json.loads(trace_path.read_text())
                waves = trace['waves']
                first = waves[0]['ready_offset_s']
                last = waves[-1]['ready_offset_s']
                n = raw['arrival_requests']
                first_wave_requests = len(waves[0]['session_ids'])
                if first != 0 or last <= first or n <= first_wave_requests:
                    raise ValueError('Unexpected formal arrival geometry')
                rate = (n - first_wave_requests) / (last - first)
                closed_rate = n / closed_raw['wall_s_including_all_setup_and_verification']
                records.append({
                    'study': study, 'model_key': model, 'repeat': repeat,
                    'registered_tenants_per_template': tenants,
                    'all_business_requests': n, 'waves': len(waves),
                    'first_wave_requests': first_wave_requests,
                    'planned_arrival_span_s': last - first,
                    'offered_business_rate_excluding_initial_wave_boundary_req_s': rate,
                    'same_sources_closed_raw_full_wall_business_rate_req_s': closed_rate,
                    'offered_rate_over_observed_closed_raw_rate': rate / closed_rate,
                    'arrival_sha256': sha(trace_path),
                    'closed_raw_summary_sha256': sha(closed_path),
                    'arrival_policies': {
                        policy: {
                            'summary_sha256': sha(arrival_paths[policy]),
                            'full_wall_s': value['wall_s_including_all_setup_and_verification'],
                            'final_drain_after_last_planned_arrival_s': value['wall_s_including_all_setup_and_verification'] - last,
                            'measured_completion_business_rate_including_idle_and_drain_req_s': n / value['wall_s_including_all_setup_and_verification'],
                        } for policy, value in values.items()
                    },
                })
    result = {
        'schema_version': 'tsc-r4.descriptive-arrival-load.v1',
        'supplement_added_after_primary_freeze': True,
        'frozen_primary_analyses_unchanged': True,
        'policy_arrivals_scores_or_results_modified': False,
        'source_sha256': sha(Path(__file__)),
        'records': records,
        'interpretation': [
            'Arrivals were generated at nominal 0.8 of model-specific observed development family wave service rates with frozen jitter.',
            'The ratio here uses all-business rate from the same new sources in separate fresh closed-loop raw processes. It describes offered pressure, not GPU utilization or a capacity confidence interval.',
            'Initial simultaneous requests are excluded from the inter-arrival rate numerator; first and last planned wave timestamps define its denominator.',
            'Fixed-arrival full wall includes idle, queueing, controller work and final drain. Its completion rate is not a maximum service capacity.',
            'Arrival rates are matched across policies within each model/repeat, not across models. Neither trace is a production traffic measurement.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'descriptive_records': len(records), 'complete': True}))


if __name__ == '__main__':
    main()
