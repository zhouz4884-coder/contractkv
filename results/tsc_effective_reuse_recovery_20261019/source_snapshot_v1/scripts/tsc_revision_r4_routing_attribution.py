"""Post-freeze request routing and observed-cost attribution; no model calls.

Terminal scope outcomes explain all L0 business rows, including the first
business wave. Lifecycle status is also reported so those first rows are not
mistaken for separate rejected qualifications. Summed concurrent RPC/controller
times are descriptive work clocks, never additive critical-path wall costs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def category(reason):
    if reason == 'observation_scope_has_no_declared_exact_reuse':
        return 'reference_requires_exact_observation_without_declared_reuse'
    if reason.startswith('raw_output_contract:'):
        return 'raw_output_contract'
    if 'terminal_stop_margin' in reason:
        return 'candidate_EOS_margin'
    if 'candidate_token_margin' in reason:
        return 'candidate_token_margin'
    if 'raw' in reason and 'margin' in reason:
        return 'raw_margin'
    if reason == 'inherited_family_L0':
        return 'inherited_family_L0'
    if 'benefit' in reason or 'cost' in reason or 'tail' in reason or 'net' in reason:
        return 'prospective_cost_or_tail_gate'
    return 'other:' + reason


def business_clock(rows, concurrency):
    """Disjoint observed HTTP generation envelopes, plus full-wall residual."""
    business = [r for r in rows if r['row_type'] in ('warm', 'future')]
    waves = []
    for offset in range(0, len(business), concurrency):
        group = business[offset:offset + concurrency]
        if len({r['turn_id'] for r in group}) != 1:
            raise ValueError('Business row order does not describe readiness waves')
        starts = [r['first_time'] - r['ttft_ms'] / 1000 for r in group]
        end = max(r['end_time'] for r in group)
        start = min(starts)
        if waves and start < waves[-1]['end'] - 1e-6:
            raise ValueError('Business envelopes overlap across readiness waves')
        waves.append({'start': start, 'end': end, 'duration_s': end - start,
                      'source_groups': sorted({r['source_group'] for r in group}),
                      'family': ','.join(sorted({r['family'] for r in group}))})
    return waves


def audit_cell(path, protocol):
    summary = json.loads(path.read_text(encoding='utf-8'))
    raw = path.with_name('raw.jsonl')
    if not summary['execution_complete'] or sha(raw) != summary['raw_file_sha256']:
        raise ValueError('Incomplete or changed measured cell: ' + str(path))
    rows = read(raw)
    business = [r for r in rows if r['row_type'] in ('warm', 'future')]
    key = lambda r: (r['certificate_namespace'], r['query_scope'])
    plans = {}
    decisions = {}
    for r in rows:
        if r['row_type'] == 'prospective_plan':
            if key(r) in plans:
                raise ValueError('Repeated prospective plan for the same scope')
            plans[key(r)] = r
        elif r['row_type'] == 'verification':
            if key(r) in decisions:
                raise ValueError('Repeated scope decision')
            decisions[key(r)] = r
    states = {}
    requests = []
    for r in rows:
        if r['row_type'] == 'verification':
            states[key(r)] = r
        elif r['row_type'] in ('warm', 'future'):
            state = states.get(key(r))
            issued_now = bool(state and state['certificate_issued'])
            compiled = r['effective_level'] != 'L0'
            if compiled != issued_now or r.get('scope_invalid_admission'):
                raise ValueError('Observed scope lifecycle/admission mismatch')
            final = decisions.get(key(r))
            plan = plans.get(key(r))
            if compiled:
                if digest(r['prompt_token_ids'][:state['stable_prefix_tokens']]) != state['stable_prefix_hash']:
                    raise ValueError('Actual compiled prefix identity mismatch')
                cause = 'compiled'
            elif final and final['certificate_issued']:
                cause = 'initial_raw_before_successful_scope_decision'
            elif final:
                cause = category(final['failure_reason'])
            elif plan and not plan.get('allow_verification'):
                cause = category(plan['reason'])
            else:
                raise ValueError('Unexplained L0 routing')
            requests.append({
                'request_id': r['request_id'], 'session_id': r['session_id'],
                'turn_id': r['turn_id'], 'row_type': r['row_type'],
                'source_group': r['source_group'], 'family': r['family'],
                'namespace': key(r)[0], 'query_scope': key(r)[1],
                'effective_level': r['effective_level'], 'terminal_routing_cause': cause,
                'scope_decision_known_at_business_dispatch': state is not None,
                'actual_prefix_hit_tokens': r['prefix_hit_tokens'],
                'raw_score_or_policy_score': r['task_score'],
            })
    scope_records = []
    for scope, plan in sorted(plans.items()):
        selected = [r for r in requests if (r['namespace'], r['query_scope']) == scope]
        d = decisions.get(scope)
        attempts = d['attempts'] if d else []
        reason = d['failure_reason'] if d else plan['reason']
        scope_records.append({
            'namespace': scope[0], 'query_scope': scope[1],
            'source_group': selected[0]['source_group'], 'family': selected[0]['family'],
            'all_business_requests': len(selected),
            'future_requests': sum(r['row_type'] == 'future' for r in selected),
            'compiled_business': sum(r['effective_level'] != 'L0' for r in selected),
            'terminal_cause': 'issued' if d and d['certificate_issued'] else category(reason),
            'failure_reason': reason, 'GPU_attempts': len(attempts),
            'issued': bool(d and d['certificate_issued']),
            'pre_gate_allowed': plan['allow_verification'],
            'pre_gate_reason': plan['reason'],
            'reference_scope_contract': d.get('reference_scope_contract') if d else None,
            'pre_business_planning_ms': d.get('pre_business_planning_ms', 0) if d else 0,
            'post_business_registration_ms': d.get('post_business_registration_ms', 0) if d else 0,
            'complete_controller_ms': d['complete_verification_ms'] if d else 0,
            'RPC_ms_sum': sum(a['verification_ms'] for a in attempts),
            'rejected_RPC_ms_sum': sum(a['verification_ms'] for a in attempts if not a['certificate_issued']),
            'issued_stable_prefix_hash': d['stable_prefix_hash'] if d and d['certificate_issued'] else None,
            'observed_tenants_with_compiled_use': len({r['session_id'] for r in selected if r['effective_level'] != 'L0'}),
        })
    counts = Counter(r['terminal_routing_cause'] for r in requests)
    families = []
    for family in sorted({r['family'] for r in requests}):
        rr = [r for r in requests if r['family'] == family]
        ss = [r for r in scope_records if r['family'] == family]
        families.append({
            'family': family, 'business_requests': len(rr),
            'terminal_routing_counts': dict(Counter(r['terminal_routing_cause'] for r in rr)),
            'scope_count': len(ss), 'GPU_attempts': sum(s['GPU_attempts'] for s in ss),
            'issued_scopes': sum(s['issued'] for s in ss),
            'RPC_ms_sum': sum(s['RPC_ms_sum'] for s in ss),
            'rejected_RPC_ms_sum': sum(s['rejected_RPC_ms_sum'] for s in ss),
            'complete_controller_ms_sum': sum(s['complete_controller_ms'] for s in ss),
        })
    waves = business_clock(rows, protocol['runtime']['concurrency'])
    envelope = sum(w['duration_s'] for w in waves)
    wall = summary['wall_s_including_all_setup_and_verification']
    if wall - envelope < -1e-6:
        raise ValueError('Business envelope exceeds measured service wall')
    paired_raw = path.parent.parent / path.parent.name.replace('_risk-tail_', '_raw-order_') / 'summary.json'
    paired_clock = None
    if paired_raw.exists():
        baseline = json.loads(paired_raw.read_text(encoding='utf-8'))
        baseline_raw = paired_raw.with_name('raw.jsonl')
        if not baseline['execution_complete'] or sha(baseline_raw) != baseline['raw_file_sha256']:
            raise ValueError('Invalid paired raw evidence')
        base_waves = business_clock(read(baseline_raw), protocol['runtime']['concurrency'])
        base_envelope = sum(w['duration_s'] for w in base_waves)
        base_wall = baseline['wall_s_including_all_setup_and_verification']
        paired_clock = {
            'raw_file_sha256': sha(baseline_raw), 'raw_full_wall_s': base_wall,
            'raw_business_HTTP_envelope_s': base_envelope,
            'raw_remaining_full_wall_s': base_wall - base_envelope,
            'observed_business_HTTP_envelope_reduction_s': base_envelope - envelope,
            'remaining_wall_change_s': (wall - envelope) - (base_wall - base_envelope),
            'observed_net_full_wall_reduction_s': base_wall - wall,
        }
    return {
        'cell': path.parent.name, 'study': summary['study'], 'model': business[0]['model'],
        'policy': summary['policy'], 'repeat': summary['repeat'],
        'raw_file_sha256': sha(raw), 'summary_sha256': sha(path),
        'all_business_requests': len(requests), 'compiled_business_requests': counts['compiled'],
        'L0_business_requests': len(requests) - counts['compiled'],
        'terminal_routing_counts': dict(counts), 'family_records': families,
        'scope_records': scope_records, 'request_records': requests,
        'observed_scope_lifecycle_or_prefix_identity_errors': 0,
        'actual_compiled_prefix_hits': sum(r['actual_prefix_hit_tokens'] > 0 for r in requests if r['effective_level'] != 'L0'),
        'actual_compiled_prefix_misses': sum(r['actual_prefix_hit_tokens'] == 0 for r in requests if r['effective_level'] != 'L0'),
        'issued_prefix_hash_objects': len({s['issued_stable_prefix_hash'] for s in scope_records if s['issued']}),
        'full_wall_s': wall, 'business_HTTP_envelope_s': envelope,
        'remaining_full_wall_s': wall - envelope, 'paired_raw_clock': paired_clock,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-partial', action='store_true')
    p.add_argument('--cell', action='append', default=[])
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve previous attribution output')
    freeze = a.root / 'freeze.json'
    protocol = json.loads(freeze.read_text(encoding='utf-8'))['protocol']
    generation = a.root / 'source_snapshot' / protocol['generation_protocol']
    protocol = {**protocol, 'runtime': json.loads(generation.read_text(encoding='utf-8'))['runtime']}
    if not a.allow_partial:
        audit = json.loads((a.root / 'analysis/completion_audit_v1.json').read_text())
        if not audit['execution_complete'] or a.cell:
            raise ValueError('Complete primary study and all cells required')
    paths = sorted((a.root / 'cells').glob('*/summary.json'))
    records = [audit_cell(path, protocol) for path in paths
               if '_risk-tail_' in path.parent.name and (not a.cell or path.parent.name in a.cell)]
    if not records:
        raise ValueError('No measured policy cells')
    result = {
        'schema_version': 'tsc-r4.routing-attribution.v1', 'partial': a.allow_partial,
        'study_root': a.root.as_posix(), 'freeze_sha256': sha(freeze),
        'analysis_source_sha256': sha(Path(__file__)), 'new_GPU_requests': 0,
        'frozen_policy_inputs_scorer_or_primary_analysis_changed': False,
        'cells': records,
        'interpretation_limits': [
            'Terminal denial causes also count the initial raw business rows belonging to denied scopes. Lifecycle status separately records whether that decision was known at dispatch.',
            'Exact-observation eligibility denial is not evidence of a malformed metadata schema, a measured harmful candidate, or an implementation fault.',
            'No compiled prefix miss does not establish that rejected candidate prefixes would have remained resident. Rejected alternatives were not probed.',
            'RPC/controller sums can overlap across concurrent requests and with each other. They are descriptive work clocks; never add them to full wall or subtract them as exact savings.',
            'Business HTTP envelopes reconstruct request starts from first_time minus ttft_ms and end at last token end_time. Remaining full wall includes planning, qualification, CPU/logging, idle and other inter-wave gaps.',
            'Paired envelope differences are descriptive observed time accounting, not causal identification of one policy component or new serving measurements.',
            'The scope-lifecycle checks establish consistency of observed controlled-client records and actual prefix identities, not public-endpoint adversarial authorization security.',
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'complete_cells_read': len(records), 'partial': a.allow_partial,
                      'business_requests': sum(r['all_business_requests'] for r in records),
                      'compiled': sum(r['compiled_business_requests'] for r in records)}))


if __name__ == '__main__':
    main()
