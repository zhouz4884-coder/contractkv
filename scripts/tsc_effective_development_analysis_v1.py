"""Independent descriptive accounting and bounded development selection."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]
def iterlines(p):
    with p.open(encoding='utf-8') as f:
        for x in f:
            if x.strip():
                yield json.loads(x)
def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()
def write(p, x):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(x, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
def key(r): return r['source_group'], r['session_id'], r['turn_id']


def main(root, output):
    assert not output.exists()
    study = root / 'results/tsc_effective_reuse_recovery_20261019'
    state = read(study / 'development_execution_state_v2.json')
    assert state['status'] == 'COMPLETE_PENDING_DEVELOPMENT_DECISION' and len(state['completed_cells']) == 3
    freeze = read(study / 'freeze_development_v2.json')
    for row in freeze['files']:
        assert sha(root / row['path']) == row['sha256'], row['path']
    output.mkdir(parents=True)
    samples = {r['revision_source_group']: r for r in lines(study / 'development_smoke_inputs_v1.jsonl')}
    dev = {r['revision_source_group']: r for r in lines(study / 'inputs_development_v1/faithful_selected_sessions_v1.jsonl')}
    arms, pairs, candidates, native_rows, violations, choices = [], [], [], [], [], []
    all_business, compiled_pairs = 0, 0
    for relative in state['completed_cells']:
        cell = study / relative
        inventory = read(cell / 'nested_completion_inventory_v1.json')['files']
        for row in inventory:
            assert sha(cell / row['path']) == row['sha256'], row['path']
        data = lines(cell / 'responses.jsonl')
        assert data[-1]['event'] == 'effective_development_cell_complete'
        model = data[0]['model']
        lookups, returns, pubs, used_publications = {}, {}, [], set()
        for row in iterlines(cell / 'backend_trace.jsonl'):
            if row['event'] == 'lookup_before':
                lookups.setdefault(row['request_id'], row)
            elif row['event'] == 'lookup_return' and row['request_id'] in lookups:
                returns.setdefault(row['request_id'], row)
            elif row['event'] == 'verification_cache_blocks_return':
                pubs.append(row)
        def actual(response):
            rid = response['request_id']
            matches = [r for k, r in lookups.items() if k == rid or k.startswith(rid + '-')]
            assert matches, rid
            before = min(matches, key=lambda r: r['seq'])
            after = returns[before['request_id']]
            assert after['seq'] > before['seq']
            assert before['prompt_tokens'] == len(response['prompt_token_ids'])
            return before, after
        baseline = None
        decisions = {}
        for arm in ['raw_authorized', 'V5_authorized', 'deferred_authorized']:
            local = lines(cell / arm / 'raw.jsonl')
            business = [r for r in local if r['row_type'] in {'warm', 'future'}]
            assert len(business) == 60
            all_business += len(business)
            certs = [r for r in local if r['row_type'] == 'verification']
            events = lines(cell / arm / 'authorization_trace.jsonl')
            for r in business:
                sample = samples[r['source_group']]
                score = standard_score(sample['dataset'], sample['task'], r['output_text'], sample.get('answer', ''))[0]
                assert r['task_score'] == score and r['success']
                before, after = actual(r)
                assert before['backend_cache_salt'] == r['actual_authorized_cache_salt']
                assert before['backend_cache_salt'].startswith('ckv-auth-v1:')
                native_rows.append(dict(model=model, arm=arm, request_id=r['request_id'],
                    compiled=r['effective_level'] != 'L0', actual_native_hits=after['hit_tokens'],
                    prompt_tokens=before['prompt_tokens'], actual_authorized_salt_SHA256=hashlib.sha256(before['backend_cache_salt'].encode()).hexdigest()))
            requested = {r['request_id']: r['payload'] for r in local if r['row_type'] == 'verification_request'}
            for cert in certs:
                ids = [r['request_id'] for r in cert['attempts']]
                assert len(ids) <= 1
                rid = ids[0] if ids else None
                publication = [r for r in pubs if rid and (r['request_id'] == rid or r['request_id'].startswith(rid + '-'))]
                if cert['certificate_issued']:
                    assert len(publication) == 1 and publication[0]['requested_tokens'] == cert['committed_tokens']
                    assert publication[0]['backend_cache_salt'] == requested[rid]['cache_salt']
                    used_publications.add(publication[0]['request_id'])
                    same = [r for r in business if r['certificate_namespace'] == cert['certificate_namespace']]
                    assert all(r['actual_authorized_cache_salt'] == requested[rid]['cache_salt'] for r in same)
                else:
                    assert int(cert.get('committed_tokens', 0)) == 0 and not publication
            current = {key(r): r for r in business}
            if baseline is None:
                baseline = current
            else:
                assert current.keys() == baseline.keys()
                for k, r in current.items():
                    ref = baseline[k]
                    equal = (ref['output_token_ids'], ref['finish_reason']) == (r['output_token_ids'], r['finish_reason'])
                    compiled = r['effective_level'] != 'L0'
                    compiled_pairs += compiled
                    delta = r['task_score'] - ref['task_score']
                    pairs.append(dict(model=model, arm=arm, source_group=r['source_group'], tenant=r['tenant_id'],
                        turn=r['turn_id'], compiled=compiled, IDs_and_finish_equal=equal,
                        score_delta=delta, score_up=delta > .03, score_down=delta < -.03))
                    if compiled and not equal:
                        violations.append(pairs[-1])
            decisions[arm] = {(r['certificate_namespace'], r['query_scope']): r for r in certs}
            summary = read(cell / arm / 'summary.json')
            arms.append(dict(model=model, arm=arm, actual_business=len(business),
                compiled_future=sum(r['row_type'] == 'future' and r['effective_level'] != 'L0' for r in business),
                qualification_decisions=len(certs), actual_RPCs=sum(len(r['attempts']) for r in certs),
                accepted=sum(bool(r['certificate_issued']) for r in certs),
                reasons=dict(Counter(r['failure_reason'] or 'PASS' for r in certs)),
                complete_service_wall_s=summary['wall_s_including_all_setup_and_verification'],
                recorded_candidate_planning_ms=sum(r['pre_business_planning_ms'] for r in certs),
                direct_registration_intervals_ms=sum(r['actual_registration_interval_ms'] for r in certs),
                skipped_candidate_preparations=sum(r['candidate_preparation_skipped'] for r in certs),
                actual_signature_checks=sum(r['event'] == 'compiled_binding_check' for r in events),
                failed_signature_checks=sum(r['event'] == 'compiled_binding_check' and not r['admitted'] for r in events),
                all_guard_and_registration_times_in_direct_wall=True,
                shared_engine_development_not_causal_fresh_service_speedup=True))
        a, b = decisions['V5_authorized'], decisions['deferred_authorized']
        assert a.keys() == b.keys()
        lost = [k for k in a if a[k]['certificate_issued'] and not b[k]['certificate_issued']]
        if lost:
            violations.append(dict(model=model, lost_development_PASS_keys=lost))
        probe = [r for r in data if r['event'] == 'candidate_feasibility']
        assert len(probe) == 12
        witness = {r['source_group']: r for r in data if r['event'] == 'development_Raw_witness'}
        assert len(witness) == 4
        all_business += len(probe) + 2 * len(witness)
        for row in probe:
            source = dev[row['source_group']]
            raw, observed = row['reference'], row['observed']
            raw_before, _ = actual(raw)
            observed_before, observed_after = actual(observed)
            payload = next((r['payload'] for r in row['verification_rows'] if r.get('row_type') == 'verification_request'), None)
            publication = [r for r in pubs if payload and (r['request_id'] == payload['request_id'] or r['request_id'].startswith(payload['request_id'] + '-'))]
            if payload:
                assert payload['cache_salt'] == raw_before['backend_cache_salt']
            if row['result']['certificate_issued']:
                assert observed_before['backend_cache_salt'] == raw_before['backend_cache_salt']
                assert len(publication) == 1
                assert publication[0]['requested_tokens'] == row['result']['committed_tokens']
                assert publication[0]['backend_cache_salt'] == payload['cache_salt']
                used_publications.add(publication[0]['request_id'])
            else:
                assert observed_before['backend_cache_salt'] != raw_before['backend_cache_salt']
                assert not publication and int(row['result'].get('committed_tokens', 0)) == 0
            delta = standard_score(source['dataset'], source['task'], observed['output_text'], source.get('answer', ''))[0] - witness[row['source_group']]['task_score']
            candidates.append(dict(model=model, source_group=row['source_group'], family=row['family'], level=row['level'],
                accepted=bool(row['result']['certificate_issued']), reason=row['result']['failure_reason'] or 'PASS',
                RPCs=len(row['result']['attempts']), behavior_equal=row['behavior_equal'],
                usable_development_evidence=row['usable_development_evidence'],
                stable_full_blocks=row['plan']['stable_full_blocks'], actual_native_hits=observed_after['hit_tokens'],
                reference_score=witness[row['source_group']]['task_score'], observed_score_delta=delta,
                complete_probe_elapsed_ms=row['complete_probe_elapsed_ms']))
        assert {r['request_id'] for r in pubs} == used_publications, 'Unaccounted actual candidate publication'
    assert all_business == 600
    for model, family in sorted({(r['model'], r['family']) for r in candidates}):
        allowed = []
        for level in ['L1', 'L2', 'L3']:
            part = [r for r in candidates if (r['model'], r['family'], r['level']) == (model, family, level)]
            assert len(part) == 2
            if all(r['usable_development_evidence'] for r in part):
                allowed.append(dict(level=level, stable_full_blocks=sum(r['stable_full_blocks'] for r in part),
                    mean_complete_probe_ms=statistics.fmean(r['complete_probe_elapsed_ms'] for r in part)))
        choice = max(allowed, key=lambda r: (r['stable_full_blocks'], -r['mean_complete_probe_ms'])) if allowed else None
        choices.append(dict(model=model, family=family, eligible_levels=allowed, chosen=choice,
            production_economic_profile_not_established_by_feasibility=family == 'RepoBench' and not model.startswith('Qwen')))
    summary = dict(status='DEVELOPMENT_ACCOUNTING_COMPLETE', actual_cells=3, actual_business=600,
        full_runner_business=540, candidate_probe_business=60, candidate_probes=36,
        full_runner_compiled_Raw_pairs=compiled_pairs, behavior_or_PASS_retention_violations=violations,
        arms=arms, development_choices=choices, new_GPU_requests=0,
        no_formal_validation_outputs_used=True, source_sha256=sha(Path(__file__)),
        boundary='Known-source shared-engine full-runner smoke and four-source development feasibility. '
        'No direct phase ratio is a causal speedup or open-arrival capacity. No metadata scope or margin threshold is changed.')
    for name, rows in [('paired_quality', pairs), ('candidate_feasibility', candidates), ('actual_native', native_rows)]:
        with (output / (name + '_v1.csv')).open('x', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    write(output / 'summary_v1.json', summary)
    print(json.dumps(dict(status=summary['status'], actual_business=all_business, violations=len(violations), choices=choices)))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    main(a.root.resolve(), a.output.resolve())
