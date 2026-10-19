"""Independently reconstruct actual business and candidate Prompt Token IDs.

Tokenizer-only analysis of completed immutable logs, never a model forward.
The new renderer must be checked against actual API IDs after generation;
matching the old renderer's controls cannot establish that new identity.
"""
import argparse
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                   'TOKENIZERS_PARALLELISM': 'false', 'USE_TORCH': '0', 'USE_TF': '0',
                   'CUDA_VISIBLE_DEVICES': ''}.items():
    os.environ[key] = value
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text as old_render
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter, ordered_text_preserving_segments


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_sha(ids):
    return hashlib.sha256(json.dumps(ids, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tokenizer-root', type=Path)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve actual-ID audit attempts')
    from transformers import AutoTokenizer
    freeze = json.loads((args.root/'freeze.json').read_text(encoding='utf-8'))
    config = freeze['protocol']
    protocol = json.loads((args.root/'source_snapshot'/config['generation_protocol']).read_text(encoding='utf-8'))
    registry_path = Path('results/tsc_revision_r4/model_registry_v1.json')
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    inputs = {study: {row['revision_session_id']: row for row in read(args.root/'source_snapshot'/name)}
              for study, name in config['input_files'].items()}
    tokenizers = {}
    identities = []
    for entry in registry['models']:
        location = args.tokenizer_root/entry['key'] if args.tokenizer_root else Path(entry['model_path'])
        checked = []
        for item in entry['files']:
            name = item['file']
            if name.endswith('.safetensors'):
                continue
            path = location/name
            if not path.exists():
                continue
            if sha(path) != item['sha256']:
                raise ValueError('Tokenizer/config identity mismatch: '+str(path))
            checked.append({'file': name, 'sha256': item['sha256']})
        tokenizer = AutoTokenizer.from_pretrained(location, local_files_only=True)
        tokenizers[entry['model']] = tokenizer
        identities.append({'model': entry['model'], 'checked_files': checked})
    faithful = config.get('input_adapter') == 'task-fidelity-contiguous-segment-text-v2'
    formatter = ordered_text_preserving_segments if faithful else old_render
    cache = {}
    cells = []
    failure = None

    def expected(sample, row, model, level):
        key = (row['study'], model, row['session_id'], row['turn_id'], level)
        if key in cache:
            return cache[key]
        data = deepcopy(sample)
        data['revision_session_id'] = row['session_id']
        if config['studies'][row['study']] > 1:
            data['shared_template_id'] = row['certificate_namespace']
        cpu_args = SimpleNamespace(protocol=protocol, experiment='free-generation', output_budget=0,
                                   model_identity=model, policy_hash=sha(args.root/'freeze.json'))
        case, messages, _, _, _ = prepare(cpu_args, data, row['turn_id'])
        if level != 'L0':
            order = layout_for_level(case, level, protocol['layout']['ladder'])['topological_order']
            messages = [messages[0], {'role': 'user', 'content': formatter(order, case['segments'])}]
        ids = list(tokenizers[model].apply_chat_template(messages, tokenize=True, add_generation_prompt=True, truncation=False))
        cache[key] = {'prompt_tokens': len(ids), 'expected_IDs_sha256': ids_sha(ids)}
        return cache[key]

    try:
        with installed_adapter() if faithful else nullcontext():
            for path in sorted((args.root/'cells').glob('*/summary.json')):
                summary = json.loads(path.read_text(encoding='utf-8'))
                raw_path = path.with_name('raw.jsonl')
                if not summary['execution_complete'] or sha(raw_path) != summary['raw_file_sha256']:
                    raise ValueError('Completed unchanged cell required')
                rows = read(raw_path)
                business = [r for r in rows if r['row_type'] in ('warm', 'future')]
                owners = {}
                for row in business:
                    owners.setdefault((row['certificate_namespace'], row['query_scope']), row)
                actual = []
                for row in business:
                    namespace = row['certificate_namespace'] if config['studies'][row['study']] > 1 else row['session_id']
                    sample = inputs[row['study']][namespace]
                    result = expected(sample, row, row['model'], row['effective_level'])
                    if ids_sha(row['prompt_token_ids']) != result['expected_IDs_sha256'] or len(row['prompt_token_ids']) != result['prompt_tokens']:
                        raise ValueError('Actual business prompt IDs differ: '+row['request_id'])
                    actual.append({'session_id': row['session_id'], 'turn_id': row['turn_id'],
                                   'effective_level': row['effective_level'], **result})
                candidate_checks = 0
                for row in rows:
                    if row['row_type'] != 'prospective_plan' or row.get('plan') is None:
                        continue
                    owner = owners[row['certificate_namespace'], row['query_scope']]
                    namespace = owner['certificate_namespace'] if config['studies'][owner['study']] > 1 else owner['session_id']
                    sample = inputs[owner['study']][namespace]
                    result = expected(sample, owner, owner['model'], row['plan']['level'])
                    if ids_sha(row['plan']['prompt_token_ids']) != result['expected_IDs_sha256']:
                        raise ValueError('Candidate plan IDs differ from declared input/layout')
                    candidate_checks += 1
                cells.append({'cell': path.parent.name, 'raw_sha256': sha(raw_path),
                              'actual_business_ID_matches': len(actual), 'candidate_plan_ID_matches': candidate_checks,
                              'reconstructed_business_prompt_hashes': actual})
                print(json.dumps({'actual_ID_audit_cell': path.parent.name, 'business_matches': len(actual),
                                  'candidate_matches': candidate_checks}), flush=True)
    except BaseException as error:
        failure = {'error_type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        result = {'schema_version': 'tsc-r4.independent-actual-prompt-ID-audit.v1',
                  'analysis_source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(args.root/'freeze.json'),
                  'model_registry_sha256': sha(registry_path), 'tokenizer_identities': identities,
                  'faithful_renderer_v2': faithful, 'cells': cells, 'complete_cells': len(cells),
                  'expected_cells': config['expected_cells'], 'allow_partial': args.allow_partial,
                  'all_observed_actual_prompt_IDs_match': failure is None,
                  'execution_complete': failure is None and len(cells) == config['expected_cells'],
                  'new_GPU_requests': 0, 'no_weights_loaded_no_model_forward': True, 'failure': failure}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    if not result['execution_complete'] and not args.allow_partial:
        raise ValueError('Full declared matrix required')


if __name__ == '__main__':
    main()
