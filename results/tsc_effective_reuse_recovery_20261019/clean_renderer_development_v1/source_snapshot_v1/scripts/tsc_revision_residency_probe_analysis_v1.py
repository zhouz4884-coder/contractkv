"""Join direct pre-lookup state, native eviction and fixed-ID probe responses."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def read(path):
    return [json.loads(s) for s in path.open(encoding='utf-8') if s.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists(), 'Do not replace scientific analysis attempts'
    plan = json.loads((args.root/'probe_plan_v1.json').read_text(encoding='utf-8'))
    freeze = json.loads((args.root/'probe_freeze_v1.json').read_text(encoding='utf-8'))
    expected_pool_sha = next(x['sha256'] for x in freeze['remote_native_read_only_hook_sources']
                             if x['file'] == 'block_pool.py')
    expected_manager_sha = next(x['sha256'] for x in freeze['files']
                                if x['path'].endswith('/kv_cache_manager.py'))
    details, cells = [], []
    for cell in plan['cells']:
        base = args.root/'probe_cells_v1'/cell['alias']
        rows = read(base/'responses.jsonl')
        traces = read(base/'backend_trace.jsonl')
        metrics = read(base/'metrics.jsonl')
        assert rows[-1]['event'] == 'diagnostic_completed'
        assert rows[-1]['businesses'] == 46 and rows[-1]['completed_requests'] == 46
        source_specs = {x['request_id']: x for w in cell['waves'] for x in w['businesses']}
        for row in rows:
            if row['event'] != 'business':
                continue
            spec = source_specs[row['source_request_id']]
            body = row['response']; choice = body['choices'][0]
            assert choice['prompt_token_ids'] == spec['prompt_token_ids']
            assert body['usage']['prompt_tokens'] == len(choice['prompt_token_ids'])
            assert body['usage']['completion_tokens'] == len(choice['token_ids'])
            assert choice['finish_reason'] in ('stop', 'length')
            assert row['archived_output_ids_equal'] == (choice['token_ids'] == spec['output_token_ids'])
        assert not [r for r in metrics if r['event'].endswith('_error')]
        engine_pids = {r['pid'] for r in traces if r['event'] == 'lookup_before'}
        assert len(engine_pids) == 1
        traces = [r for r in traces if r['pid'] in engine_pids]
        installed = {r['module']: r['source_sha256'] for r in traces
                     if r['event'] == 'diagnostic_hook_installed'}
        assert installed['vllm.v1.core.block_pool'] == expected_pool_sha
        assert installed['vllm.v1.core.kv_cache_manager'] == expected_manager_sha
        assert all(b['seq'] > a['seq'] for a, b in zip(traces, traces[1:]))
        lookups = {r['request_id']: r for r in traces if r['event'] == 'lookup_before'}
        returned = {r['request_id']: r for r in traces if r['event'] == 'lookup_return'}
        commits = [r for r in traces if r['event'] == 'verification_cache_blocks_return']
        reclaims = [r for r in traces if r['event'] == 'native_evict_return' and r['removed']]
        assert all(r['ref_before'] == 0 for r in reclaims)
        assert all(r['requested_tokens'] > 0 and r['requested_tokens'] % 16 == 0 for r in commits)
        for r in commits:
            blocks = r['blocks'][0][:r['requested_tokens']//16]
            assert len(blocks) == r['requested_tokens']//16
            assert all(x['hash'] is not None for x in blocks)
        local = []
        for row in rows:
            if row['event'] != 'business' or row['level'] == 'L0':
                continue
            rid = row['actual_request_id']
            matches = [r for k, r in lookups.items() if k == rid or k.startswith(rid+'-')]
            assert len(matches) == 1, rid
            before = matches[0]
            result = returned[before['request_id']]
            assert before['kv_groups'] == 1 and before['block_size'] == 16
            expected = plan['base_freeze_sha256']+':'+cell['namespace']
            assert before['backend_cache_salt'] == expected == row['wire_cache_salt']
            n = cell['accepted_scope_commit_tokens'][row['scope']]
            assert before['certified_boundary_count'] >= n//16
            hits = result['hit_tokens']
            commit_candidates = [x for x in commits if x['seq'] < before['seq']
                                 and x['requested_tokens'] >= n
                                 and [b['hash'] for b in x['blocks'][0][:n//16]] == before['backend_hashes'][:n//16]]
            assert commit_candidates, 'Actual backend chain differs from observed commit'
            detail = {'alias': cell['alias'], 'model': cell['model_identity'], 'source_group': cell['source_group'],
                'label': row['label'], 'request_id': before['request_id'], 'scope': row['scope'],
                'committed_tokens': n, 'native_hit_tokens': hits,
                'status': 'full' if hits >= n else ('zero' if hits == 0 else 'partial'),
                'actual_backend_salt_and_committed_chain_match': True,
                'lookup_seq': before['seq'], 'pool_blocks': before['pool_blocks'],
                'free_blocks_including_cached_eviction_candidates': before['free_blocks'],
                'all_committed_hashes_present_before_lookup': all(before['cached_entries_by_block'][:n//16]),
                'first_unhit_block_index': None, 'first_unhit_backend_hash': None,
                'pre_lookup_missing_block_has_native_last_entry_eviction': False,
                'eviction_seq': None, 'eviction_request_id': None, 'evicted_physical_id': None,
                'eviction_ref_before': None, 'duplicates_after_eviction': None,
                'archived_output_ids_equal_diagnostic_only': row['archived_output_ids_equal']}
            if hits < n:
                index = hits//16
                key = before['backend_hashes'][index]
                assert not before['cached_entries_by_block'][index], 'Miss despite indexed exact requested block'
                events = [x for x in reclaims if x['old_hash'] == key and x['duplicate_entries_after'] == 0
                          and commit_candidates[0]['seq'] < x['seq'] < before['seq']]
                detail.update(first_unhit_block_index=index, first_unhit_backend_hash=key)
                if events:
                    ev = events[-1]
                    detail.update(pre_lookup_missing_block_has_native_last_entry_eviction=True,
                                  eviction_seq=ev['seq'], eviction_request_id=ev['request_id'],
                                  evicted_physical_id=ev['block_id'], eviction_ref_before=ev['ref_before'],
                                  duplicates_after_eviction=ev['duplicate_entries_after'])
            details.append(detail); local.append(detail)
        gaps = [r for r in local if r['status'] != 'full']
        controls = [r for r in local if r['label'].startswith('immediate-')]
        final_serial = [r for r in local if r['label'].startswith('final-serial-')]
        replay_rows = [r for r in local if r['label'].startswith('c')]
        cells.append({'alias': cell['alias'], 'model': cell['model_identity'],
            'source_group': cell['source_group'], 'completed_business': 46,
            'verification_requests': sum(r['event'] == 'verification_request' for r in rows),
            'verification_passes': sum(r['event'] == 'verification_response' and r['response']['certificate_issued'] for r in rows),
            'compiled_probe_requests': len(local), 'status_counts': dict(Counter(r['status'] for r in local)),
            'all46_actual_prompt_ID_arrays_independently_match_frozen_plan': True,
            'immediate_post_commit_control_count': len(controls),
            'immediate_controls_all_full_committed_prefix_hits': all(r['status'] == 'full' for r in controls),
            'final_serial_statuses': [r['status'] for r in final_serial],
            'final_serial_hit_tokens': [r['native_hit_tokens'] for r in final_serial],
            'replayed_original_wave_status_counts': dict(Counter(r['status'] for r in replay_rows)),
            'archived_output_ID_match_count_diagnostic_only': sum(r['event'] == 'business' and r['archived_output_ids_equal'] for r in rows),
            'all_gaps_have_direct_native_eviction_and_prelookup_absence': bool(gaps) and all(r['pre_lookup_missing_block_has_native_last_entry_eviction'] for r in gaps),
            'direct_native_eviction_events': len(reclaims), 'all_evictions_reference_count_zero': True,
            'files': {name: sha(base/name) for name in ('responses.jsonl','backend_trace.jsonl','metrics.jsonl','runtime_manifest.json')}})
    assert sum(r['completed_business'] for r in cells) == 138 <= plan['maximum_business_requests']
    assert sum(r['verification_requests'] for r in cells) <= plan['maximum_verification_requests']
    args.output.mkdir(parents=True)
    with (args.output/'compiled_probe_trace.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(details[0])); writer.writeheader(); writer.writerows(details)
    result = {'schema_version': 'tsc-residency.probe-analysis.v1', 'cells': cells,
              'compiled_probes': details, 'source_sha256': sha(Path(__file__)),
              'probe_plan_sha256': sha(args.root/'probe_plan_v1.json'),
              'limitations': ['Only three known-source diagnostic cells; historical 189 cases do not have per-case causal eviction traces.',
                             'Fixed-ID completion requests and archived witnesses are not a fresh independent behavior validation.',
                             'Synchronous read-only logging invalidates performance interpretation of diagnostic timings.',
                             'Current allocation hooks preserve native functions but do not prove every other workload free of implementation defects.']}
    (args.output/'probe_mechanism_results_v1.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print(json.dumps({'cells': cells}, indent=2))


if __name__ == '__main__':
    main()
