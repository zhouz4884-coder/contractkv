"""Read-only decision funnel and component-cost audit of retained V5/Table III."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def load(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(workspace, output):
    assert not output.exists()
    serving = workspace / '.artifacts/faithful_serving_restore_v1/results/tsc_task_faithful_open_arrival_20261018/formal/cells'
    table = workspace / '.artifacts/tableIII_fullcost_restore_v1/results/tsc_tableIII_fullcost_replay_20261018/cells'
    inputs, decisions, costs = [], [], []
    for cell in sorted(serving.glob('*risk-tail_on')):
        if cell.name.startswith('gate_'):
            continue
        path = cell / 'raw.jsonl'
        data = load(path)
        business = [r for r in data if r['row_type'] in {'warm', 'future'}]
        assert len(business) == 360
        inputs.append(dict(path=path.relative_to(workspace).as_posix(), sha256=sha(path)))
        for row in [r for r in data if r['row_type'] == 'verification']:
            same_scope = [r for r in business if r['certificate_namespace'] == row['certificate_namespace']
                          and r['query_scope'] == row['query_scope']]
            witnesses = [r for r in same_scope if r['scope_first_raw_business']]
            assert len(witnesses) <= 1
            witness = witnesses[0] if witnesses else None
            later = [r for r in same_scope if witness and r['end_time'] > witness['end_time']]
            reason = row['failure_reason'] or 'PASS'
            scope_reject = reason == 'observation_scope_has_no_declared_exact_reuse'
            decisions.append(dict(cell=cell.name, model=business[0]['model'], family=row['family'],
                namespace=row['certificate_namespace'], query_scope=row['query_scope'], reason=reason,
                accepted=bool(row['certificate_issued']), RPCs=len(row['attempts']),
                planning_ms=row.get('pre_business_planning_ms', 0),
                complete_controller_ms=row['complete_verification_ms'],
                post_business_ms=row['post_business_registration_ms'],
                exact_observation_rejection=scope_reject, same_query_later_business=len(later),
                same_full_actual_Prompt_IDs_later=sum(r['prompt_token_ids'] == witness['prompt_token_ids'] for r in later) if witness else 0,
                deterministic_guard_reject_after_candidate_preparation=(scope_reject or reason.startswith('raw_output_contract:')),
                note='Measured component time, not an isolated critical-path saving or a new admission rule.'))
    assert len({r['cell'] for r in decisions}) == 12
    grouped = []
    for model, reason in sorted({(r['model'], r['reason']) for r in decisions}):
        part = [r for r in decisions if r['model'] == model and r['reason'] == reason]
        grouped.append(dict(model=model, reason=reason, decisions=len(part),
            RPCs=sum(r['RPCs'] for r in part), planning_ms=sum(r['planning_ms'] for r in part),
            complete_controller_ms=sum(r['complete_controller_ms'] for r in part),
            same_query_later_business=sum(r['same_query_later_business'] for r in part),
            same_full_actual_Prompt_IDs_later=sum(r['same_full_actual_Prompt_IDs_later'] for r in part)))
    state = json.loads((table.parent / 'execution_state_v1.json').read_text(encoding='utf-8'))
    for relative in state['completed_pairs']:
        pair = table.parent / relative
        path = pair / 'contract/audit/complete_controller_events_v1.jsonl'
        data = load(path)
        inputs.append(dict(path=path.relative_to(workspace).as_posix(), sha256=sha(path)))
        cc = [r for r in data if r['event'] == 'complete_controller']
        generate = [r for r in data if r['event'] == 'generate_raw']
        verify = [r for r in data if r['event'] == 'compact_verify']
        completion = json.loads((pair / 'contract/completion_v1.json').read_text(encoding='utf-8'))
        costs.append(dict(pair=relative, controllers=len(cc),
            full_controller_ms=sum(r['controller_ms'] for r in cc),
            Raw_reference_calls=len(generate), Raw_reference_elapsed_ms=sum(r['elapsed_ms'] for r in generate),
            compact_verify_calls=len(verify), compact_verify_elapsed_ms=sum(r['elapsed_ms'] for r in verify),
            failed_controller_count=sum(not r.get('certificate_issued', False) for r in cc),
            actual_contract_service_wall_s=completion['checks']['service_wall_with_drain_s'],
            per_source_controller_rows=cc,
            component_sum_is_not_parallel_critical_path=True,
            event_timers_lack_common_absolute_start_end=True))
    assert len(costs) == 12 and sum(r['controllers'] for r in costs) == 525
    failures = [r for r in decisions if r['deterministic_guard_reject_after_candidate_preparation']]
    result = dict(schema_version='contractkv.effective-reuse-existing-evidence-audit.v1',
        new_GPU_requests=0, prior_service_cells=12, prior_service_decisions=len(decisions),
        decision_counts_by_model_reason=grouped, decisions=decisions, TableIII_costs=costs,
        deterministic_scope_or_output_guard_rejections=len(failures),
        planning_elapsed_ms_before_these_rejections=sum(r['planning_ms'] for r in failures),
        scope_rejected_same_actual_Prompt_reuse=sum(r['same_full_actual_Prompt_IDs_later'] for r in decisions if r['exact_observation_rejection']),
        inputs=inputs, source_sha256=sha(Path(__file__)),
        conclusion='Deferring candidate preparation until after the same deterministic witness guards is an execution optimization hypothesis. '
        'Recorded preparation sums are not promised wall savings. No scope rejection is reclassified as PASS; exact metadata repetition is not invented. '
        'Table III component sums cannot reconstruct missing overlapping absolute intervals; new runner will time those intervals directly.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ['prior_service_cells', 'prior_service_decisions',
        'deterministic_scope_or_output_guard_rejections', 'planning_elapsed_ms_before_these_rejections',
        'scope_rejected_same_actual_Prompt_reuse', 'new_GPU_requests']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.workspace.resolve(), args.output.resolve())
