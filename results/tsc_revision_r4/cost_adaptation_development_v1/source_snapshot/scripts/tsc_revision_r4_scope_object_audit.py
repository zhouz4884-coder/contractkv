"""Offline scope/amortization accounting; no new certificate implementation.

Added after R4 freezes to connect measured modes with the claimed service
objects. Primary policies, scorers, frozen analyses and GPU runs stay unchanged.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve previous scope-object audit version')
    freeze = args.root / 'freeze.json'
    protocol = json.loads(freeze.read_text())['protocol']
    complete = args.root / 'analysis/completion_audit_v1.json'
    if not args.allow_partial:
        if not json.loads(complete.read_text())['execution_complete']:
            raise ValueError('Full study completion proof is required')
    records = []
    for path in sorted((args.root / 'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text())
        if summary['policy'] == 'raw-order':
            continue
        raw = path.with_name('raw.jsonl')
        if not summary['execution_complete'] or sha(raw) != summary['raw_file_sha256']:
            raise ValueError('Incomplete/changed measured cell')
        rows = read(raw)
        groups = defaultdict(list)
        for row in rows:
            if row['row_type'] in ('warm', 'future', 'prospective_plan', 'verification'):
                groups[row['certificate_namespace']].append(row)
        for namespace, group in sorted(groups.items()):
            business = [r for r in group if r['row_type'] in ('warm', 'future')]
            decisions = [r for r in group if r['row_type'] == 'verification']
            plans = [r for r in group if r['row_type'] == 'prospective_plan']
            issued = [r for r in decisions if r['certificate_issued']]
            compiled = [r for r in business if r['effective_level'] != 'L0']
            scopes = sorted({r['query_scope'] for r in business})
            expected_salt = sha(freeze) + ':' + namespace
            payloads = [r['payload'] for r in rows if r['row_type'] == 'verification_request'
                        and r['payload'].get('cache_salt') == expected_salt]
            prefixes = sorted({(r['stable_prefix_hash'], r['stable_prefix_tokens']) for r in issued})
            per_scope = []
            for scope in scopes:
                called = [r for r in decisions if r['query_scope'] == scope]
                used = [r for r in compiled if r['query_scope'] == scope]
                per_scope.append({
                    'query_scope': scope,
                    'business_requests': sum(r['query_scope'] == scope for r in business),
                    'decision_records': len(called),
                    'GPU_attempts': sum(len(r['attempts']) for r in called),
                    'issued': any(r['certificate_issued'] for r in called),
                    'compiled_all_business_requests': len(used),
                    'compiled_future_requests': sum(r['row_type'] == 'future' for r in used),
                    'tenant_sessions_with_compiled_reuse': len({r['tenant_id'] for r in used}),
                    'failure_reasons': dict(Counter(r['failure_reason'] for r in called if not r['certificate_issued'])),
                })
            records.append({
                'cell': path.parent.name, 'study': summary['study'], 'model': business[0]['model'],
                'policy': summary['policy'], 'repeat': summary['repeat'], 'namespace': namespace,
                'observed_tenant_sessions': len({r['tenant_id'] for r in business}),
                'business_requests': len(business), 'future_requests': sum(r['row_type'] == 'future' for r in business),
                'observed_behavioral_scope_count_U': len(scopes),
                'prospective_plan_records': len(plans), 'decision_records': len(decisions),
                'GPU_attempts': sum(len(r['attempts']) for r in decisions),
                'issued_behavioral_scope_records': len(issued),
                'distinct_returned_certificate_hashes': len({r['certificate_hash'] for r in issued}),
                'observed_issued_stable_prefix_hash_objects': len(prefixes),
                'stable_prefix_hash_objects': [{'hash': h, 'stable_prefix_tokens': n} for h, n in prefixes],
                'verification_requests_using_template_namespace_salt': len(payloads),
                'compiled_all_business_requests': len(compiled),
                'compiled_future_requests': sum(r['row_type'] == 'future' for r in compiled),
                'compiled_requests_with_actual_prefix_hit': sum(int(r['prefix_hit_tokens']) > 0 for r in compiled),
                'scope_records': per_scope,
                'raw_file_sha256': sha(raw), 'summary_sha256': sha(path),
            })
    source_paths = [
        'scripts/tsc_revision_r4_live.py', 'scripts/tsc_revision_r4_live_fixed.py',
        'scripts/tsc_revision_r1r_query_scope.py', 'scripts/tsc_revision_r4_cost_policy.py',
        'scripts/tsc_revision_r2_admission.py', 'scripts/tsc_revision_r2_candidate_plan.py',
        'scripts/tsc_revision_r2_business_stream.py', 'scripts/tsc_revision_r4_policy_v2.py',
        'scripts/tsc_service_template_quality_live.py', 'scripts/tsc_open_loop_service.py',
        'scripts/tsc_real_task_open_loop.py', 'scripts/contractkv_certificate_binding.py',
    ]
    provenance = []
    for relative in source_paths:
        snapshot = args.root / 'source_snapshot' / relative
        source = snapshot if snapshot.exists() else Path(relative)
        provenance.append({'logical_path': relative, 'source_read': source.as_posix(),
                           'sha256': sha(source), 'from_this_study_frozen_snapshot': snapshot.exists()})
    original = Path('results/tsc_service/certificate_granularity_ablation_v0.csv')
    with original.open(encoding='utf-8', newline='') as stream:
        original_rows = list(csv.DictReader(stream))
    result = {
        'schema_version': 'tsc-r4.scope-object-amortization-audit.v1',
        'partial': args.allow_partial, 'study_root': args.root.as_posix(),
        'study_development_only': protocol.get('development_only', False),
        'freeze_sha256': sha(freeze), 'analysis_source_sha256': sha(Path(__file__)),
        'new_GPU_requests': 0, 'frozen_primary_policy_or_analysis_changed': False,
        'records': records, 'source_provenance': provenance,
        'original_granularity_evidence': {'path': original.as_posix(), 'sha256': sha(original),
                                          'rows_unmodified': original_rows},
        'implementation_findings': [
            'R4 client gates and decisions use (template namespace, query scope); tenant sessions sharing that pair reuse its decision.',
            'R4 prefix-state forecasts use template namespace and stable-prefix hash. Verification and compiled business use a template namespace cache salt.',
            'R4 stores a joint per-scope registration result. These two indexes do not demonstrate two independently signed or separately enforced certificate objects.',
            'The older deployment-template modes attest a compiled-path reference after prospective qualification. R4 uses a real raw business witness. Their attestation semantics and costs must remain separate.',
            'Signed binding checks in the original real-task serving control plane are distinct from R4 controlled-client query eligibility; this audit does not establish a new public-endpoint authentication defense.',
        ],
        'complexity_and_limits': [
            'For T template objects and U observed behavioral scope keys, the R4 controller stores O(T+U) state and creates O(U) prospective decisions. Each selected key has at most one GPU attempt.',
            'For M requests in a fixed authorized scope set, control checks are O(M) and behavioral model work can be amortized across tenants. O(1) per template requires U to be treated as fixed.',
            'When distinct behavioral scopes grow with request count, model attestation work may grow linearly if admitted; no measurement here establishes production query repetition prevalence.',
            'Current benchmark reuse hints are operator-declared fixed three-query patterns, not a measured production reuse predictor.',
            'A repeated stable-prefix hash is not an independently signed template certificate, a count of distinct newly allocated blocks, or a universal future-behavior guarantee.',
            'The metadata-only scope schema intentionally ignores allowed metadata values. It defines an empirical class; unchanged task evidence does not prove model-output invariance.',
            'Original granularity rows use their own frozen deployment protocol. Do not subtract their latency from R4 or call this CPU accounting a new live scaling experiment.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'template_namespace_records': len(records),
                      'complete_cells_read': len({r['cell'] for r in records}),
                      'partial': args.allow_partial, 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
