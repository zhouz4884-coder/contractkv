"""Freeze a single Qwen three-policy DEV, with no adaptive parameter search."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root=Path.cwd().resolve();base=Path('results/tsc_revision_r4')
    parent_path=base/'input_fidelity_validation_v1/freeze.json'
    parent=json.loads(parent_path.read_text(encoding='utf-8'))
    for item in parent['files']:assert sha(item['path'])==item['sha256']
    profile=base/'development_cost_profile_candidate_v1.json'
    assert sha(profile)=='be21959e9bde139b7fd0ecdec7f64bea089f9858b929f737accc232882ce4c8f'
    replay=json.loads((base/'development_cost_adapter_full_stage_replay_v1.json').read_text(encoding='utf-8'))
    assert replay['all_12_scopes_replayed'] and replay['original_issued_4_still_allowed']==4 and replay['old_attempts_skipped']==3
    assert json.loads((base/'cost_study_baseline_auditor_equivalence_v1.json').read_text(encoding='utf-8'))['all_four_actual_cells_exact_equal']
    study=base/'cost_adaptation_development_v1';config_path=Path('configs/tsc_revision_r4_cost_development_v1.json')
    assert not study.exists() and not config_path.exists()
    config=deepcopy(parent['protocol'])
    prep=base/'input_fidelity_development_inputs_v3'
    config.update(schema_version='tsc-r4.single-cost-candidate-DEV.v1',development_only=True,
                  models=['qwen'],repeats=1,policies=['raw-order','risk-tail','cost-adapted'],
                  expected_cells=3,expected_actual_generations=1200,expected_future_requests=1080,
                  input_files={'template-fanout':(prep/'development_faithful_sessions_v3.jsonl').as_posix()},
                  CPU_input_length_preflight=(prep/'independent_input_integrity_v2.json').as_posix(),
                  new_sources=0,prior_sources_excluded=None,
                  input_preparation_record_sha256=sha(prep/'preparation_record_v3.json'),
                  cost_profile=profile.as_posix(),cost_profile_sha256=sha(profile),
                  selected_client='scripts/tsc_revision_r4_cost_study_live_v1.py',
                  selected_auditor='scripts/tsc_revision_r4_cost_study_summary_v1.py',
                  policy_order={'1':['raw-order','cost-adapted','risk-tail']},
                  source_cluster_units='Four previously observed faithful DEV sources, two per family; one process per policy, not independent validation.',
                  cross_condition_clock_boundary='All three fresh-process cells onGPU0,otherGPUidle;identicalclosed-loop2requestwaveclockandfullcost.',
                  cost_calibration='Original risk-tail gate preserved as the original-policy control. Cost-adapted uses one fixed DEV-only cold-envelope profile and incremental fan-out wait allowance. Original probability and saving-cap terms unchanged.',
                  formal_acceptance_boundary='One DEV candidate and fixed selection criteria only; if it fails retain negatives and skip conditional independent cost validation.',
                  cost_selection_plan='configs/tsc_revision_r4_cost_adaptation_plan_v1.json',
                  additional_conservative_quality_veto='All-route material drops must not exceed the original-policy control; this is fixed before any cost DEV output, in addition to the plan minimum checks.',
                  no_primary6_model_outputs_used_for_cost_selection=True,
                  known_primary18_completion_required_before_GPU_dispatch=True,
                  prior_faithful_validation_freeze_sha256=sha(parent_path))
    config_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    assignment=base/'cost_adaptation_development_assignment_v1.json'
    assert not assignment.exists()
    assignment.write_text(json.dumps({'timestamp_UTC':datetime.now(timezone.utc).isoformat(),
        'sources_known':True,'GPU_lane':0,'other_GPU_idle':True,'policy_order':config['policy_order']['1'],
        'no_new_independent_source_selected_for_cost_variant':True},indent=2)+'\n',encoding='utf-8')
    seeds={item['path'] for item in parent['files']}
    seeds.update({config_path.as_posix(),assignment.as_posix(),profile.as_posix(),
        'configs/tsc_revision_r4_cost_adaptation_plan_v1.json',
        'scripts/tsc_revision_r4_cost_adapter_v1.py',
        'scripts/tsc_revision_r4_cost_study_live_v1.py',
        'scripts/tsc_revision_r4_cost_study_audit_cell_v1.py',
        'scripts/tsc_revision_r4_cost_study_summary_v1.py',
        'scripts/tsc_revision_r4_cost_study_routing_v1.py',
        'scripts/tsc_revision_r4_cost_DEV_decision_v1.py',
        'scripts/tsc_revision_r4_freeze_cost_development_v1.py',
        'scripts/run_tsc_revision_r4_cost_development_v1.sh',
        'scripts/close_tsc_revision_r4_cost_development_v1.sh',
        'scripts/tsc_revision_r4_package_cost_development_v1.py',
        'results/tsc_revision_r4/development_qualification_cost_audit_v1.json',
        'results/tsc_revision_r4/development_cost_profile_offline_replay_v1.json',
        'results/tsc_revision_r4/development_cost_adapter_full_stage_replay_v1.json',
        'results/tsc_revision_r4/cost_study_baseline_auditor_equivalence_v1.json'})
    print(json.dumps(freeze_scope(root,study,config_path.resolve(),seeds,{
        'known_source_cost_DEV_only':True,'one_candidate_no_safety_scope_changes':True,
        'primary18_results_not_used_to_select_cost_parameters':True,'primary18_still_unmodified':True,
        'next_independent_cost_sources_not_yet_selected':True})))


if __name__=='__main__':main()
