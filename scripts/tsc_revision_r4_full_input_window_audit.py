"""CPU-only head versus full input window audit on every frozen R4 source.

No weights, model forward, HTTP inference or test-source replacement. All
overflow cases remain in the audit. Tokenizer files match the serving registry.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['USE_TORCH'] = '0'
os.environ['USE_TF'] = '0'
os.environ['CUDA_VISIBLE_DEVICES'] = ''
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase22_llama_layout_ladder import layout_for_level
from transformers import AutoTokenizer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_sha(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results/tsc_revision_r4/validation_closed_v1'))
    parser.add_argument('--tokenizers', type=Path, default=Path('results/tsc_revision_r4/cpu_tokenizer_snapshots_v1'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve full-input window audit version')
    root = args.root
    freeze_path = root / 'freeze.json'
    study = json.loads(freeze_path.read_text(encoding='utf-8'))['protocol']
    generation_path = root / 'source_snapshot' / study['generation_protocol']
    original_protocol = json.loads(generation_path.read_text(encoding='utf-8'))
    registry_path = Path('results/tsc_revision_r4/model_registry_v1.json')
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    copied = json.loads((args.tokenizers / 'transport_identity_v1.json').read_text(encoding='utf-8'))
    if copied['model_registry_sha256'] != sha(registry_path):
        raise ValueError('Copied tokenizer registry binding differs')
    for item in copied['files']:
        if sha(Path(item['path'])) != item['sha256']:
            raise ValueError('Copied tokenizer bytes changed')
    catalog_path = root / 'source_snapshot' / study['selected_catalog']
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    samples = {name: read(root / 'source_snapshot' / path) for name, path in study['input_files'].items()}
    by_source = {s['revision_session_id']: s for s in samples['single-session']}
    controls = []
    records = []
    integrity = []
    native_provenance = []
    for model in registry['models']:
        key, identity = model['key'], model['model']
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizers / key, local_files_only=True)

        def tokenize(messages):
            return list(tokenizer.apply_chat_template(messages, tokenize=True,
                                                      add_generation_prompt=True, truncation=False))

        live_path = root / 'cells' / f'single-session_{key}_raw-order_r1/raw.jsonl'
        live_summary = json.loads(live_path.with_name('summary.json').read_text(encoding='utf-8'))
        if not live_summary['execution_complete'] or sha(live_path) != live_summary['raw_file_sha256']:
            raise ValueError('Known actual API control source changed')
        actual = [r for r in read(live_path) if r['row_type'] in ('warm', 'future') and r['turn_id'] in (0, 1, 2)]
        head_args = SimpleNamespace(protocol=original_protocol, experiment='free-generation',
                                    output_budget=0, model_identity=identity, policy_hash=sha(freeze_path))
        for row in actual:
            ids = tokenize(prepare(head_args, by_source[row['session_id']], row['turn_id'])[1])
            matches = ids == row['prompt_token_ids']
            controls.append({'model': identity, 'session_id': row['session_id'], 'turn_id': row['turn_id'],
                             'actual_API_prompt_IDs_match': matches, 'prompt_tokens': len(ids)})
            if not matches:
                raise ValueError('Local CPU tokenizer does not reproduce recorded serving prompt IDs')
        native_provenance.append({'path': live_path.as_posix(), 'sha256': sha(live_path)})
        for condition, cap in [('head', 1500), ('full', 0)]:
            protocol = deepcopy(original_protocol)
            protocol['layout']['stable_word_limit'] = cap
            cpu_args = SimpleNamespace(protocol=protocol, experiment='free-generation', output_budget=0,
                                       model_identity=identity, policy_hash=sha(freeze_path))
            for name, source_samples in samples.items():
                tenants = study['studies'][name]
                for source_sample in source_samples:
                    for tenant in range(tenants):
                        sample = deepcopy(source_sample)
                        if tenants > 1:
                            sample['shared_template_id'] = source_sample['revision_session_id']
                            sample['revision_session_id'] += f'-tenant{tenant:02d}'
                        for turn in range(10):
                            case, raw, _, budget, _ = prepare(cpu_args, sample, turn)
                            if condition == 'full' and tenant == 0 and turn == 0:
                                base = build_case(sample, 0)
                                checks = []
                                for segment in base['segments']:
                                    if segment['segment_type'] in ('SYS_PROMPT', 'USER_QUERY', 'TOOL_OBS'):
                                        continue
                                    joined = ''.join(r['text'] for r in case['segments']
                                                     if r['segment_id'].startswith(segment['segment_id'] + '__p'))
                                    checks.append(joined == segment['text'])
                                if not all(checks):
                                    raise ValueError('Character-preserving segmentation lost source text')
                                integrity.append({'model': identity, 'study': name,
                                                  'source_group': sample['revision_source_group'],
                                                  'all_stable_segment_characters_preserved': True})
                            level = catalog['models'][identity][name][sample['revision_family']]['level']
                            raw_ids = tokenize(raw)
                            if level == 'L0':
                                candidate_ids = raw_ids
                            else:
                                order = layout_for_level(case, level, protocol['layout']['ladder'])['topological_order']
                                candidate = [raw[0], {'role': 'user', 'content': _ordered_text(order, case['segments'])}]
                                candidate_ids = tokenize(candidate)
                            maximum = max(len(raw_ids), len(candidate_ids)) + budget
                            records.append({
                                'condition': condition, 'model': identity, 'study': name,
                                'source_group': sample['revision_source_group'], 'family': sample['revision_family'],
                                'session_id': sample['revision_session_id'], 'turn_id': turn,
                                'selected_level': level, 'output_budget': budget,
                                'raw_prompt_tokens': len(raw_ids), 'candidate_prompt_tokens': len(candidate_ids),
                                'max_prompt_plus_output_budget': maximum,
                                'fits_8192': maximum <= 8192, 'fits_actual_16384': maximum <= 16384,
                                'CPU_raw_IDs_sha256': ids_sha(raw_ids), 'CPU_candidate_IDs_sha256': ids_sha(candidate_ids),
                            })
        print(json.dumps({'CPU_model_complete': identity, 'actual_API_controls': len(actual),
                          'request_conditions_checked': sum(r['model'] == identity for r in records)}), flush=True)
    groups = defaultdict(list)
    for row in records:
        groups[row['condition'], row['model'], row['family'], row['source_group']].append(row)
    source_windows = []
    for key, group in sorted(groups.items()):
        source_windows.append(dict(zip(('condition', 'model', 'family', 'source_group'), key),
                                   declared_request_variants=len(group),
                                   all_variants_fit_8192=all(r['fits_8192'] for r in group),
                                   all_variants_fit_actual_16384=all(r['fits_actual_16384'] for r in group),
                                   max_prompt_plus_budget=max(r['max_prompt_plus_output_budget'] for r in group)))
    result = {
        'schema_version': 'tsc-r4.all-source-full-input-CPU-window.v1',
        'source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(freeze_path),
        'model_registry_sha256': sha(registry_path), 'generation_protocol_sha256': sha(generation_path),
        'local_runtime': {'python': sys.version, 'packages': {name: importlib.metadata.version(name)
                           for name in ['transformers', 'tokenizers', 'Jinja2', 'sentencepiece', 'numpy', 'huggingface-hub']}},
        'no_weights_loaded_or_model_forward': True, 'no_GPU_or_inference_HTTP_requests': True,
        'new_inputs_selected_or_replaced': False, 'reference_labels_used': False,
        'actual_serving_context_limit': 16384, 'auxiliary_historical_window': 8192,
        'known_actual_API_controls': controls, 'actual_API_control_provenance': native_provenance,
        'all_known_API_IDs_match': all(r['actual_API_prompt_IDs_match'] for r in controls),
        'stable_segment_integrity': integrity, 'source_window_records': source_windows, 'requests': records,
        'limits': [
            'All fifty frozen source inputs are retained, including overflow. This does not replace any R4 input or model result.',
            'Lengths include complete chat templates and the actual selected candidate layout plus the unchanged output budget. Segment token estimates are not added as a proxy.',
            'The local key tokenizer/template versions and file bytes match serving; other CPU environment details are recorded. Head-input IDs are independently matched to 450 recorded actual API requests.',
            'Full-input IDs and lengths are CPU predictions, not newly measured serving IDs or evidence of task quality, eligibility or speed. Final new-protocol preflight still binds its actual frozen inputs.',
            'Full character retention precedes unchanged CALC separators/segment labels; it is not an exact author benchmark rendering or a semantic answerability proof.',
        ],
    }
    if len(controls) != 450 or len(records) != 9000:
        raise ValueError('Incomplete declared full-input audit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'request_conditions': len(records), 'actual_API_ID_controls': len(controls),
                      'all_controls_match': True, 'full_source_model_units_fit_16K': sum(r['condition'] == 'full' and r['all_variants_fit_actual_16384'] for r in source_windows),
                      'full_source_model_units_total': sum(r['condition'] == 'full' for r in source_windows)}))


if __name__ == '__main__':
    main()
