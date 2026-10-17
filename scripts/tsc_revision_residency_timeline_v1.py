"""CPU reconstruction of qualified-prefix identity, chronology and block reuse.

The scheduler probe runs after allocation, before GPU execution. An indexed
physical hash is therefore not by itself evidence of completed GPU KV work.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists(), 'Preserve every audit attempt'
    freeze = json.loads((a.root/'freeze.json').read_text())
    config = freeze['protocol']
    assert json.loads((a.root/'analysis/completion_audit_v1.json').read_text())['execution_complete']
    fsha = sha(a.root/'freeze.json')
    assert fsha == '20c10422e075df1e855665668d94d4df408ee664571738a035c1ef60564faf5f'
    for item in freeze['files']:
        assert sha(item['path']) == item['sha256'], item['path']
    samples = read(a.root/'source_snapshot'/config['input_files']['template-fanout'])
    source_order = {r['revision_source_group']: i for i, r in enumerate(samples)}
    timeline, cases, cells = [], [], []
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text())
        if summary['policy'] != 'risk-tail':
            continue
        cell = path.parent
        assert sha(cell/'raw.jsonl') == summary['raw_file_sha256']
        rows = read(cell/'raw.jsonl')
        metrics = [r for r in read(cell/'metrics.jsonl')
                   if r.get('event') == 'prefix_cache_request_observation' and r.get('initial_prefill_observation')]
        metrics.sort(key=lambda r: r['ts'])
        by_id = {r['request_id']: r for r in metrics}
        assert len(by_id) == len(metrics)
        business = [r for r in rows if r['row_type'] in ('warm', 'future')]
        assert len(business) == 600
        by_business = {r['request_id']: r for r in business}
        requests = {r['request_id']: r['payload'] for r in rows if r['row_type'] == 'verification_request'}
        certs = {(r['certificate_namespace'], r['query_scope']): r for r in rows
                 if r['row_type'] == 'verification' and r['certificate_issued']}
        waves = defaultdict(list)
        for r in business:
            tenant = int(r['tenant_id'].rsplit('tenant', 1)[1])
            waves[r['source_group'], tenant//2, r['turn_id']].append(r)
        assert all(len(values) == 2 for values in waves.values())
        # Read-only snapshots of the last observed association of a physical ID.
        state = {}
        last_full = {}
        last_prefix_end = {}
        prefix_work = [0]
        for m in metrics:
            prefix_work.append(prefix_work[-1] + max(0, m['prompt_tokens']-m['prefix_hit_tokens']))
        key_first_block = defaultdict(set)
        local_cases = []
        for index, m in enumerate(metrics):
            rid = m['request_id']
            r = by_business.get(rid)
            block_ids, block_hashes = m['physical_block_ids'], m['physical_block_hashes']
            assert len(block_ids) == len(block_hashes)
            if r:
                tenant = int(r['tenant_id'].rsplit('tenant', 1)[1])
                compiled = r['effective_level'] != 'L0'
                cert = certs[r['certificate_namespace'], r['query_scope']] if compiled else None
                n = int(cert['committed_tokens']) if cert else 0
                stable_n = cert['stable_prefix_tokens'] if cert else 0
                stable_hash = cert['stable_prefix_hash'] if cert else ''
                logical = (r['certificate_namespace'], stable_hash, stable_n) if compiled else None
                expected_salt = fsha+':'+r['certificate_namespace'] if compiled else None
                payload = requests.get(cert.get('request_id')) if cert else None
                if compiled:
                    assert n > 0 and n % 16 == 0 and n <= stable_n
                    assert digest(r['prompt_token_ids'][:stable_n]) == stable_hash
                    assert payload and payload['cache_salt'] == expected_salt
                    assert payload['prompt_token_ids'][:stable_n] == r['prompt_token_ids'][:stable_n]
                    key_first_block[logical].add(digest(r['prompt_token_ids'][:16]))
                start = r['end_time']-r['latency_ms']/1000
                assert abs(start-(r['first_time']-r['ttft_ms']/1000)) < 1e-5
                hit = int(r['prefix_hit_tokens'])
                assert hit == m['prefix_hit_tokens'] and len(r['prompt_token_ids']) == m['prompt_tokens']
                previous = last_full.get(logical) if compiled else None
                entry = {'cell': cell.name, 'model': r['model'], 'repeat': r['repeat'],
                    'source_group': r['source_group'], 'source_order': source_order[r['source_group']],
                    'cohort_start': source_order[r['source_group']]*10+(tenant//2)*2,
                    'tenant_id': r['tenant_id'], 'turn_id': r['turn_id'], 'row_type': r['row_type'],
                    'request_id': rid, 'query_scope': r['query_scope'], 'namespace': r['certificate_namespace'],
                    'policy_hash': fsha, 'client_cache_salt_reconstructed_from_frozen_path': expected_salt,
                    'business_backend_cache_salt_directly_logged': False,
                    'certification_wire_cache_salt': payload['cache_salt'] if payload else None,
                    'selected_level': r['effective_level'], 'committed_tokens': n,
                    'stable_prefix_tokens': stable_n, 'stable_prefix_hash': stable_hash,
                    'first_block_token_ids_sha256': digest(r['prompt_token_ids'][:16]),
                    'prompt_ids_sha256': r['prompt_ids_sha256'], 'prefix_hit_tokens': hit,
                    'new_prefill_tokens': r['new_prefill_tokens'], 'first_backend_physical_hash': block_hashes[0] if block_hashes else None,
                    'first_physical_block_id': block_ids[0] if block_ids else None,
                    'request_start_perf_s': start, 'request_first_token_perf_s': r['first_time'],
                    'request_end_perf_s': r['end_time'], 'scheduler_epoch_s': m['ts'],
                    'scheduler_event_index': index, 'pool_blocks': m['total_gpu_blocks'],
                    'free_blocks_including_cached_refcount_zero': m['free_gpu_blocks'],
                    'scheduler_running_requests': m['scheduler_running_requests'],
                    'initial_physical_block_count': m['physical_block_count'],
                    'previous_same_prefix_end_perf_s': last_prefix_end.get(logical) if compiled else None,
                    'previous_proven_full_hit_request': previous['request_id'] if previous else None,
                    'intervening_initial_new_prefill_tokens_since_full_hit': prefix_work[index]-prefix_work[previous['event_index']+1] if previous else None,
                    'raw_task_score': r['task_score'],
                    'status': 'raw_order' if not compiled else ('full' if hit >= n else ('zero' if hit == 0 else 'partial'))}
                timeline.append(entry)
                if compiled and hit < n:
                    missing_index = hit//16
                    detail = {**entry, 'missing_committed_tokens_upper_bound': n-hit,
                              'first_unhit_committed_block_index': missing_index,
                              'previous_full_block_mapping_available': previous is not None}
                    old_id = previous['block_ids'][missing_index] if previous else None
                    old_hash = previous['block_hashes'][missing_index] if previous else None
                    observed = state.get(old_id) if previous else None
                    changed = bool(previous and observed and observed['event_index'] > previous['event_index']
                                   and observed['hash'] != old_hash)
                    detail.update(previous_missing_block_physical_id=old_id,
                                  previous_missing_block_hash=old_hash,
                                  prior_reassignment_of_first_unhit_block_observed=changed,
                                  prior_reassignment_observation=observed if changed else None,
                                  first_backend_hash_equal_previous_full=(block_hashes[0] == previous['block_hashes'][0]) if previous and block_hashes else None)
                    peers = [x for x in waves[r['source_group'], tenant//2, r['turn_id']] if x['request_id'] != rid]
                    peer = peers[0]
                    pm = by_id[peer['request_id']]
                    shared = sum(x == y for x, y in zip(block_ids[:n//16], pm['physical_block_ids'][:n//16]))
                    detail.update(peer_request_id=peer['request_id'], peer_prefix_hit_tokens=peer['prefix_hit_tokens'],
                                  peer_scheduler_epoch_s=pm['ts'],
                                  peer_same_first_backend_hash=bool(block_hashes and pm['physical_block_hashes'] and block_hashes[0] == pm['physical_block_hashes'][0]),
                                  shared_prefix_block_positions_observed_with_peer=shared,
                                  later_same_wave_full_hit=(pm['ts'] > m['ts'] and peer['effective_level'] != 'L0' and peer['prefix_hit_tokens'] >= n),
                                  causal_eviction_trace_available=False)
                    if changed and detail['first_backend_hash_equal_previous_full']:
                        classification = 'MATCHED_PREFIX_PRIOR_PHYSICAL_BLOCK_REASSIGNMENT'
                    elif detail['later_same_wave_full_hit'] and detail['peer_same_first_backend_hash'] and shared:
                        classification = 'CONCURRENT_COLD_THEN_WARM_WITH_PREWAVE_RESIDENCY_GAP'
                    else:
                        classification = 'INSUFFICIENT_EVIDENCE'
                    detail['classification'] = classification
                    cases.append(detail)
                    local_cases.append(detail)
                if compiled:
                    last_prefix_end[logical] = max(last_prefix_end.get(logical, 0), r['end_time'])
                    if hit >= n:
                        assert len(block_ids) >= n//16
                        last_full[logical] = {'event_index': index, 'request_id': rid,
                                             'block_ids': block_ids[:n//16], 'block_hashes': block_hashes[:n//16]}
            # Apply the current snapshot only AFTER asking about prior reassignments.
            for physical, hashed in zip(block_ids, block_hashes):
                state[physical] = {'hash': hashed, 'event_index': index, 'request_id': rid, 'scheduler_epoch_s': m['ts']}
        assert all(len(values) == 1 for values in key_first_block.values())
        cells.append({'cell': cell.name, 'business_requests': len(business), 'cases': len(local_cases),
                      'raw_sha256': sha(cell/'raw.jsonl'), 'metrics_sha256': sha(cell/'metrics.jsonl'),
                      'manifest_sha256': sha(cell/'runtime_manifest.json'),
                      'all_compiled_stable_prefix_IDs_and_certification_salts_match': True,
                      'classification_counts': dict(Counter(r['classification'] for r in local_cases))})
    assert len(cells) == 9 and len(timeline) == 5400 and len(cases) == 189
    a.output.mkdir(parents=True)
    with (a.output/'residency_identity_timeline.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(timeline[0])); writer.writeheader(); writer.writerows(timeline)
    result = {'schema_version': 'tsc-residency.identity-timeline.v1', 'source_sha256': sha(__file__),
        'primary_freeze_sha256': fsha, 'cells': cells, 'business_requests': len(timeline),
        'cases': cases, 'case_count': len(cases),
        'classification_counts': dict(Counter(r['classification'] for r in cases)),
        'missing_committed_tokens_arithmetic_upper_bound': dict(Counter({model: sum(r['missing_committed_tokens_upper_bound'] for r in cases if r['model'] == model) for model in {r['model'] for r in cases}})),
        'new_GPU_requests': 0,
        'limits': ['Physical hashes are observed after allocation and before GPU execution; indexed is not synonymous with completed.',
                   'Client cache salt is reconstructed from frozen caller code; certification payload salt is directly logged, business backend salt is not.',
                   'Reassignment of a previously hit physical ID is observed; unlogged global duplicate entries or exact eviction triggers are not reconstructed.',
                   'Epoch scheduler and monotonic client times are kept separate, without claiming a measured clock conversion.',
                   'Initial new-prefill counters and missing-prefix token sums are not kernel compute integrals or predicted speedups.']}
    (a.output/'residency_identity_audit_v1.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'cells': len(cells), 'business_requests': len(timeline), 'cases': len(cases),
                      'classifications': result['classification_counts'], 'upper_bound_tokens': result['missing_committed_tokens_arithmetic_upper_bound']}))


if __name__ == '__main__':
    main()
