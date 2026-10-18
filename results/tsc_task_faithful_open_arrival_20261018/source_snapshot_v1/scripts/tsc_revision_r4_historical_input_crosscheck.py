"""Crosscheck recovered historical bytes against pre-R4 exclusion commitments."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path('results/tsc_revision_r4/historical_input_additional_provenance_v1.json')
    if output.exists():
        raise ValueError('Preserve historical provenance supplement')
    prior = Path('results/tsc_revision_r4/inputs/input_commitment_v1.json')
    expected = {r['file']: r['sha256'] for r in json.loads(prior.read_text())['exclusion_files']}
    pairs = [
        ('results/end_to_end/phase19b_untouched_sessions_v0.jsonl', 'results/end_to_end/phase19b_untouched_sessions_v0.jsonl'),
        ('results/mistral/heldout_sealed_sessions_v0.jsonl', 'results/mistral/heldout_sealed_sessions_v0.jsonl'),
        ('results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl', 'results/tsc_revision_r4/historical_input_snapshots_v1/original_llama_sealed.jsonl'),
        ('results/scale_up/qwen3_14b_tp2_v0/frozen_sessions_v0.jsonl', 'results/tsc_revision_r4/historical_input_snapshots_v1/original_qwen14_sealed.jsonl'),
    ]
    records = []
    for original, recovered in pairs:
        actual = sha(Path(recovered))
        if actual != expected[original]:
            raise ValueError('Recovered historical bytes differ from pre-R4 commitment')
        records.append({'original_logical_path': original, 'recovered_path': recovered,
                        'full_file_sha256': actual, 'matches_pre_R4_byte_commitment': True})
    result = {'schema_version': 'tsc-r4.historical-input-additional-provenance.v1',
              'source_sha256': sha(Path(__file__)), 'prior_commitment_sha256': sha(prior),
              'prior_commitment_timestamp': json.loads(prior.read_text())['timestamp'],
              'records': records, 'new_GPU_requests': 0,
              'interpretation': 'The old split digests for Llama/Qwen14 bind identities only, but these recovered full file bytes also match the later pre-R4 exclusion commitments made before this input issue was diagnosed. This strengthens stored-input provenance; it does not create missing historical executed prompt IDs or per-cell source attestations.'}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'historical_full_byte_checks': len(records), 'all_match': True}))


if __name__ == '__main__':
    main()
