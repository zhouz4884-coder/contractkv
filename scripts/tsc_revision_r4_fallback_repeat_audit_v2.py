"""All non-raw policies: match selected L0 anomalies to frozen raw repeats."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import first_divergence


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(ids):
    return hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    assert json.loads((a.root/'analysis/completion_audit_v1.json').read_text())['execution_complete']
    config = json.loads((a.root/'freeze.json').read_text())['protocol']
    selected = defaultdict(list)
    with (a.root/'all_business_quality_v1.csv').open(encoding='utf-8', newline='') as f:
        pairs = list(csv.DictReader(f))
    for r in pairs:
        if r['effective_level'] != 'L0':
            continue
        inflation = int(r['policy_output_tokens']) >= 4*max(1, int(r['raw_output_tokens'])) and int(r['policy_output_tokens'])-int(r['raw_output_tokens']) >= 128
        if float(r['quality_drop']) > .03 or inflation:
            key = r['study'], r['model'], r['session_id'], int(r['turn_id']), r['policy']
            selected[key].append({'repeat': int(r['repeat']), 'quality_drop': float(r['quality_drop']),
                                  'large_length_inflation': inflation})
    indexed = defaultdict(dict)
    provenance = []
    fields = ('effective_level', 'task_score', 'output_text', 'output_token_ids', 'prompt_ids_sha256',
              'finish_reason', 'prefix_hit_tokens', 'ready_ttft_ms', 'latency_ms', 'row_type', 'family', 'source_group')
    wanted = {key[:4] for key in selected}
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        meta = json.loads(path.read_text())
        raw_path = path.with_name('raw.jsonl')
        assert sha(raw_path) == meta['raw_file_sha256']
        for line in raw_path.open(encoding='utf-8'):
            r = json.loads(line)
            if r['row_type'] not in ('warm', 'future'):
                continue
            key = r['study'], r['model'], r['session_id'], r['turn_id']
            if key in wanted:
                indexed[key][r['policy'], int(r['repeat'])] = {**{name: r[name] for name in fields},
                    'repeat': int(r['repeat']), 'policy': r['policy'],
                    'output_signature_sha256': signature(r['output_token_ids'])}
        provenance.append({'cell': path.parent.name, 'raw_sha256': sha(raw_path)})
    cases = []
    for key, events in sorted(selected.items()):
        available = indexed[key[:4]]
        raw = [available['raw-order', r] for r in range(1, config['repeats']+1)]
        policy = [available[key[4], r] for r in range(1, config['repeats']+1)]
        assert len({r['prompt_ids_sha256'] for r in raw+policy if r['effective_level'] == 'L0'}) == 1
        fallback = [r for r in policy if r['effective_level'] == 'L0']
        raw_signatures = {r['output_signature_sha256'] for r in raw}
        extra = {r['output_signature_sha256'] for r in fallback} - raw_signatures
        classification = 'L0_variant_not_observed_in_three_raw_controls' if extra else 'all_L0_variants_observed_in_raw_controls'
        cases.append({'study': key[0], 'model': key[1], 'session_id': key[2], 'turn_id': key[3], 'policy': key[4],
            'source_group': raw[0]['source_group'], 'events': events, 'classification': classification,
            'raw_unique_output_signatures': len(raw_signatures), 'L0_unique_output_signatures': len({r['output_signature_sha256'] for r in fallback}),
            'same_repeat_first_output_ID_divergences': [first_divergence(x['output_token_ids'], y['output_token_ids']) for x, y in zip(raw, policy)],
            'raw_controls': raw, 'policy_controls': policy})
    result = {'schema_version': 'tsc-r4.all-policy-L0-repeat-audit.v2', 'source_sha256': sha(__file__),
              'freeze_sha256': sha(a.root/'freeze.json'), 'cases': cases, 'case_count': len(cases),
              'classifications': dict(Counter(r['classification'] for r in cases)), 'cell_provenance': provenance,
              'new_GPU_requests': 0, 'primary_scores_and_failures_unchanged': True,
              'limits': ['Post-output case selection: all L0 material drops >.03 or >=4x and >=128-token length inflation.',
                         'Raw controls are shared and correlated. Seeing a variant in raw is descriptive, not causal exoneration.',
                         'Absence from three controls is not proof of policy causation. Full-population balance is reported separately.',
                         'Full prompt IDs remain in the verified original archive; this diagnostic retains their checked identity hashes.']}
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'classifications': result['classifications'], 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
