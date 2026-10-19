"""Freeze the unchanged-method, source-disjoint, eighteen-cell fidelity study."""
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
    root = Path.cwd().resolve()
    base = Path('results/tsc_revision_r4')
    parent_path = base/'input_fidelity_development_faithful_v3/freeze.json'
    parent = json.loads(parent_path.read_text(encoding='utf-8'))
    for item in parent['files']:
        assert sha(item['path']) == item['sha256'], item['path']
    prepared = base/'input_fidelity_validation_inputs_v1'
    record_path = prepared/'preparation_record_v1.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    proof_path = prepared/'independent_input_integrity_v1.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    assert proof['execution_complete'] and proof['sources'] == 6 and proof['layout_checks'] == 24
    assert proof['preparation_record_sha256'] == sha(record_path)
    assert record['selected_sources_disjoint_from_all_567_prior'] and record['sources'] == 6
    assert not record['model_outcomes_observed'] and record['new_GPU_requests'] == 0
    for item in record['data_files']:
        assert sha(item['path']) == item['sha256']
    review = json.loads((base/'input_fidelity_development_comparison_v1.json').read_text(encoding='utf-8'))
    faithful = next(row for row in review['conditions'] if row['condition'] == 'faithful')
    assert sum(row['compiled_pairs'] for row in faithful['family_populations'] if row['population'] == 'future') == 112
    assert all(row['compiled_output_ID_divergences'] == 0 and row['compiled_any_score_decrease'] == 0
               for row in faithful['family_populations'])
    study = base/'input_fidelity_validation_v1'
    config_path = Path('configs/tsc_revision_r4_fidelity_validation_v1.json')
    assignment = base/'input_fidelity_validation_assignment_v1.json'
    route = base/'input_fidelity_validation_route_v1.json'
    assert not study.exists() and not config_path.exists() and not assignment.exists() and not route.exists()
    config = deepcopy(parent['protocol'])
    config.update(schema_version='tsc-r4.independent-fidelity-validation.v1', development_only=False,
                  models=['qwen', 'mistral', 'llama'], repeats=3, policies=['raw-order', 'risk-tail'],
                  expected_cells=18, expected_actual_generations=10800, expected_future_requests=9720,
                  input_files={'template-fanout': (prepared/'faithful_selected_sessions_v1.jsonl').as_posix()},
                  CPU_input_length_preflight=proof_path.as_posix(), new_sources=6, prior_sources_excluded=567,
                  input_preparation_record_sha256=sha(record_path),
                  parent_faithful_development_freeze_sha256=sha(parent_path),
                  policy_order={'1': ['raw-order', 'risk-tail'], '2': ['risk-tail', 'raw-order'], '3': ['raw-order', 'risk-tail']},
                  source_cluster_units='Six independently selected source groups, three per family, shared across models; all ten tenants nested within each source and fresh process repeat.',
                  cross_condition_clock_boundary='Paired raw/risk blocks share GPU lane; assignments counterbalanced across model and three repeats. Two separate GPU lanes may execute concurrently. Same closed-loop two-request readiness protocol.',
                  output_contract_version='unchanged-one-python-statement',
                  cost_calibration='Original balanced R4 calibration, including fan-out tail enforcement behavior, is unchanged. Known DEV tail regression is retained; no cost-adapted policy is included in these18.',
                  source_selection_seed=10672146,
                  formal_acceptance_boundary='This is an independent evaluation of the fixed method, not a deployment SLO acceptance gate. Known DEV p99 worsening is not hidden or used to tune input, scope or calibration. All failures and coverage losses are reported.',
                  primary_method_frozen_before_any_new_source_model_output=True,
                  cost_adaptation_uses_only_preexisting_development_logs=True,
                  formal_heldout_outputs_forbidden_for_cost_rule_selection=True)
    config_path.write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    blocks = []
    for repeat in (1, 2, 3):
        for offset, alias in enumerate(('qwen', 'mistral', 'llama')):
            blocks.append({'model': alias, 'repeat': repeat, 'GPU_lane': (3*(repeat-1)+offset) % 2,
                           'policy_order': config['policy_order'][str(repeat)]})
    assignment.write_text(json.dumps({'schema_version': 'tsc-r4.fidelity-independent-assignment.v1',
                                     'paired_same_device': True, 'blocks': blocks}, indent=2)+'\n', encoding='utf-8')
    route.write_text(json.dumps({'timestamp_UTC': datetime.now(timezone.utc).isoformat(),
                                'direct_human_answer_received_after_p99_consultation': True,
                                'route': 'First execute unchanged faithful18; parallel local CPU cost audit and reproducible TableI reconstruction. Evidence-backed cost repair is a separate bounded DEV variant, not silently included in the primary18.',
                                'no_new_certificate_or_scheduler': True,
                                'no_safety_margin_scope_or_scorer_changes': True,
                                'old_fixed_arrival_remains_5_of_54': True,
                                'model_outcomes_of_selected_new_sources_unused': True}, indent=2)+'\n', encoding='utf-8')
    seeds = {item['path'] for item in parent['files']}
    seeds.update({config_path.as_posix(), assignment.as_posix(), route.as_posix(), record_path.as_posix(), proof_path.as_posix(),
                  'results/tsc_revision_r4/fidelity_complete_exclusion_audit_v1.json',
                  'results/tsc_revision_r4/fidelity_additional_service_exclusion_proof_v1.json',
                  'scripts/tsc_revision_r4_prepare_fidelity_validation_v1.py',
                  'scripts/tsc_revision_r4_fidelity_validation_input_proof_v1.py',
                  'scripts/tsc_revision_r4_fidelity_validation_remote_preflight_v1.py',
                  'scripts/tsc_revision_r4_freeze_fidelity_validation_v1.py',
                  'scripts/run_tsc_revision_r4_fidelity_validation_v1.sh',
                  'scripts/close_tsc_revision_r4_fidelity_validation_v1.sh',
                  'scripts/tsc_revision_r4_package_fidelity_validation_v1.py',
                  'scripts/tsc_revision_r4_all_business_quality.py',
                  'scripts/tsc_revision_r4_score_balance.py',
                  'scripts/tsc_revision_r4_routing_attribution.py',
                  'scripts/tsc_revision_r4_scope_object_audit.py',
                  'scripts/tsc_revision_r4_actual_prompt_audit.py',
                  'tests/test_tsc_revision_r4_fidelity_selection.py'})
    seeds.update(item['path'] for item in record['data_files'])
    result = freeze_scope(root, study, config_path.resolve(), seeds, {
        'independent_new_sources': True, 'new_source_model_outputs_unused': True,
        'current_and_original_faithful_R4_method_equal': True,
        'cost_variant_not_in_this_primary_study': True,
        'all_prior_results_and_49_unexecuted_arrival_cells_preserved': True})
    print(json.dumps(result))


if __name__ == '__main__':
    main()
