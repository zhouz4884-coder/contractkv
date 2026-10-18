"""Post-output diagnosis of cost denials versus matched original controls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    assert json.loads((a.root/'analysis/completion_audit_v1.json').read_text())['execution_complete']
    config = json.loads((a.root/'freeze.json').read_text())['protocol']
    records = []
    provenance = []
    fields = ('allow_verification', 'reason', 'stage', 'gpu_registration_cost_ms', 'information_cost_ms',
              'estimated_saved_ms', 'estimated_cost_ms', 'expected_net_ms', 'predicted_ready_bound_ms',
              'tail_budget_ms', 'additional_sync_controller_allowance_ms', 'cost_profile_support',
              'cost_profile_bucket_upper_tokens', 'cost_profile_source_clusters', 'prefix_state',
              'save_per_reuse_ms', 'declared_remaining_reuse_hint')
    for repeat in range(1, config['repeats']+1):
        policies = {}
        for policy in ('risk-tail', 'cost-adapted'):
            cell = a.root/'cells'/f'template-fanout_qwen_{policy}_r{repeat}'
            summary = json.loads((cell/'summary.json').read_text())
            assert sha(cell/'raw.jsonl') == summary['raw_file_sha256']
            rows = [json.loads(x) for x in (cell/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            plans = {}
            owners = {}
            decisions = {}
            for row in rows:
                if row['row_type'] not in ('prospective_plan', 'warm', 'future', 'verification'):
                    continue
                key = row['certificate_namespace'], row['query_scope']
                if row['row_type'] == 'prospective_plan':
                    plans[key] = row
                elif row['row_type'] == 'verification':
                    decisions[key] = row
                else:
                    owners.setdefault(key, row)
            policies[policy] = plans, owners, decisions
            provenance.append({'cell': cell.name, 'raw_sha256': sha(cell/'raw.jsonl')})
        original, adapted = policies['risk-tail'], policies['cost-adapted']
        assert set(original[0]) == set(adapted[0])
        for key, old in original[0].items():
            new = adapted[0][key]
            old_owner, new_owner = original[1][key], adapted[1][key]
            assert old_owner['prompt_token_ids'] == new_owner['prompt_token_ids']
            old_plan, new_plan = old.get('plan'), new.get('plan')
            records.append({'repeat': repeat, 'namespace': key[0], 'query_scope': key[1],
                'source_group': old_owner['source_group'], 'family': old_owner['family'],
                'first_raw_prompt_IDs_equal': True,
                'first_raw_output_IDs_equal': old_owner['output_token_ids'] == new_owner['output_token_ids'],
                'candidate_prompt_IDs_equal_if_both_planned': old_plan['prompt_token_ids'] == new_plan['prompt_token_ids'] if old_plan and new_plan else None,
                'original_candidate_prompt_tokens': len(old_plan['prompt_token_ids']) if old_plan else None,
                'adapted_candidate_prompt_tokens': len(new_plan['prompt_token_ids']) if new_plan else None,
                'original': {name: old.get(name) for name in fields},
                'adapted': {name: new.get(name) for name in fields},
                'original_GPU_attempts': len(original[2].get(key, {}).get('attempts', [])),
                'adapted_GPU_attempts': len(adapted[2].get(key, {}).get('attempts', [])),
                'original_issued': original[2].get(key, {}).get('certificate_issued', False),
                'adapted_issued': adapted[2].get(key, {}).get('certificate_issued', False)})
    denied = [r for r in records if not r['adapted']['allow_verification']]
    result = {'schema_version': 'tsc-r4.post-output-cost-gate-effect.v1',
              'source_sha256': sha(__file__), 'freeze_sha256': sha(a.root/'freeze.json'),
              'scope_records': records, 'cell_provenance': provenance,
              'adapted_denial_counts': [dict(zip(('family', 'reason', 'profile_support'), key), scopes=value)
                  for key, value in sorted(Counter((r['family'], str(r['adapted']['reason']), str(r['adapted']['cost_profile_support'])) for r in denied).items())],
              'adapted_denials_with_matched_original_issued': sum(r['original_issued'] for r in denied),
              'adapted_denials_with_original_GPU_attempt': sum(r['original_GPU_attempts'] > 0 for r in denied),
              'new_GPU_requests': 0,
              'limits': ['Original issuance is a matched control label, not a GPU probe of a denied adapted request.',
                         'Identical prompt/witness IDs do not fix physical cache or numerical execution paths.',
                         'No test-outcome-based cost, scope or input tuning. This is descriptive diagnosis after all frozen cells.']}
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'scopes': len(records), 'adapted_denials': len(denied), 'matched_original_issued': result['adapted_denials_with_matched_original_issued']}))


if __name__ == '__main__':
    main()
