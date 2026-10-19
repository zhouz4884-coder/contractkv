"""Read-only post-hoc evidence reuse; never launches inference or changes policy.

The fixed margin grid is descriptive on already observed traces. It is not a
selection procedure, a replay of rejected requests, or a future-behavior claim.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


GRID = (0.0, 0.03125, 0.0625, 0.125, 0.25, 0.5, 1.0)


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def csvrows(p):
    with p.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def quantile(values, q):
    a = sorted(values)
    pos = (len(a) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return a[lo] + (a[hi] - a[lo]) * (pos - lo)


def finite(x):
    try:
        y = float(x)
        return y if math.isfinite(y) else None
    except (TypeError, ValueError):
        return None


def write_csv(p, records):
    assert records
    with p.open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)


def write_json(p, value):
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def main(root, output):
    if output.exists():
        raise FileExistsError('Preserve every CPU analysis attempt')
    inputs = {}

    def record(p):
        inputs[str(p.relative_to(root)).replace('\\', '/')] = dict(bytes=p.stat().st_size, sha256=sha(p))

    faithful = root / 'results/tsc_revision_r4/input_fidelity_validation_v1'
    latency_path = faithful / 'analysis/request_latency_pairs_v1.csv'
    record(latency_path)
    latency = csvrows(latency_path)
    latency = [x for x in latency if x['row_type'] == 'future']
    assert len(latency) == 4860
    lookup = {(x['model'], int(x['repeat']), x['session_id'], int(x['turn_id'])): x for x in latency}
    assert len(lookup) == len(latency)
    inventory_path = faithful / 'raw_evidence_inventory_v1.csv'
    record(inventory_path)
    inventory = {x['path']: x['sha256'] for x in csvrows(inventory_path)}

    business, registrations, margin_records = {}, {}, []
    for cell in sorted((faithful / 'cells').iterdir()):
        if '_risk-tail_' not in cell.name:
            continue
        p = cell / 'raw.jsonl'
        record(p)
        relative = str(p.relative_to(root)).replace('\\', '/')
        assert relative in inventory and inputs[relative]['sha256'] == inventory[relative]
        with p.open(encoding='utf-8') as f:
            for line in f:
                row = json.loads(line)
                typ = row['row_type']
                if typ in ('warm', 'future'):
                    key = (row['model'], int(row['repeat']), row['session_id'], int(row['turn_id']))
                    assert key not in business
                    business[key] = row
                if typ == 'verification':
                    tenant = int(row['session_id'].rsplit('-tenant', 1)[1])
                    k = (cell.name, row['certificate_namespace'], tenant // 2, int(row['turn_id']))
                    assert k not in registrations, 'Do not silently sum concurrent registration durations'
                    registrations[k] = row
                if typ == 'verification_response':
                    r = row['response']
                    raw, candidate, stop = [finite(r.get(k)) for k in
                                            ('raw_margin_min', 'candidate_margin_min', 'terminal_stop_margin')]
                    margin_records.append(dict(cell=cell.name, request_id=row['request_id'],
                        observed_issued=bool(r.get('certificate_issued')), observed_decision=r.get('verify_decision'),
                        observed_failure=r.get('failure_reason', ''), raw_margin_min=raw,
                        candidate_margin_min=candidate, terminal_stop_margin=stop,
                        all_three_margins_retained=all(x is not None for x in (raw, candidate, stop))))

    detailed = []
    for key, row in lookup.items():
        actual = business[key]
        model, repeat, sid, turn = key
        ready, backend, queue, controller = [float(row[k]) for k in
            ('ready_ttft_ms', 'ttft_ms', 'queue_before_controller_ms', 'controller_to_submit_ms')]
        assert abs(ready - backend - queue - controller) < 1e-5
        tenant = int(sid.rsplit('-tenant', 1)[1])
        short = {'Qwen3-8B': 'qwen', 'Mistral-7B-Instruct-v0.3': 'mistral', 'Llama-3.1-8B-Instruct': 'llama'}[model]
        cell = f'template-fanout_{short}_risk-tail_r{repeat}'
        prev = registrations.get((cell, actual['certificate_namespace'], tenant // 2, turn - 1))
        post_ms = float(prev.get('post_business_registration_ms', 0)) if prev else 0.0
        # Closed-loop readiness is the preceding business-wave end, before its
        # registration. This is an observed shared wait, not an independent
        # additional GPU cost for each tenant who waited for that registration.
        assert post_ms <= controller + 20.0, 'Unexpected timing boundary; inspect instead of assigning causality'
        detailed.append(dict(model=model, repeat=repeat, source_group=row['source_group'], family=row['family'],
            session_id=sid, tenant=tenant, turn_id=turn, query_scope=actual['query_scope'],
            route=row['effective_level'], ready_ttft_ms=ready, backend_ttft_ms=backend,
            queue_before_controller_ms=queue, controller_to_submit_ms=controller,
            observed_previous_wave_registration_wait_ms=post_ms,
            other_controller_to_submit_ms=controller-post_ms,
            previous_registration_issued=prev.get('certificate_issued') if prev else None,
            previous_registration_failure=prev.get('failure_reason', '') if prev else '',
            previous_registration_GPU_calls=len(prev.get('attempts', [])) if prev else 0,
            completion_tokens=actual['completion_tokens'], finish_reason=actual['finish_reason'],
            output_budget=actual['output_budget'], at_output_limit=actual['finish_reason'] == 'length',
            task_score=actual['task_score'], prompt_tokens=actual['prompt_tokens'],
            prefix_hit_tokens=actual['prefix_hit_tokens'], new_prefill_tokens=actual['new_prefill_tokens'],
            raw_ready_ttft_ms=float(row['raw_ready_ttft_ms']),
            raw_controller_to_submit_ms=float(row['raw_controller_to_submit_ms'])))

    by_repeat = defaultdict(list)
    for row in detailed:
        by_repeat[row['model'], row['repeat']].append(row)
    slow, tail_summary = [], []
    for (model, repeat), group in sorted(by_repeat.items()):
        threshold = quantile([x['ready_ttft_ms'] for x in group], .99)
        selected = [dict(x, descriptive_p99_threshold_ms=threshold) for x in group if x['ready_ttft_ms'] >= threshold]
        slow.extend(selected)
        tail_summary.append(dict(model=model, repeat=repeat, future_requests=len(group),
            raw_p99_ms=quantile([x['raw_ready_ttft_ms'] for x in group], .99), contract_p99_ms=threshold,
            p99_tail_requests=len(selected), p99_tail_sources=dict(Counter(x['source_group'] for x in selected)),
            p99_tail_routes=dict(Counter(x['route'] for x in selected)),
            mean_tail_backend_ms=statistics.fmean(x['backend_ttft_ms'] for x in selected),
            mean_tail_controller_to_submit_ms=statistics.fmean(x['controller_to_submit_ms'] for x in selected),
            mean_tail_previous_registration_wait_ms=statistics.fmean(x['observed_previous_wave_registration_wait_ms'] for x in selected),
            tail_waiting_after_failed_GPU_registration=sum(x['previous_registration_GPU_calls'] > 0 and x['previous_registration_issued'] is False for x in selected),
            tail_output_limit_events=sum(x['at_output_limit'] for x in selected)))

    grid_rows = []
    by_model = defaultdict(list)
    for row in margin_records:
        by_model[row['cell'].split('_')[1]].append(row)
    for model, group in sorted(by_model.items()):
        complete = [r for r in group if r['all_three_margins_retained']]
        for threshold in GRID:
            passing = [r for r in complete if min(r['raw_margin_min'], r['candidate_margin_min'], r['terminal_stop_margin']) >= threshold]
            grid_rows.append(dict(model=model, common_floor=threshold, observed_RPC_responses=len(group),
                responses_with_complete_margins=len(complete), margin_only_PASS=len(passing),
                originally_issued_in_margin_only_PASS=sum(r['observed_issued'] for r in passing),
                not_originally_issued_in_margin_only_PASS=sum(not r['observed_issued'] for r in passing),
                boundary='Post-hoc common-floor predicate only. Other constraints, unexecuted candidates, admission coverage and future outputs are not re-evaluated.'))

    known_path = root / 'results/tsc_revision_r4/diagnosis_v1/analysis/qualifications_v1.csv'
    paired_path = root / 'results/tsc_revision_r4/diagnosis_v1/analysis/paired_outputs_v1.csv'
    record(known_path); record(paired_path)
    known, paired = csvrows(known_path), csvrows(paired_path)
    known_summary = dict(known_source='NarrativeQA doc99; already observed diagnostic, one source',
        qualifications=len(known), observed_issued=sum(x['issued']=='True' for x in known),
        candidate_min_margins=sorted(set(float(x['candidate_min_margin']) for x in known)),
        pairs=len(paired), material_decrease_pairs=sum(float(x['candidate_score'])-float(x['raw_score']) < -.03 for x in paired),
        common_floor_counts=[dict(floor=t, raw_and_candidate_margin_PASS=sum(min(float(x['raw_min_margin']), float(x['candidate_min_margin'])) >= t for x in known)) for t in GRID],
        boundary='The historical candidate minimum 0.40625 and independent controlled strong positive candidate margins do not certify a changed future raw input; exact scope remains necessary. This grid does not use unseen future outputs to select a threshold.')

    p16 = root / 'results/hard_systems/phase16r_pstp_live_v0.csv'
    p17 = root / 'results/hard_systems/phase17_concurrency_fault_v0.csv'
    p18 = root / 'results/hard_systems/phase18_c3_gate_summary_v1.json'
    for p in (p16, p17, p18): record(p)
    r16, r17, r18 = csvrows(p16), csvrows(p17), json.loads(p18.read_text(encoding='utf-8'))
    nonpass16 = [x for x in r16 if x['decision'] != 'PASS']
    nonpass17 = [x for x in r17 if x['verify_decision'] != 'PASS']
    assert all(int(x['cache_entries_delta']) == 0 and int(x['commit_tokens']) == 0 for x in nonpass16 + nonpass17)
    pstp = dict(phase16_harness=dict(cases=len(r16), all_gates=sum(x['gate_pass']=='True' for x in r16),
        nonpass_cases=len(nonpass16), nonpass_new_entries=sum(int(x['cache_entries_delta']) for x in nonpass16),
        boundary='Real native scheduler publication with harness decisions; alone does not prove automatic verifier wiring.'),
        phase17_concurrent_fault=dict(cases=len(r17), nonpass_cases=len(nonpass17),
            all_gates=sum(x['gate_pass']=='True' for x in r17), nonpass_new_entries=sum(int(x['cache_entries_delta']) for x in nonpass17),
            scenarios=dict(Counter(x['scenario'] for x in r17)),
            boundary='Live source-level fault modes. Stale-pointer checks are invariant signals, not a memory-sanitizer or all-interleavings proof.'),
        phase18_compact_lifecycle=r18,
        new_GPU_requests=0,
        decision='Reuse these existing fault/cancel/timeout/duplicate data for the bounded fifth-batch evidence. Do not repeat GPU stress unless a specific missing invariant is demonstrated.')

    output.mkdir(parents=True)
    write_csv(output / 'faithful_future_timing_decomposition_v1.csv', detailed)
    write_csv(output / 'faithful_p99_requests_v1.csv', slow)
    write_csv(output / 'margin_observed_RPCs_v1.csv', margin_records)
    write_csv(output / 'margin_fixed_grid_v1.csv', grid_rows)
    write_json(output / 'faithful_p99_summary_v1.json', tail_summary)
    write_json(output / 'known_scope_counterexample_v1.json', known_summary)
    write_json(output / 'PSTP_existing_evidence_v1.json', pstp)
    record(Path(__file__).resolve())
    write_json(output / 'input_inventory_v1.json', inputs)
    write_json(output / 'completion_v1.json', dict(status='CPU_existing_evidence_analysis_complete', new_GPU_requests=0,
        faithful_future_requests=len(detailed), faithful_RPC_responses=len(margin_records),
        post_hoc_grid=list(GRID), no_admission_or_generation_changes=True,
        pending=['Independent open-arrival evidence and its tail decomposition',
                 'Actual economic-gate ON/OFF controlled comparison if existing evidence is insufficient',
                 'Faithful L0/L1/L2/L3 tokenizer/block/displacement analysis',
                 'Real RepoBench layout-only mechanism evidence gap remains separate from synthetic code_context'],
        restrictions=['P99 tails are descriptive per model/process, not independent tenant/source samples.',
            'Previous registration waits are the same shared wait seen by two tenants; never sum them as two GPU executions.',
            'Backend TTFT already includes server-side waiting and prefill; their isolated GPU causal durations are unavailable here.',
            'Existing admission margins only; missing and unexecuted candidate margins cannot be imputed.',
            'No offline margin PASS is a new GPU certification or a guarantee of future behavior.']))
    print(json.dumps(dict(futures=len(detailed), RPCs=len(margin_records), slow_requests=len(slow), output=str(output))))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    main(a.root.resolve(), a.output.resolve())
