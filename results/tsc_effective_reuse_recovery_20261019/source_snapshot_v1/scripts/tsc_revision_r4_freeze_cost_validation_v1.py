"""Freeze the single selected cost candidate on another six unseen sources."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    base = Path('results/tsc_revision_r4')
    dev = base/'cost_adaptation_development_v1'
    parent_path = dev/'freeze.json'
    parent = json.loads(parent_path.read_text(encoding='utf-8'))
    for item in parent['files']:
        assert sha(item['path']) == item['sha256']
    for name in ('local_independent_recompute_v1.json', 'local_independent_supplements_recompute_v1.json'):
        assert json.loads((dev/name).read_text())['independent_local_recomputation_complete']
    assert json.loads((dev/'fixed_DEV_decision_v1.json').read_text())['all_prespecified_DEV_checks_pass']
    assert json.loads((dev/'agent_all_business_review_v1.json').read_text())['allow_conditional_independent_nine']
    prepared = base/'cost_adaptation_validation_inputs_v1'
    record = json.loads((prepared/'preparation_record_v1.json').read_text())
    proof = json.loads((prepared/'independent_input_integrity_v1.json').read_text())
    assert record['sources'] == 6 and record['excluded_unique_sources'] == 573
    assert record['selected_sources_disjoint_from_all_573_prior'] and not record['model_outcomes_observed']
    assert proof['execution_complete'] and proof['layout_checks'] == 24
    assert proof['preparation_record_sha256'] == sha(prepared/'preparation_record_v1.json')
    for row in record['data_files']:
        assert sha(row['path']) == row['sha256']
    study = base/'cost_adaptation_validation_v1'
    config_path = Path('configs/tsc_revision_r4_cost_validation_v1.json')
    assignment = base/'cost_adaptation_validation_assignment_v1.json'
    assert not study.exists() and not config_path.exists() and not assignment.exists()
    config = deepcopy(parent['protocol'])
    order = {'1': ['raw-order', 'cost-adapted', 'risk-tail'],
             '2': ['risk-tail', 'raw-order', 'cost-adapted'],
             '3': ['cost-adapted', 'risk-tail', 'raw-order']}
    config.update(schema_version='tsc-r4.single-cost-candidate-independent.v1', development_only=False,
                  models=['qwen'], repeats=3, expected_cells=9, expected_actual_generations=5400,
                  expected_future_requests=4860,
                  input_files={'template-fanout': (prepared/'faithful_selected_sessions_v1.jsonl').as_posix()},
                  CPU_input_length_preflight=(prepared/'independent_input_integrity_v1.json').as_posix(),
                  new_sources=6, prior_sources_excluded=573, policy_order=order,
                  input_preparation_record_sha256=sha(prepared/'preparation_record_v1.json'),
                  source_cluster_units='Six new source groups, three per family; tenants nested within source and three fresh process repeats; Qwen only.',
                  cross_condition_clock_boundary='Three policies within each repeat share GPU. Repeat1/3 onGPU0, repeat2 onGPU1. Separate lanes may run concurrently, with unchanged two-request closed-loop readiness and complete costs.',
                  formal_acceptance_boundary='Complete all nine cells regardless of favorable or unfavorable outcomes. No profile, safety, scope, input or scoring retuning; no further automatic experiment matrix.',
                  additional_conservative_quality_veto='Applied to the preceding DEV only, not a selection filter on these test results.',
                  no_primary6_model_outputs_used_for_cost_selection=True,
                  direct_cost_vs_original_statistics='Source-template and paired fresh-repeat bootstrap: mean3000seed10672128, p992000seed10672129; future global/family/template; wall aggregate ratio and three per-repeat ratios, not wall sourceCI.',
                  selected_DEV_decision_sha256=sha(dev/'fixed_DEV_decision_v1.json'),
                  fixed_profile_no_independent_output_used=True)
    config_path.write_bytes((json.dumps(config, indent=2)+'\n').encode())
    assignment.write_bytes((json.dumps({'timestamp_UTC': datetime.now(timezone.utc).isoformat(),
        'balanced_three_policy_order': True, 'paired_same_device': True,
        'blocks': [{'repeat': r, 'model': 'qwen', 'GPU_lane': (r-1)%2, 'policy_order': order[str(r)]} for r in (1, 2, 3)]}, indent=2)+'\n').encode())
    seeds = {item['path'] for item in parent['files']}
    seeds.update({parent_path.as_posix(), config_path.as_posix(), assignment.as_posix(),
                  (dev/'fixed_DEV_decision_v1.json').as_posix(), (dev/'agent_all_business_review_v1.json').as_posix(),
                  (dev/'local_independent_recompute_v1.json').as_posix(),
                  (dev/'local_independent_supplements_recompute_v1.json').as_posix(),
                  (prepared/'preparation_record_v1.json').as_posix(),
                  (prepared/'independent_input_integrity_v1.json').as_posix()})
    seeds.update(row['path'] for row in record['data_files'])
    seeds.update({'scripts/'+name for name in [
        'tsc_revision_r4_prepare_cost_validation_v1.py', 'tsc_revision_r4_cost_validation_input_proof_v1.py',
        'tsc_revision_r4_cost_validation_remote_preflight_v1.py', 'tsc_revision_r4_freeze_cost_validation_v1.py',
        'run_tsc_revision_r4_cost_validation_v1.sh', 'close_tsc_revision_r4_cost_validation_v1.sh',
        'tsc_revision_r4_package_cost_validation_v1.py', 'tsc_revision_r4_cost_validation_comparison_v1.py']})
    print(json.dumps(freeze_scope(Path.cwd(), study, config_path.resolve(), seeds,
        {'new_cost_test_sources_outcomes_unused': True, 'cost_candidate_unchanged_since_prior_DEV_profile': True,
         'bounded_final_nine_cells_no_favorable_result_selection': True})))


if __name__ == '__main__':
    main()
