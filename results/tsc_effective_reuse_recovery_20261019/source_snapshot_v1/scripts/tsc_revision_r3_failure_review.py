"""Review retained material regressions from sealed R3 requests; no inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_divergence(a, b):
    for index, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return index
    return -1 if len(a) == len(b) else min(len(a), len(b))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve the prior failure review')
    audit = json.loads((args.root / 'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']:
        raise ValueError('Complete the independent audit first')
    pair_path = args.root / 'analysis/quality_pairs_v1.csv'
    with pair_path.open(encoding='utf-8', newline='') as stream:
        bad = [r for r in csv.DictReader(stream) if r['effective_level'] != 'L0' and float(r['quality_drop']) > .03]
    keys = {'Qwen3-8B': 'qwen', 'Mistral-7B-Instruct-v0.3': 'mistral', 'Llama-3.1-8B-Instruct': 'llama'}
    cached = {}

    def rows(path):
        if path not in cached:
            with path.open(encoding='utf-8') as stream:
                cached[path] = [json.loads(line) for line in stream]
        return cached[path]

    reviewed = []
    for pair in bad:
        stem = pair['study'] + '_' + keys[pair['model']] + '_'
        suffix = '_r' + pair['repeat']
        policy_dir = args.root / 'cells' / (stem + pair['policy'] + suffix)
        raw_dir = args.root / 'cells' / (stem + 'raw-order' + suffix)
        policy_path, raw_path = policy_dir / 'raw.jsonl', raw_dir / 'raw.jsonl'
        policy, raw = rows(policy_path), rows(raw_path)
        future = next(r for r in policy if r['row_type'] == 'future' and
                      r['session_id'] == pair['session_id'] and r['turn_id'] == int(pair['turn_id']))
        baseline = next(r for r in raw if r['row_type'] == 'future' and
                        r['session_id'] == pair['session_id'] and r['turn_id'] == int(pair['turn_id']))
        scope = future['certificate_namespace'], future['query_scope']
        witness = next(r for r in policy if r['row_type'] in ('warm', 'future') and
                       r['scope_first_raw_business'] and (r['certificate_namespace'], r['query_scope']) == scope)
        decision = next(r for r in policy if r['row_type'] == 'verification' and
                        (r['certificate_namespace'], r['query_scope']) == scope)
        baseline_witness = next(r for r in raw if r['row_type'] in ('warm', 'future') and
                                r['session_id'] == witness['session_id'] and r['turn_id'] == witness['turn_id'])
        reviewed.append({'pair': pair, 'query_scope': future['query_scope'],
                         'policy_raw_sha256': sha(policy_path), 'baseline_raw_sha256': sha(raw_path),
                         'raw_full_margin_min': min(witness['reference_margins']),
                         'raw_stop_margin': witness['reference_margins'][-1],
                         'candidate_margin_min': decision['candidate_margin_min'],
                         'candidate_stop_margin': decision['terminal_stop_margin'],
                         'witness_turn': witness['turn_id'], 'witness_text': witness['output_text'],
                         'witness_score': witness['task_score'],
                         'baseline_at_witness_text': baseline_witness['output_text'],
                         'witness_baseline_same_prompt_IDs': witness['prompt_token_ids'] == baseline_witness['prompt_token_ids'],
                         'witness_baseline_same_output_IDs': witness['output_token_ids'] == baseline_witness['output_token_ids'],
                         'future_witness_same_output_IDs': future['output_token_ids'] == witness['output_token_ids'],
                         'raw_future_text': baseline['output_text'], 'compiled_future_text': future['output_text'],
                         'first_divergence_from_raw_future': first_divergence(baseline['output_token_ids'], future['output_token_ids']),
                         'first_divergence_from_witness': first_divergence(witness['output_token_ids'], future['output_token_ids']),
                         'raw_gpu': json.loads((raw_dir / 'runtime_manifest.json').read_text(encoding='utf-8'))['declared_gpu_lane'],
                         'policy_gpu': json.loads((policy_dir / 'runtime_manifest.json').read_text(encoding='utf-8'))['declared_gpu_lane']})
    result = {'schema_version': 'tsc-r3.sealed-failure-review.v1', 'source_quality_pairs_sha256': sha(pair_path),
              'analysis_source_sha256': sha(Path(__file__)), 'material_threshold': .03,
              'compiled_material_pairs': len(reviewed),
              'distinct_model_source_query_units': len({(r['pair']['model'], r['pair']['source_group'], r['query_scope']) for r in reviewed}),
              'reviewed': reviewed, 'new_inference_requests': 0, 'admission_and_evaluator_changed': False,
              'boundary': 'Observed selected-failure diagnosis; no universal numerical cause or unseen efficacy inferred.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'reviewed'}))


if __name__ == '__main__':
    main()
