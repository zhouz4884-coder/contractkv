"""Prepare isolated, structure-preserving known-source development inputs.

This uses the already observed R4 sources. It is CPU input construction, never
independent validation or a model-quality/performance result.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
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
from scripts.tsc_revision_r4_input_fidelity import pack_task_input
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase22_llama_layout_ladder import layout_for_level
from transformers import AutoTokenizer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError('Preserve every attempted CPU input-preparation version')
    root = Path('results/tsc_revision_r4/validation_closed_v1')
    freeze_path = root / 'freeze.json'
    config = json.loads(freeze_path.read_text(encoding='utf-8'))['protocol']
    inputs = root / 'source_snapshot' / config['input_files']['single-session']
    original = read(inputs)
    catalog_path = root / 'source_snapshot' / config['selected_catalog']
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    generation_path = root / 'source_snapshot' / config['generation_protocol']
    generation = json.loads(generation_path.read_text(encoding='utf-8'))
    generation['layout']['stable_word_limit'] = 0
    registry_path = Path('results/tsc_revision_r4/model_registry_v1.json')
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    window_audit = Path('results/tsc_revision_r4/full_input_window_audit_v1.json')
    prior = json.loads(window_audit.read_text(encoding='utf-8'))
    if not prior['all_known_API_IDs_match'] or len(prior['known_actual_API_controls']) != 450:
        raise ValueError('Complete actual-ID matched CPU tokenizer audit first')
    if prior['model_registry_sha256'] != sha(registry_path):
        raise ValueError('Model registry changed')
    for package in ['transformers', 'tokenizers', 'Jinja2', 'sentencepiece', 'numpy', 'huggingface-hub']:
        if importlib.metadata.version(package) != prior['local_runtime']['packages'][package]:
            raise ValueError('Local tokenizer environment changed: ' + package)
    copied = Path('results/tsc_revision_r4/cpu_tokenizer_snapshots_v1')
    transport = json.loads((copied / 'transport_identity_v1.json').read_text(encoding='utf-8'))
    for item in transport['files']:
        if sha(Path(item['path'])) != item['sha256']:
            raise ValueError('Tokenizer snapshot changed')
    tokenizers = {m['model']: AutoTokenizer.from_pretrained(copied / m['key'], local_files_only=True)
                  for m in registry['models']}
    cpu_args = {model: SimpleNamespace(protocol=generation, experiment='free-generation', output_budget=0,
                                       model_identity=model, policy_hash='input-fidelity-CPU-only')
                for model in tokenizers}
    args.output_dir.mkdir(parents=True)
    progress_path = args.output_dir / 'CPU_progress_v2.jsonl'
    started = time.perf_counter()
    packed = []
    ledgers = []
    unsupported = []
    models = list(tokenizers)

    def count(candidate, exhaustive):
        maxima = {}
        checked = 0
        guard = 0 if exhaustive else 128
        tenants = range(10) if exhaustive else (9,)
        turns = range(10) if exhaustive else (0, 1, 2)
        for model in models:
            maximum = 0
            for tenant in tenants:
                sample = deepcopy(candidate)
                sample['shared_template_id'] = candidate['revision_session_id']
                sample['revision_session_id'] += f'-tenant{tenant:02d}'
                for turn in turns:
                    case, raw, _, budget, _ = prepare(cpu_args[model], sample, turn)
                    tokenizer = tokenizers[model]
                    raw_ids = tokenizer.apply_chat_template(raw, tokenize=True, add_generation_prompt=True, truncation=False)
                    level = catalog['models'][model]['template-fanout'][sample['revision_family']]['level']
                    if level != 'L0':
                        order = layout_for_level(case, level, generation['layout']['ladder'])['topological_order']
                        messages = [raw[0], {'role': 'user', 'content': _ordered_text(order, case['segments'])}]
                        candidate_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, truncation=False)
                    else:
                        candidate_ids = raw_ids
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

    for sample in original:
        result = pack_task_input(sample, lambda candidate: count(candidate, False),
                                 validate=lambda candidate: count(candidate, True))
        metadata = {k: v for k, v in result.items() if k != 'sample'}
        metadata.update(namespace=sample['revision_session_id'], source_group=sample['revision_source_group'],
                        family=sample['revision_family'], original_segments_sha256=digest(sample['segments']))
        if result['sample'] is None:
            unsupported.append(metadata)
        else:
            row = result['sample']
            row['revision_input_fidelity'] = {'protocol': 'structure-preserving-window-v2',
                                               'status': result['status'],
                                               'original_segments_sha256': digest(sample['segments']),
                                               'packed_segments_sha256': digest(row['segments'])}
            packed.append(row)
            ledgers.append(metadata)
        with progress_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'source_group': sample['revision_source_group'],
                                     'status': result['status'],
                                     'CPU_wall_s': result['input_preparation_CPU_wall_s']}) + '\n')
        print(json.dumps({'CPU_input_complete': len(packed) + len(unsupported), 'total': len(original),
                          'family': sample['revision_family'], 'status': result['status']}), flush=True)
    by_namespace = {r['revision_session_id']: r for r in packed}
    fan_path = root / 'source_snapshot' / config['input_files']['template-fanout']
    # The first two already frozen fan-out sources of each target family were
    # chosen before R4 outcomes. They now form an explicitly known-source DEV.
    old_dev = [r for r in read(fan_path) if r['revision_family'] in ('HotpotQA', 'RepoBench')]
    if len(old_dev) != 4 or any(r['revision_session_id'] not in by_namespace for r in old_dev):
        raise ValueError('One of four fixed known DEV task inputs cannot fit with critical fields protected')
    new_dev = [by_namespace[r['revision_session_id']] for r in old_dev]
    files = []
    for name, data in [('all_known_faithful_sessions_v2.jsonl', packed),
                       ('development_old_head_sessions_v2.jsonl', old_dev),
                       ('development_faithful_sessions_v2.jsonl', new_dev)]:
        path = args.output_dir / name
        path.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in data), encoding='utf-8')
        files.append({'path': path.as_posix(), 'rows': len(data), 'sha256': sha(path)})
    result = {
        'schema_version': 'tsc-r4.known-source-input-fidelity-preparation.v2',
        'timestamp_UTC': datetime.now(timezone.utc).isoformat(),
        'preparation_script_sha256': sha(Path(__file__)),
        'packing_module_sha256': sha(Path('scripts/tsc_revision_r4_input_fidelity.py')),
        'original_input_sha256': sha(inputs), 'tokenizer_window_audit_sha256': sha(window_audit),
        'catalog_sha256': sha(catalog_path), 'registry_sha256': sha(registry_path),
        'known_sources': len(original), 'packed_sources': len(packed),
        'unsupported_critical_inputs': unsupported, 'source_ledgers': ledgers,
        'data_files': files, 'new_GPU_or_inference_requests': 0,
        'reference_labels_or_answer_positions_used_for_packing': False,
        'new_independent_test_sources_selected': False,
        'total_preparation_CPU_wall_s': time.perf_counter() - started,
        'role': 'Input implementation development on previously observed sources, not model efficacy or independent validation.',
        'cost_boundary': 'This is immutable benchmark trace preparation shared by raw and ContractKV. Its local CPU time is separately recorded, not added to remote service wall or presented as GPU cost. All online ContractKV planning/qualification remains charged in serving.',
        'future_binding': 'Faithful cells must use stable_word_limit=0 so the historical renderer does not collapse the preserved text a second time. Original R4 cells remain untouched.',
    }
    (args.output_dir / 'preparation_record_v2.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_known_sources_prepared': len(packed), 'unsupported': len(unsupported),
                      'fixed_Qwen_DEV_sources': len(old_dev), 'CPU_wall_s': result['total_preparation_CPU_wall_s']}))


if __name__ == '__main__':
    main()
