"""Prospectively freeze the bounded, known-source input-fidelity four-grid.

Run only once after CPU preparation. GPU execution remains separately gated on
completion of the pre-existing 90-cell R4 matrix and a verified public commit.
"""
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path.cwd().resolve()
    r4 = root / 'results/tsc_revision_r4'
    parent_path = r4 / 'validation_closed_v1/freeze.json'
    parent = json.loads(parent_path.read_text(encoding='utf-8'))
    for item in parent['files']:
        if sha(root / item['path']) != item['sha256']:
            raise ValueError('Immutable R4 file drift: ' + item['path'])
    prep_dir = r4 / 'input_fidelity_development_inputs_v3'
    prep_path = prep_dir / 'preparation_record_v3.json'
    prep = json.loads(prep_path.read_text(encoding='utf-8'))
    proof_path = prep_dir / 'independent_input_integrity_v2.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    if not proof['execution_complete'] or proof['sources'] != 50 or proof['layout_checks'] != 200:
        raise ValueError('Complete input/type/layout proof first')
    if proof['preparation_record_sha256'] != sha(prep_path) or proof['adapter_source_sha256'] != sha(root / 'scripts/tsc_revision_r4_fidelity_adapter_v2.py'):
        raise ValueError('Input proof provenance changed')
    for item in prep['data_files']:
        if sha(root / item['path']) != item['sha256']:
            raise ValueError('Prepared input changed')
    if prep['unsupported_critical_inputs'] or prep['packed_sources'] != 50:
        raise ValueError('Do not silently substitute unsupported known DEV sources')
    base_config = parent['protocol']
    historical_generation = json.loads((root / base_config['generation_protocol']).read_text(encoding='utf-8'))
    for condition, name, cap in [('head', 'head', 1500), ('faithful', 'preserved', 0)]:
        generation = json.loads((root / f'configs/tsc_revision_r4_input_fidelity_{name}_generation_v1.json').read_text(encoding='utf-8'))
        if generation['runtime'] != historical_generation['runtime'] or generation['free_generation'] != historical_generation['free_generation']:
            raise ValueError('Keep original runtime and generation budgets')
        layout = dict(generation['layout'])
        if layout.pop('stable_word_limit') != cap:
            raise ValueError('Wrong input condition word cap')
        historical_layout = dict(historical_generation['layout']); historical_layout.pop('stable_word_limit')
        if layout != historical_layout:
            raise ValueError('Keep the original CALC ladder and expansion')
    configs = {}
    for condition, input_name, generation, client, audit in [
        ('head', 'development_old_head_sessions_v3.jsonl', 'configs/tsc_revision_r4_input_fidelity_head_generation_v1.json',
         'scripts/tsc_revision_r4_live.py', 'scripts/tsc_revision_r4_live_summary.py'),
        ('faithful', 'development_faithful_sessions_v3.jsonl', 'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json',
         'scripts/tsc_revision_r4_fidelity_live_v2.py', 'scripts/tsc_revision_r4_fidelity_summary_v2.py')]:
        base = r4 / f'input_fidelity_development_{condition}_v2'
        config_path = root / f'configs/tsc_revision_r4_fidelity_development_{condition}_v2.json'
        if base.exists() or config_path.exists():
            raise ValueError('Preserve every prospective DEV version')
        config = deepcopy(base_config)
        config.update(schema_version='tsc-r4.task-fidelity-known-development.v2',
                      development_only=True, models=['qwen'], policies=['raw-order', 'risk-tail'], repeats=1,
                      studies={'template-fanout': 10}, expected_cells=2,
                      expected_actual_generations=800, expected_future_requests=720,
                      input_files={'template-fanout': (prep_dir / input_name).relative_to(root).as_posix()},
                      generation_protocol=generation, selected_client=client, selected_auditor=audit,
                      CPU_input_length_preflight=proof_path.relative_to(root).as_posix(),
                      new_sources=0, prior_sources_excluded=None,
                      policy_order={'1': ['raw-order', 'risk-tail'] if condition == 'head' else ['risk-tail', 'raw-order']},
                      task_fidelity_condition=condition,
                      parent_R4_freeze_sha256=sha(parent_path),
                      input_preparation_record_sha256=sha(prep_path),
                      output_contract_version='unchanged-one-python-statement',
                      input_adapter='none' if condition == 'head' else 'task-fidelity-contiguous-segment-text-v2',
                      cost_calibration='Original R4 balanced calibration unchanged; no refitting to larger input or DEV outcomes.',
                      cross_condition_clock_boundary='All four fresh Qwen processes on GPU lane 0, cross-condition order head/raw, faithful/risk, faithful/raw, head/risk. One repeat, no independent-validation/process-uncertainty claim.',
                      scope_boundary='Existing exact query/typed metadata rules, raw/candidate/EOS floors, single-shot and inherited L0 unchanged.')
        config['input_adaptation'] = ({**base_config['input_adaptation'], 'condition': 'historical head-1500 word collapse'} if condition == 'head' else
                                      {'stable_word_limit': 0, 'stable_pieces': 16,
                                       'text_processing': 'Frozen label-blind original head/tail context substrings; complete CODE_PREFIX/query, whitespace and omission ledgers. Adjacent pieces of the same original segment are rendered contiguously under one outside heading; no internal injected labels. CALC node order/levels/dependencies unchanged.',
                                       'metadata_correction': 'CODE_PREFIX volatility=0 and cache_stability=1; 200 layouts and corresponding prompts unchanged.',
                                       'task_defining_fields_not_truncated': True})
        # Claims about all 50 original sources belong to their separate R4
        # study. This DEV root contains exactly the same four known sources.
        config['source_cluster_units'] = 'Four previously observed source templates, two per family, all ten tenants; one repeat.'
        config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        configs[condition] = (base, config_path)
    assignment = r4 / 'input_fidelity_development_assignment_v2.json'
    assignment.write_text(json.dumps({
        'timestamp_UTC': datetime.now(timezone.utc).isoformat(),
        'sources_already_observed': True,
        'no_new_source_selection': True,
        'cells': [{'condition': c, 'policy': p, 'gpu_lane': 0, 'repeat': 1} for c, p in
                  [('head', 'raw-order'), ('faithful', 'risk-tail'), ('faithful', 'raw-order'), ('head', 'risk-tail')]],
        'reason': 'Same device for all four cells; reverse raw/risk order across input conditions; no policy threshold/contract tuning.',
        'no_execution_authorized_before_existing_R4_complete': True,
    }, indent=2) + '\n', encoding='utf-8')
    seeds = {r['path'] for r in parent['files']}
    seeds.update({
        'configs/tsc_revision_r4_input_fidelity_plan_v3.json',
        'configs/tsc_revision_r4_input_fidelity_head_generation_v1.json',
        'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json',
        'scripts/tsc_revision_r4_input_fidelity.py',
        'scripts/tsc_revision_r4_prepare_fidelity_development_v3.py',
        'scripts/tsc_revision_r4_fidelity_adapter.py',
        'scripts/tsc_revision_r4_fidelity_adapter_v2.py',
        'tests/test_tsc_revision_r4_fidelity_renderer.py',
        'results/tsc_revision_r4/fidelity_render_contiguity_diagnostic_v1.json',
        'scripts/tsc_revision_r4_fidelity_live_v2.py',
        'scripts/tsc_revision_r4_fidelity_summary_v2.py',
        'scripts/tsc_revision_r4_fidelity_input_proof_v2.py',
        'scripts/tsc_revision_r4_freeze_fidelity_development_v2.py',
        'scripts/run_tsc_revision_r4_fidelity_development_v2.sh',
        'scripts/tsc_revision_r4_package_fidelity_v2.py',
        'scripts/tsc_revision_r4_physical_prefix_accounting.py',
        'tests/test_tsc_revision_r4_input_fidelity.py',
        'results/tsc_revision_r4/full_input_window_audit_v1.json',
        'scripts/tsc_revision_r4_full_input_window_audit.py',
        assignment.relative_to(root).as_posix(), prep_path.relative_to(root).as_posix(), proof_path.relative_to(root).as_posix(),
    })
    seeds.update((prep_dir / name).relative_to(root).as_posix() for name in
                 ['all_known_faithful_sessions_v3.jsonl', 'development_old_head_sessions_v3.jsonl', 'development_faithful_sessions_v3.jsonl'])
    seeds.update(path.relative_to(root).as_posix() for _, path in configs.values())
    results = {}
    for condition, (base, config_path) in configs.items():
        results[condition] = freeze_scope(root, base, config_path, seeds, {
            'known_source_development': True, 'model_outcomes_of_these_new_input_cells_unused': True,
            'unchanged_R4_algorithms_and_output_contract': True,
            'unexecuted_v1_prototype_preserved_due_to_pre_forward_CPU_renderer_discovery': True,
            'existing_90_cell_R4_results_preserved': True,
            'independent_validation_sources_not_selected_yet': True,
        })
    print(json.dumps(results))


if __name__ == '__main__':
    main()
