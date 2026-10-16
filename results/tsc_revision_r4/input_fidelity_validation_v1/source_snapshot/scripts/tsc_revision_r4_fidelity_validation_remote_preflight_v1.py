"""Native-tokenizer CPU recheck of the frozen independent input population."""
import hashlib
import json
from pathlib import Path
import sys
from copy import deepcopy
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import CapacityCheck, ordered_candidates, read
from scripts.tsc_revision_build_inputs import source
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter
from transformers import AutoTokenizer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    base = Path('results/tsc_revision_r4')
    study = base/'input_fidelity_validation_v1'
    output = study/'independent_remote_CPU_preflight_v1.json'
    assert not output.exists(), 'Preserve every CPU check'
    freeze = json.loads((study/'freeze.json').read_text(encoding='utf-8'))
    for item in freeze['files']:
        assert sha(item['path']) == item['sha256']
        assert sha(study/'source_snapshot'/item['path']) == item['sha256']
    directory = base/'input_fidelity_validation_inputs_v1'
    record = json.loads((directory/'preparation_record_v1.json').read_text(encoding='utf-8'))
    for item in record['data_files']:
        assert sha(item['path']) == item['sha256']
    config = freeze['protocol']
    generation = json.loads(Path(config['generation_protocol']).read_text(encoding='utf-8'))
    catalog = json.loads(Path(config['selected_catalog']).read_text(encoding='utf-8'))
    registry = json.loads((base/'model_registry_v1.json').read_text(encoding='utf-8'))
    tokenizers = {model['model']: AutoTokenizer.from_pretrained(model['model_path'], local_files_only=True)
                  for model in registry['models']}
    selected = read(directory/'faithful_selected_sessions_v1.jsonl')
    check = CapacityCheck(generation, catalog, tokenizers)
    ledgers = {row['source_group']: row for row in record['source_ledgers']}
    exclusions = json.loads((base/'fidelity_complete_exclusion_audit_v1.json').read_text(encoding='utf-8'))
    pool = Path('results/workload/phase14d_full_pool_v2.jsonl')
    assert sha(pool) == record['source_pool_sha256']
    examined = record['candidates_examined_in_frozen_hash_order']
    pool_rows = read(pool)
    for family in ('HotpotQA', 'RepoBench'):
        ordered = ordered_candidates(pool_rows, set(exclusions['excluded_source_groups']), family, 10672146)
        observed = [row for row in examined if row['family'] == family]
        assert [source(row) for row in ordered[:len(observed)]] == [row['source_group'] for row in observed]
        assert [row['source_group'] for row in observed if row['critical_capacity_eligible']] == [source(row) for row in selected if row['revision_family'] == family]
    results = []
    with installed_adapter():
        for row in selected:
            actual = check(row, True)
            expected = ledgers[source(row)]['fit_calls'][-1]['result']
            assert actual == expected, 'Native tokenizers differ from local complete window checks'
            results.append({'source_group': source(row), 'fit': actual})
    assert len(results) == 6 and sum(row['fit']['checked_request_variants'] for row in results) == 1800
    result = {'schema_version': 'tsc-r4.independent-fidelity-native-tokenizer-preflight.v1',
              'source_sha256': sha(__file__), 'freeze_sha256': sha(study/'freeze.json'),
              'input_preparation_sha256': sha(directory/'preparation_record_v1.json'),
              'sources': 6, 'declared_model_tenant_turn_variants': 1800,
              'actual_raw_and_selected_candidate_prompts_checked': True,
              'all_selected_variants_fit_and_preserve_critical_fields': True,
              'native_and_copied_tokenizer_window_checks_exact': True,
              'selection_prefix_hash_order_verified': True, 'source_disjointness_verified': True,
              'new_GPU_requests': 0, 'results': results}
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'independent_native_CPU_preflight': 'PASS', 'sources': 6, 'variants': 1800}))


if __name__ == '__main__':
    main()
