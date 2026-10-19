"""Describe actual prefix reuse separately from a valid layout qualification."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    assert json.loads((a.root/'analysis/completion_audit_v1.json').read_text())['execution_complete']
    groups = defaultdict(list)
    cases = []
    provenance = []
    pools = []
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        s = json.loads(path.read_text())
        if s['policy'] == 'raw-order':
            continue
        raw = path.with_name('raw.jsonl')
        assert sha(raw) == s['raw_file_sha256']
        rows = [json.loads(x) for x in raw.read_text(encoding='utf-8').splitlines()]
        certs = {(r['certificate_namespace'], r['query_scope']): r for r in rows
                 if r['row_type'] == 'verification' and r['certificate_issued']}
        for row in rows:
            if row['row_type'] not in ('warm', 'future') or row['effective_level'] == 'L0':
                continue
            c = certs[row['certificate_namespace'], row['query_scope']]
            n = int(c['committed_tokens'])
            assert n > 0 and not row['scope_invalid_admission']
            assert digest(row['prompt_token_ids'][:c['stable_prefix_tokens']]) == c['stable_prefix_hash']
            hit = int(row['prefix_hit_tokens'])
            status = 'zero_native_hit' if hit == 0 else ('full_committed_prefix_hit' if hit >= n else 'partial_committed_prefix_hit')
            record = {'cell': path.parent.name, 'model': row['model'], 'policy': s['policy'],
                      'repeat': s['repeat'], 'source_group': row['source_group'], 'family': row['family'],
                      'session_id': row['session_id'], 'turn_id': row['turn_id'], 'row_type': row['row_type'],
                      'status': status, 'actual_native_hit_tokens': hit, 'committed_tokens': n,
                      'prompt_tokens': len(row['prompt_token_ids']), 'prompt_IDs_sha256': row['prompt_ids_sha256']}
            if status != 'full_committed_prefix_hit':
                cases.append(record)
            for population in ('all_business', row['row_type']):
                for source in ('ALL', row['source_group']):
                    groups[row['model'], s['policy'], population, source].append(record)
        provenance.append({'cell': path.parent.name, 'raw_sha256': sha(raw)})
        log = Path('logs/tsc_revision_r4')/('fidelity_validation_v1_'+path.parent.name+'_server.log')
        if log.exists():
            text = log.read_text(encoding='utf-8', errors='replace')
            sizes = re.findall(r'GPU KV cache size: ([\d,]+) tokens', text)
            pools.append({'cell': path.parent.name, 'server_log_sha256': sha(log),
                          'reported_pool_tokens': [int(x.replace(',', '')) for x in sizes],
                          'preemption_warning_lines': [line for line in text.splitlines()
                                                       if 'WARN' in line and 'preempt' in line.lower()]})
    summaries = []
    for key, rows in sorted(groups.items()):
        summaries.append({**dict(zip(('model', 'policy', 'population', 'source_group'), key)),
                          'compiled_business_answers': len(rows),
                          **{name: sum(r['status'] == name for r in rows) for name in
                             ('full_committed_prefix_hit', 'partial_committed_prefix_hit', 'zero_native_hit')}})
    result = {'schema_version': 'tsc-r4.compiled-layout-vs-native-residency.v1', 'source_sha256': sha(__file__),
              'freeze_sha256': sha(a.root/'freeze.json'), 'summaries': summaries,
              'partial_or_zero_cases': cases, 'cell_provenance': provenance, 'server_pool_observations': pools,
              'new_GPU_requests': 0,
              'limits': ['A valid behavioral/layout qualification is not a guarantee of current full KV residency.',
                         'Initial native prefix-hit counters are not a kernel compute integral or an eviction trace.',
                         'Zero-hit routing does not establish eviction, a namespace bug, or unsafe publication as its cause.',
                         'No warning match does not prove absence of recomputation or eviction. No runtime policy was changed.']}
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'summaries': len(summaries), 'partial_or_zero_cases': len(cases), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
