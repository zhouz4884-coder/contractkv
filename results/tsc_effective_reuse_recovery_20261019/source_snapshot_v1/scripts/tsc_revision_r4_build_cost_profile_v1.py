"""One DEV-only monotone cold-cost envelope and explicit fan-out wait budget.

This prepares a candidate controller calibration, not live efficacy evidence.
New independent validation outputs are never opened or used for fitting.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_cost_policy import decide


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def forecast(profile, model, family, level, tokens, original_features):
    key = '|'.join((model, family, level))
    matching = profile['cold_envelopes'].get(key, [])
    item = next((row for row in matching if row['bucket_upper_tokens'] >= tokens), None)
    if item is None:
        return None
    features = deepcopy(original_features)
    features['gpu_registration_cost_ms'] = max(item['conservative_observed_RPC_envelope_ms'], item['original_cold_GPU_p90_ms'])
    allowance = original_features['tail_budget_ms']
    features['tail_budget_ms'] = original_features['baseline_ttft_p95_ms'] + allowance
    features['tail_budget_enforced'] = True
    features['additional_sync_controller_allowance_ms'] = allowance
    features['tail_budget_definition'] = 'baseline_p95_plus_fixed_DEV_raw_global_p99_incremental_controller_allowance'
    features['cost_profile_version'] = 'DEV-monotone-cold-envelope-v1'
    features['residency_forecast'] = 'cold_cost_when_current_full_residency_unproven'
    features['cost_profile_bucket_upper_tokens'] = item['bucket_upper_tokens']
    features['cost_profile_source_clusters'] = item['source_clusters']
    return features


def main():
    base = Path('results/tsc_revision_r4')
    source_path = base/'development_qualification_cost_audit_v1.json'
    audit = json.loads(source_path.read_text(encoding='utf-8'))
    output = base/'development_cost_profile_candidate_v1.json'
    replay_path = base/'development_cost_profile_offline_replay_v1.json'
    assert not output.exists() and not replay_path.exists()
    assert not audit['new_independent_validation_logs_read']
    groups = defaultdict(list)
    for row in audit['rows']:
        if row['actual_cached_prefix_read_tokens'] == 0:
            groups[(row['model'], row['family'], row['level'], row['length_bucket_upper_tokens'])].append(row)
    catalog_path = base/'development_fit_v3/calibration_v1.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    envelopes = defaultdict(list)
    for (model, family, level, bucket), rows in sorted(groups.items()):
        calibration = catalog['models'][model]['template-fanout'][family]
        old_cold = calibration['prefix_states']['cold']['cost_quantiles']['0.9']['gpu_registration_ms']
        envelopes['|'.join((model, family, level))].append({
            'bucket_upper_tokens': bucket, 'RPCs': len(rows),
            'source_clusters': len({row['source_group'] for row in rows}),
            'observed_min_prompt_tokens': min(row['candidate_prompt_tokens'] for row in rows),
            'observed_max_prompt_tokens': max(row['candidate_prompt_tokens'] for row in rows),
            'observed_max_RPC_ms': max(row['actual_GPU_RPC_ms'] for row in rows),
            'original_cold_GPU_p90_ms': old_cold,
        })
    for values in envelopes.values():
        maximum = 0
        for row in sorted(values, key=lambda item: item['bucket_upper_tokens']):
            maximum = max(maximum, row['observed_max_RPC_ms'])
            row['conservative_observed_RPC_envelope_ms'] = maximum
    profile = {'schema_version': 'tsc-r4.DEV-cost-profile-candidate.v1',
               'source_sha256': sha(__file__), 'DEV_audit_sha256': sha(source_path),
               'original_catalog_sha256': sha(catalog_path),
               'cold_envelopes': dict(envelopes), 'active_candidate_models': ['Qwen3-8B'],
               'bucket_boundaries_fixed_before_counterfactual': [2048, 4096, 8192, 16384],
               'unsupported_model_family_level_length': 'raw_fallback_for_adapted_model_no_extrapolation_past_largest_profile_bucket',
               'unproven_current_residency': 'use_cold_envelope_even_if_hash_was_published',
               'gain_estimator': 'preserve_original_calibrated_prefill_token_cap_and_probability_terms',
               'fanout_wait_allowance': 'use_existing_DEV_raw_global_ready_p99_as_explicit_additional_sync_controller_budget',
               'single_session': 'unchanged', 'new_independent_outputs_used': False,
               'tail_runtime_guarantee': False,
               'limitations': ['Sparse correlated DEV sources; empirical cost envelope, not a probabilistic upper confidence bound.',
                              'Only Qwen has newly measured long-input DEV costs; no cost-adapted three-model claim.',
                              'Bucket support is an empirical calibration domain, not a proof for every intermediate prompt.',
                              'Actual online efficacy and quality require a separately frozen live A/B.']}
    output.write_text(json.dumps(profile, indent=2)+'\n', encoding='utf-8')
    root = base/'input_fidelity_development_faithful_v3'
    path = root/'cells/template-fanout_qwen_risk-tail_r1/raw.jsonl'
    data = [json.loads(line) for line in path.open(encoding='utf-8')]
    decisions = {(row['certificate_namespace'], row['query_scope']): row for row in data if row['row_type'] == 'verification'}
    records = []
    for row in data:
        if row['row_type'] != 'prospective_plan':
            continue
        key = row['certificate_namespace'], row['query_scope']
        plan = row['plan']
        adjusted = forecast(profile, 'Qwen3-8B', row['family'], plan['level'], len(plan['prompt_token_ids']), row['fine_cost_features'])
        reuses = row['declared_remaining_reuse_hint']
        prediction = decide(adjusted, reuses) if adjusted is not None else {'allow_verification': False, 'reason': 'cost_profile_length_unsupported'}
        old = decisions[key]
        records.append({'namespace': key[0], 'query_scope': key[1], 'family': row['family'],
                        'candidate_prompt_tokens': len(plan['prompt_token_ids']),
                        'old_GPU_attempts': len(old['attempts']), 'old_issued': old['certificate_issued'],
                        'candidate_allow': prediction['allow_verification'], 'candidate_reason': prediction['reason'],
                        'new_conditional_GPU_forecast_ms': adjusted['gpu_registration_cost_ms'] if adjusted else None,
                        'additional_controller_allowance_ms': adjusted['additional_sync_controller_allowance_ms'] if adjusted else None,
                        'old_RPC_work_would_be_skipped_ms': sum(a['verification_ms'] for a in old['attempts']) if not prediction['allow_verification'] else 0})
    result = {'schema_version': 'tsc-r4.DEV-offline-cost-candidate-replay.v1',
              'source_sha256': sha(__file__), 'profile_sha256': sha(output), 'original_DEV_raw_sha256': sha(path),
              'records': records, 'old_GPU_attempts': sum(row['old_GPU_attempts'] for row in records),
              'old_issued_scopes': sum(row['old_issued'] for row in records),
              'old_issued_scopes_still_candidate_allowed': sum(row['old_issued'] and row['candidate_allow'] for row in records),
              'old_GPU_attempts_candidate_would_skip': sum(row['old_GPU_attempts'] for row in records if not row['candidate_allow']),
              'new_GPU_requests': 0, 'is_live_latency_or_coverage_result': False,
              'not_additive_wall_saving': True, 'new_independent_outputs_read': False}
    replay_path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'records'}))


if __name__ == '__main__':
    main()
