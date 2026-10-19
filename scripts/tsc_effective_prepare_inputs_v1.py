"""Blind development/held-out task inputs and exact CPU prompt commitments."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_prepare_sources_v1 import (
    Capacity, MODELS, DISK, AutoTokenizer, source, ordered_candidates, pack_task_input,
    installed_adapter, prepare, layout_for_level, ordered_text_preserving_segments)
from scripts.phase17_live_common import digest

STUDY = Path('results/tsc_effective_reuse_recovery_20261019')


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(x, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main(root):
    study = root / STUDY
    plan = read(study / 'selection_plan_v1.json')
    excluded = set(read(root / 'results/tsc_final_existing_evidence_CPU_20261018/final_known_source_exclusions_v1.json')['excluded_source_groups'])
    for group in read(root / 'results/tsc_task_faithful_open_arrival_20261018/input_selection_complete_v1.json')['sets']:
        excluded.update(group['sources'])
    excluded.update(read(root / 'results/tsc_authorization_task_repair_20261019/inputs_v1/preparation_receipt_v1.json')['selected_source_groups'])
    assert len(excluded) == 719 == plan['excluded_sources_before']
    pool = root / 'results/workload/phase14d_full_pool_v2.jsonl'
    assert sha(pool) == read(root / 'results/tsc_revision_r4/inputs/input_commitment_v1.json')['source_pool_sha256']
    generation = read(root / 'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json')
    catalog = read(root / 'results/tsc_revision_r4/development_fit_v3/calibration_v1.json')
    registry = read(root / 'results/tsc_revision_mechanism_controls_20261018/preflight_v3/model_asset_registry_v1.json')
    for entry in registry['models']:
        if entry['model'] in MODELS:
            for a in entry['files']:
                if a['file'].startswith(('tokenizer', 'special_tokens', 'vocab', 'merges')):
                    assert sha(DISK / 'models' / entry['model'] / a['file']) == a['sha256']
    tokenizers = {m: AutoTokenizer.from_pretrained(str(DISK / 'models' / m), local_files_only=True) for m in MODELS}
    capacity = Capacity(generation, catalog, tokenizers, True)
    all_rows = [json.loads(x) for x in pool.read_text(encoding='utf-8').splitlines() if x.strip()]
    sets = []
    for name, per_family, seed in [('development', 2, 2026101902), ('validation', 3, 2026101903)]:
        output = study / ('inputs_' + name + '_v1')
        output.mkdir()
        original, packed, ledger, shapes = [], [], [], []
        before = sorted(excluded)
        for family in ('HotpotQA', 'RepoBench'):
            count = 0
            for row in ordered_candidates(all_rows, excluded, family, seed):
                group = source(row)
                ns = 'reuse-' + hashlib.sha256(group.encode()).hexdigest()[:16]
                sample = {**row, 'revision_session_id': ns, 'phase19b_session_id': ns,
                          'revision_source_group': group, 'revision_family': family}
                critical = 'CODE_PREFIX' if family == 'RepoBench' else 'USER_QUERY'
                if not any(s['type'] == critical and s['text'] for s in sample['segments']):
                    ledger.append(dict(source=group, status='missing_critical_field'))
                    continue
                result = pack_task_input(sample, lambda x: capacity(x, False), validate=lambda x: capacity(x, True))
                ledger.append(dict(source=group, packing={k: v for k, v in result.items() if k != 'sample'}))
                if result['sample'] is None:
                    continue
                chosen = result['sample']
                chosen['revision_input_fidelity'] = dict(protocol='structure-preserving-window-v2', status=result['status'])
                original.append(sample)
                packed.append(chosen)
                excluded.add(group)
                count += 1
                print(json.dumps(dict(set=name, source=group, status=result['status'])), flush=True)
                if count == per_family:
                    break
            assert count == per_family
        for filename, data in [('original_selected_sessions_v1.jsonl', original), ('faithful_selected_sessions_v1.jsonl', packed)]:
            with (output / filename).open('x', encoding='utf-8', newline='\n') as f:
                for row in data:
                    f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n')
        for model, tok in tokenizers.items():
            args = SimpleNamespace(protocol=generation, experiment='free-generation', output_budget=0,
                                   model_identity=model, policy_hash='CPU-only-effective-reuse-capacity')
            for row in packed:
                for tenant in range(2):
                    sample = deepcopy(row)
                    sample['shared_template_id'] = sample['revision_session_id']
                    sample['revision_session_id'] += f'-tenant{tenant:02d}'
                    for turn in range(10):
                        case, raw, _, budget, _ = prepare(args, sample, turn)
                        for level in ('L0', 'L1', 'L2', 'L3'):
                            order = layout_for_level(case, level, generation['layout']['ladder'])['topological_order']
                            messages = raw if level == 'L0' else [raw[0], dict(role='user', content=ordered_text_preserving_segments(order, case['segments']))]
                            ids = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
                            assert len(ids) + budget <= 16384
                            shapes.append(dict(model=model, source_group=row['revision_source_group'], tenant=tenant,
                                turn=turn, level=level, prompt_tokens=len(ids), output_budget=budget, prompt_ids_sha256=digest(ids)))
        with (output / 'CPU_prompt_shapes_v1.jsonl').open('x', encoding='utf-8', newline='\n') as f:
            for row in shapes:
                f.write(json.dumps(row, sort_keys=True) + '\n')
        write(output / 'preparation_receipt_v1.json', dict(selection_seed=seed, source_pool_sha256=sha(pool),
            excluded_source_groups_before=before, selected_source_groups=[r['revision_source_group'] for r in packed],
            packing_ledger=ledger, model_outcomes_or_gold_positions_used=False, CPU_only=True,
            all_four_levels_checked_for_two_tenants_ten_turns=True, checked_shapes=len(shapes),
            source_sha256=sha(Path(__file__)), files=[dict(path=p.relative_to(root).as_posix(), sha256=sha(p))
                for p in sorted(output.iterdir()) if p.is_file()]))
        sets.append(dict(set=name, sources=[r['revision_source_group'] for r in packed]))
    write(study / 'input_selection_complete_v1.json', dict(status='COMPLETE_CPU_ONLY', sets=sets,
        new_GPU_requests=0, final_excluded_unique_sources=len(excluded), source_identity_disjoint=True,
        semantic_disjointness_not_claimed=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    with installed_adapter():
        main(parser.parse_args().root.resolve())
