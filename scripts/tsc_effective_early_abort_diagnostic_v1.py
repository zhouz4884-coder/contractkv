"""CPU-only first-failure and token-tail opportunity audit; no early abort implementation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def observation(dataset, model, family, condition, payload, result, trace=None, raw_all_min=None):
    answer = len(payload['reference_answer_ids'])
    prompt = payload['verify_start_token']
    supplied = len(payload['prompt_token_ids'])
    assert supplied == prompt + answer + 1
    cached = int(result.get('cached_prefix_read_tokens', 0))
    first, provenance = None, 'not_retained'
    if trace:
        assert trace['reference_answer_ids'] == payload['reference_answer_ids']
        assert len(trace['candidate_ranks']) == len(trace['candidate_margins']) == answer
        failing = [i for i, (rank, margin) in enumerate(zip(trace['candidate_ranks'], trace['candidate_margins']))
                   if rank != 1 or margin < .125]
        if trace['terminal_stop_rank'] != 1 or trace['terminal_stop_margin'] < .125:
            failing.append(answer)
        first = min(failing) if failing else None
        provenance = 'complete_actual_per_position_rank_margin_and_EOS_trace'
        assert not result['certificate_issued'] or first is None
    elif result.get('candidate_margin_min') is not None:
        # A global argmin is only the first failing token when it is index 0.
        # Never relabel an arbitrary minimum-margin position as the earliest.
        if result['candidate_margin_min'] < .125 and result.get('candidate_margin_min_index') == 0:
            first, provenance = 0, 'first_position_itself_fails_in_actual_summary'
        elif result['candidate_margin_min'] >= .125 and result.get('terminal_stop_margin', float('inf')) < .125:
            first, provenance = answer, 'all_answer_margins_pass_and_actual_EOS_margin_fails'
    uncached_proxy = supplied - cached
    assert uncached_proxy > 0 and 0 <= cached <= prompt
    tail = max(0, answer - first) if first is not None else None
    return dict(dataset=dataset, model=model, family=family, condition=condition,
        actual_request_id=payload['request_id'], accepted=bool(result['certificate_issued']),
        reason=result.get('failure_reason', ''), Raw_all_tokens_margin_min=raw_all_min,
        proposed_Raw_0125_gate_would_skip=raw_all_min is not None and raw_all_min < .125,
        candidate_answer_margin_min=result.get('candidate_margin_min'),
        terminal_stop_margin=result.get('terminal_stop_margin'),
        candidate_prompt_tokens=prompt, witness_answer_tokens=answer, EOS_tokens=1,
        actual_supplied_forced_token_slots=supplied, actual_cached_prefix_read_tokens=cached,
        uncached_supplied_token_slots_proxy=uncached_proxy,
        earliest_candidate_failure_index=first, failure_position_provenance=provenance,
        tail_witness_positions_after_failure=tail,
        optimistic_tail_slot_fraction=tail / uncached_proxy if tail is not None else None,
        actual_verification_RPC_ms=result.get('verification_ms'),
        pure_GPU_kernel_time_available=False,
        caveat='Token-slot proxy only: no FLOP/time conversion. Current full forward has already completed before this trace. '
               'Chunk padding, attention/projection cost, synchronization, queueing, and any staged re-execution overhead are not measured here.')


def main(root, output):
    assert not output.exists()
    data, inventory = [], []
    old = root / '.artifacts/authorization_repair_restore_v1/results/tsc_authorization_task_repair_20261019'
    for relative in read(old / 'execution_state_v2.json')['completed_cells']:
        cell = old / relative
        rr, traces = rows(cell / 'responses.jsonl'), rows(cell / 'verify_trace.jsonl')
        actual = {r['request_id']: r for r in traces if r.get('event') == 'r2_actual_verify_answer_eos_rows'}
        for q in [r for r in rr if r['event'] == 'qualification']:
            requests = [r for r in rr if r['event'] == 'qualification_detail' and r['case_id'] == q['case_id']
                        and r['phase'] == q['phase'] and r.get('row_type') == 'verification_request']
            if not requests:
                assert not q['result']['attempts']
                continue
            assert len(requests) == len(q['result']['attempts']) == 1
            req, result = requests[0]['payload'], q['result']['attempts'][0]
            trace = actual.get(req['request_id'])
            assert trace is not None
            family = next(r['family'] for r in rr if r['event'] == 'business' and r['case_id'] == q['case_id'])
            data.append(observation('authorized_transport_9_cells', rr[0]['model'], family, q['phase'],
                req, result, trace, q['result'].get('raw_all_tokens_margin_min')))
        inventory.extend(dict(path=(cell / name).relative_to(root).as_posix(), sha256=sha(cell / name))
                         for name in ['responses.jsonl', 'verify_trace.jsonl'])
    assert len(data) == 75 and sum(not r['accepted'] for r in data) == 33
    serving = root / '.artifacts/faithful_serving_restore_v1/results/tsc_task_faithful_open_arrival_20261018/formal/cells'
    for cell in sorted(serving.glob('qwen_*risk-tail_on')):
        rr = rows(cell / 'raw.jsonl')
        requests = {r['request_id']: r['payload'] for r in rr if r['row_type'] == 'verification_request'}
        model = next(r['model'] for r in rr if r['row_type'] == 'warm')
        for q in [r for r in rr if r['row_type'] == 'verification']:
            for result in q['attempts']:
                req = requests[result['request_id']]
                data.append(observation('F8_Qwen_common_and_high_6_cells', model, q['family'], cell.name,
                    req, result, None, q.get('raw_all_tokens_margin_min')))
        inventory.append(dict(path=(cell / 'raw.jsonl').relative_to(root).as_posix(), sha256=sha(cell / 'raw.jsonl')))
    groups = []
    for name in sorted({r['dataset'] for r in data}):
        rr = [r for r in data if r['dataset'] == name]
        failed = [r for r in rr if not r['accepted']]
        known = [r for r in failed if r['earliest_candidate_failure_index'] is not None]
        low = [r for r in rr if r['proposed_Raw_0125_gate_would_skip']]
        groups.append(dict(dataset=name, actual_RPCs=len(rr), PASS=sum(r['accepted'] for r in rr),
            FAIL=len(failed), earliest_failure_available=len(known),
            observed_first_token_failures=sum(r['earliest_candidate_failure_index'] == 0 for r in failed),
            hypothetical_Raw_0125_rejections=len(low),
            PASS_lost_by_hypothetical_Raw_0125=sum(r['accepted'] for r in low),
            failed_RPC_ms=sum(r['actual_verification_RPC_ms'] or 0 for r in failed),
            known_failure_tail_slot_fractions=[r['optimistic_tail_slot_fraction'] for r in known],
            cold_or_no_cached_prefix_failed=sum(r['actual_cached_prefix_read_tokens'] == 0 for r in failed),
            source_or_process_independence_not_assumed=True))
    result = dict(schema_version='contractkv.early-abort-CPU-opportunity.v1', new_GPU_requests=0,
        no_gate_or_runtime_modified=True, groups=groups, rows=data, inputs=inventory,
        source_sha256=sha(Path(__file__)),
        decision_boundary='Do not raise Raw floor or claim 80 percent GPU saving. RPC success and business coverage are distinct. '
        'Per-position evidence is retained only in the transport diagnostic; incomplete F8 earliest positions remain missing. '
        'New development traces must be analyzed separately before a staged-forward Oracle microbenchmark is justified.')
    with output.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(groups))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    main(a.root.resolve(), a.output.resolve())
