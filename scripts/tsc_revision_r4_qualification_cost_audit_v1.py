"""DEV-only conditional cost and benefit-cap audit; never read new held-out logs."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

DEV_ROOTS = ('development_pilot_v1', 'development_repeat_check_v1',
             'input_fidelity_development_head_v3', 'input_fidelity_development_faithful_v3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quantile(values, fraction):
    values = sorted(values)
    index = (len(values)-1)*fraction
    low = int(index)
    high = min(low+1, len(values)-1)
    return values[low]+(values[high]-values[low])*(index-low)


def length_bucket(tokens):
    return next((limit for limit in (2048, 4096, 8192, 16384) if tokens <= limit), 'over16384')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    json_path = Path(str(args.output_prefix)+'.json')
    csv_path = Path(str(args.output_prefix)+'.csv')
    assert not json_path.exists() and not csv_path.exists(), 'Preserve audit versions'
    rows, provenance, exclusions = [], [], []
    for name in DEV_ROOTS:
        root = Path('results/tsc_revision_r4')/name
        freeze = json.loads((root/'freeze.json').read_text(encoding='utf-8'))
        config = freeze['protocol']
        catalog = json.loads(Path(config['selected_catalog']).read_text(encoding='utf-8'))
        for summary_path in sorted((root/'cells').glob('*/summary.json')):
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            if summary['policy'] != 'risk-tail':
                exclusions.append({'cell': summary_path.parent.name, 'reason': 'not_original_R4_risk_tail'})
                continue
            raw_path = summary_path.with_name('raw.jsonl')
            assert summary['execution_complete'] and sha(raw_path) == summary['raw_file_sha256']
            data = [json.loads(line) for line in raw_path.open(encoding='utf-8')]
            business, plans, post = {}, {}, {}
            for row in data:
                key = row.get('certificate_namespace'), row.get('query_scope')
                if row['row_type'] in ('warm', 'future'):
                    business.setdefault(key, row)
                elif row['row_type'] == 'prospective_plan':
                    plans[key] = row
                elif row['row_type'] == 'post_reference_benefit_gate':
                    post[key] = row
            for decision in data:
                if decision['row_type'] != 'verification' or not decision['attempts']:
                    continue
                key = decision['certificate_namespace'], decision['query_scope']
                first = business[key]
                plan = plans[key]
                features = plan['fine_cost_features']
                candidate = plan['plan']
                assert len(decision['attempts']) == 1
                attempt = decision['attempts'][0]
                calibration = catalog['models'][first['model']][first['study']][first['family']]
                prompt = len(candidate['prompt_token_ids'])
                before_cap = max(0, candidate['stable_full_blocks']*16-math.ceil(calibration['raw_native_prefix_p95_tokens']/16)*16)
                after_cap = min(before_cap, calibration['calibrated_prefill_reduction_p95_tokens'])
                rpc = attempt['verification_ms']
                predicted_rpc = features['gpu_registration_cost_ms']
                rows.append({
                    'study_root': name, 'cell': summary_path.parent.name, 'model': first['model'],
                    'study': first['study'], 'family': first['family'], 'source_group': first['source_group'],
                    'namespace': key[0], 'query_scope': key[1], 'level': candidate['level'],
                    'candidate_prompt_tokens': prompt, 'witness_output_tokens': len(first['output_token_ids']),
                    'length_bucket_upper_tokens': length_bucket(prompt),
                    'declared_prefix_state': features['prefix_state'],
                    'actual_cached_prefix_read_tokens': attempt['cached_prefix_read_tokens'],
                    'actual_validation_prefix_class': 'positive_read' if attempt['cached_prefix_read_tokens'] else 'zero_read',
                    'full_residency_known_from_publication_index_alone': False,
                    'predicted_conditional_GPU_RPC_ms': predicted_rpc,
                    'predicted_information_ms': features['information_cost_ms'],
                    'predicted_pre_reference_weighted_total_ms': plan['estimated_cost_ms'],
                    'predicted_post_reference_conditional_total_ms': post[key]['estimated_cost_ms'] if key in post else None,
                    'actual_GPU_RPC_ms': rpc, 'actual_complete_controller_ms': decision['complete_verification_ms'],
                    'GPU_RPC_actual_over_conditional_prediction': rpc/predicted_rpc,
                    'tail_budget_enforced': features['tail_budget_enforced'], 'tail_budget_ms': features['tail_budget_ms'],
                    'declared_remaining_reuses': plan['declared_remaining_reuse_hint'],
                    'p_eligible_upper': features['p_eligible_upper'], 'p_joint_lower': features['p_joint_lower'],
                    'predicted_pre_reference_saved_ms': plan['estimated_saved_ms'],
                    'predicted_post_reference_saved_ms': post[key]['estimated_saved_ms'] if key in post else None,
                    'uncapped_planned_token_reduction': before_cap, 'capped_planned_token_reduction': after_cap,
                    'benefit_tokens_removed_by_old_calibration_cap': before_cap-after_cap,
                    'predicted_saving_per_reuse_ms': features['save_per_reuse_ms'],
                    'certificate_issued': attempt['certificate_issued'], 'failure_reason': attempt['failure_reason'],
                    'actual_batch_shape_trace_available_in_this_performance_cell': False,
                })
            provenance.append({'root': name, 'cell': summary_path.parent.name, 'raw_sha256': sha(raw_path),
                               'freeze_sha256': sha(root/'freeze.json')})
    groups = defaultdict(list)
    for row in rows:
        groups[(row['model'], row['study_root'], row['length_bucket_upper_tokens'],
                row['declared_prefix_state'], row['actual_validation_prefix_class'])].append(row)
    summaries = []
    for key, values in sorted(groups.items(), key=lambda item: str(item[0])):
        summaries.append({'model': key[0], 'study_root': key[1], 'length_bucket_upper_tokens': key[2],
                          'declared_prefix_state': key[3], 'actual_validation_prefix_class': key[4],
                          'RPCs': len(values), 'source_clusters': len({r['source_group'] for r in values}),
                          'issued': sum(r['certificate_issued'] for r in values),
                          'actual_GPU_RPC_ms_quantiles': {str(q): quantile([r['actual_GPU_RPC_ms'] for r in values], q) for q in (.5, .9, .95)},
                          'mean_actual_over_conditional_prediction': mean(r['GPU_RPC_actual_over_conditional_prediction'] for r in values),
                          'max_actual_over_conditional_prediction': max(r['GPU_RPC_actual_over_conditional_prediction'] for r in values),
                          'benefit_cap_active_RPCs': sum(r['benefit_tokens_removed_by_old_calibration_cap'] > 0 for r in values)})
    assert rows
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result = {'schema_version': 'tsc-r4.DEV-conditional-qualification-cost-audit.v1',
              'source_sha256': sha(__file__), 'fixed_preexisting_DEV_roots_only': list(DEV_ROOTS),
              'new_independent_validation_logs_read': False, 'new_GPU_requests': 0,
              'rows': rows, 'strata': summaries, 'cell_provenance': provenance,
              'excluded_cells': exclusions, 'CSV_sha256': sha(csv_path),
              'limits': [
                  'Pre-reference weighted expected cost is not a conditional GPU RPC prediction; compare like clocks.',
                  'Observed qualification RPCs are selected by the old admission policy; no outcomes for skipped attempts.',
                  'Length buckets and quantiles describe few correlated sources, not calibrated population confidence bounds.',
                  'Performance cells do not record per-step ModelRunner batch shape; do not substitute configured HTTP concurrency.',
                  'Publication hash presence alone does not prove complete resident KV state.',
                  'No cost-adapted policy has been selected or tested by this audit.']}
    json_path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'DEV_RPCs': len(rows), 'sources': len({(r['model'], r['source_group']) for r in rows}),
                      'strata': len(summaries), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
