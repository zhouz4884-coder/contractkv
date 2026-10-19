"""Select and pack six independent sources without observing model outcomes.

The input packer, contiguous renderer, model windows, candidate levels and task
budgets are the already executed DEV versions. Only source identity and critical
capacity eligibility determine selection. No labels, scores or speed filters.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

for key, value in {'TOKENIZERS_PARALLELISM': 'false', 'HF_HUB_OFFLINE': '1',
                   'TRANSFORMERS_OFFLINE': '1', 'USE_TORCH': '0', 'USE_TF': '0',
                   'CUDA_VISIBLE_DEVICES': ''}.items():
    os.environ[key] = value
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import family, source
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter, ordered_text_preserving_segments
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from transformers import AutoTokenizer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in Path(path).open(encoding='utf-8') if line.strip()]


def ordered_candidates(rows, excluded, selected_family, seed):
    unique = {}
    for row in rows:
        identity = source(row)
        if identity not in excluded and family(row) == selected_family:
            unique.setdefault(identity, row)
    return sorted(unique.values(), key=lambda row: hashlib.sha256(
        (str(seed) + ':' + source(row)).encode()).hexdigest())


class CapacityCheck:
    def __init__(self, generation, catalog, tokenizers):
        self.generation, self.catalog, self.tokenizers = generation, catalog, tokenizers
        self.arguments = {model: SimpleNamespace(protocol=generation, experiment='free-generation',
                                                output_budget=0, model_identity=model,
                                                policy_hash='input-fidelity-CPU-only') for model in tokenizers}

    def __call__(self, candidate, exhaustive):
        maxima = {}
        checked = 0
        guard = 0 if exhaustive else 128
        for model, tokenizer in self.tokenizers.items():
            maximum = 0
            for tenant in range(10) if exhaustive else (9,):
                sample = deepcopy(candidate)
                sample['revision_input_fidelity'] = {'protocol': 'structure-preserving-window-v2'}
                sample['shared_template_id'] = candidate['revision_session_id']
                sample['revision_session_id'] += f'-tenant{tenant:02d}'
                for turn in range(10) if exhaustive else (0, 1, 2):
                    case, raw, _, budget, _ = prepare(self.arguments[model], sample, turn)
                    raw_ids = tokenizer.apply_chat_template(raw, tokenize=True, add_generation_prompt=True, truncation=False)
                    level = self.catalog['models'][model]['template-fanout'][sample['revision_family']]['level']
                    compiled = raw
                    if level != 'L0':
                        order = layout_for_level(case, level, self.generation['layout']['ladder'])['topological_order']
                        compiled = [raw[0], {'role': 'user', 'content': ordered_text_preserving_segments(order, case['segments'])}]
                        candidate_ids = tokenizer.apply_chat_template(compiled, tokenize=True, add_generation_prompt=True, truncation=False)
                    else:
                        candidate_ids = raw_ids
                    for segment in sample['segments']:
                        if segment['type'] == 'CODE_PREFIX':
                            assert segment['text'] in raw[1]['content']
                            assert segment['text'] in compiled[1]['content']
                    total = max(len(raw_ids), len(candidate_ids)) + budget
                    maximum = max(maximum, total)
                    checked += 1
                    if total + guard > 16384:
                        return {'fits': False, 'checked_request_variants': checked,
                                'all_declared_variants_checked': False, 'conservative_guard_tokens': guard,
                                'first_failure': {'model': model, 'tenant': tenant, 'turn': turn,
                                                  'prompt_plus_budget': total}, 'completed_model_maxima': maxima}
            maxima[model] = maximum
        return {'fits': True, 'checked_request_variants': checked,
                'all_declared_variants_checked': exhaustive, 'conservative_guard_tokens': guard,
                'max_prompt_plus_budget_by_model': maxima}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tokenizer-root', type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError('Preserve every independent preparation attempt')
    base = Path('results/tsc_revision_r4')
    pool = Path('results/workload/phase14d_full_pool_v2.jsonl')
    original_commitment = json.loads((base/'inputs/input_commitment_v1.json').read_text(encoding='utf-8'))
    assert sha(pool) == original_commitment['source_pool_sha256']
    exclusions_path = base/'fidelity_complete_exclusion_audit_v1.json'
    exclusions = json.loads(exclusions_path.read_text(encoding='utf-8'))
    excluded = set(exclusions['excluded_source_groups'])
    assert len(excluded) == 567
    assert hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest() == exclusions['excluded_set_sha256']
    primary_record_path = base/'input_fidelity_validation_inputs_v1/preparation_record_v1.json'
    primary_record = json.loads(primary_record_path.read_text(encoding='utf-8'))
    assert len(set(primary_record['selected_source_groups'])) == 6
    excluded.update(primary_record['selected_source_groups'])
    assert len(excluded) == 573
    dev = base/'cost_adaptation_development_v1'
    assert json.loads((dev/'fixed_DEV_decision_v1.json').read_text())['all_prespecified_DEV_checks_pass']
    assert json.loads((dev/'local_independent_recompute_v1.json').read_text())['independent_local_recomputation_complete']
    assert json.loads((dev/'agent_all_business_review_v1.json').read_text())['allow_conditional_independent_nine']
    parent_root = base/'input_fidelity_development_faithful_v3'
    parent = json.loads((parent_root/'freeze.json').read_text(encoding='utf-8'))
    for item in parent['files']:
        assert sha(item['path']) == item['sha256'], item['path']
    config = parent['protocol']
    generation = json.loads(Path(config['generation_protocol']).read_text(encoding='utf-8'))
    assert generation['layout']['stable_word_limit'] == 0
    catalog = json.loads(Path(config['selected_catalog']).read_text(encoding='utf-8'))
    registry_path = base/'model_registry_v1.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    for model in registry['models']:
        location = args.tokenizer_root/model['key'] if args.tokenizer_root else Path(model['model_path'])
        for item in model['files']:
            path = location/item['file']
            if path.is_file() and not item['file'].endswith('.safetensors'):
                assert sha(path) == item['sha256'], str(path)
        assert (location/'tokenizer.json').is_file() and (location/'tokenizer_config.json').is_file()
    tokenizers = {row['model']: AutoTokenizer.from_pretrained(
        args.tokenizer_root/row['key'] if args.tokenizer_root else row['model_path'], local_files_only=True)
        for row in registry['models']}
    check = CapacityCheck(generation, catalog, tokenizers)
    rows = read(pool)
    args.output_dir.mkdir(parents=True)
    started = time.perf_counter()
    selected, original, ledgers, candidates_examined = [], [], [], []
    seed = 10672146
    for target_family in ('HotpotQA', 'RepoBench'):
        accepted = 0
        for row in ordered_candidates(rows, excluded, target_family, seed):
            identity = source(row)
            namespace = 'r4c-heldout-' + hashlib.sha256(identity.encode()).hexdigest()[:16]
            sample = {**row, 'revision_session_id': namespace, 'phase19b_session_id': namespace,
                      'revision_source_group': identity, 'revision_family': target_family}
            result = pack_task_input(sample, lambda candidate: check(candidate, False),
                                     validate=lambda candidate: check(candidate, True))
            metadata = {k: v for k, v in result.items() if k != 'sample'}
            metadata.update(namespace=namespace, source_group=identity, family=target_family,
                            original_segments_sha256=digest(sample['segments']))
            candidates_examined.append({'source_group': identity, 'family': target_family,
                                        'selection_hash': hashlib.sha256((str(seed)+':'+identity).encode()).hexdigest(),
                                        'critical_capacity_eligible': result['sample'] is not None,
                                        'status': result['status']})
            if result['sample'] is None:
                ledgers.append(metadata)
                continue
            packed = result['sample']
            packed['revision_input_fidelity'] = {'protocol': 'structure-preserving-window-v2',
                                                'status': result['status'],
                                                'original_segments_sha256': digest(sample['segments']),
                                                'packed_segments_sha256': digest(packed['segments'])}
            original.append(sample)
            selected.append(packed)
            ledgers.append(metadata)
            accepted += 1
            print(json.dumps({'independent_CPU_source_prepared': len(selected), 'source_group': identity,
                              'status': result['status']}), flush=True)
            if accepted == 3:
                break
        if accepted != 3:
            raise ValueError('Insufficient source-disjoint critical-capacity-eligible sources: '+target_family)
    assert len({source(row) for row in selected}) == 6
    assert not ({source(row) for row in selected} & excluded)
    files = []
    for name, values in [('original_selected_sessions_v1.jsonl', original),
                         ('faithful_selected_sessions_v1.jsonl', selected)]:
        path = args.output_dir/name
        path.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n' for row in values), encoding='utf-8')
        files.append({'path': path.as_posix(), 'rows': len(values), 'sha256': sha(path)})
    result = {'schema_version': 'tsc-r4.independent-fidelity-input-preparation.v1',
              'source_sha256': sha(__file__), 'source_pool_sha256': sha(pool),
              'exclusions_sha256': sha(exclusions_path), 'excluded_unique_sources': len(excluded),
              'primary_six_exclusion_record_sha256': sha(primary_record_path),
              'combined_excluded_set_sha256': hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),
              'selection_seed': seed, 'sources': 6, 'selected_source_groups': [source(r) for r in selected],
              'selected_sources_disjoint_from_all_573_prior': True,
              'candidates_examined_in_frozen_hash_order': candidates_examined,
              'source_ledgers': ledgers, 'data_files': files,
              'packer_sha256': sha('scripts/tsc_revision_r4_input_fidelity.py'),
              'renderer_sha256': sha('scripts/tsc_revision_r4_fidelity_adapter_v2.py'),
              'catalog_sha256': sha(config['selected_catalog']), 'generation_sha256': sha(config['generation_protocol']),
              'model_registry_sha256': sha(registry_path), 'total_preparation_CPU_wall_s': time.perf_counter()-started,
              'reference_labels_or_answer_positions_used_for_selection_or_packing': False,
              'model_outcomes_observed': False, 'new_GPU_requests': 0,
              'capacity_checked_raw_and_actual_selected_candidates': True,
              'all_selected_source_variants_per_model_tenant_turn': 300,
              'no_cost_calibration_or_scope_changes': True}
    (args.output_dir/'preparation_record_v1.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'independent_sources_prepared': 6, 'CPU_wall_s': result['total_preparation_CPU_wall_s']}))


if __name__ == '__main__':
    with installed_adapter():
        main()
