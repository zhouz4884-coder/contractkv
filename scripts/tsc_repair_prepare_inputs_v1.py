"""Blind independent inputs for authorized-cache transport validation, CPU only."""
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
from scripts.contractkv_pstp import lcp_length

STUDY = Path('results/tsc_authorization_task_repair_20261019')


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, data):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')


def main(root):
    study = root / STUDY
    selection = read(study / 'selection_plan_v1.json')
    output = study / 'inputs_v1'; output.mkdir()
    known = root / 'results/tsc_final_existing_evidence_CPU_20261018/final_known_source_exclusions_v1.json'
    excluded = set(read(known)['excluded_source_groups'])
    previous = read(root / 'results/tsc_task_faithful_open_arrival_20261018/input_selection_complete_v1.json')
    for group in previous['sets']: excluded.update(group['sources'])
    assert len(excluded) == selection['excluded_source_count'] == 713
    pool = root / 'results/workload/phase14d_full_pool_v2.jsonl'
    assert sha(pool) == read(root / 'results/tsc_revision_r4/inputs/input_commitment_v1.json')['source_pool_sha256']
    generation = read(root / 'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json')
    catalog = read(root / 'results/tsc_revision_r4/development_fit_v3/calibration_v1.json')
    tokenizers = {m: AutoTokenizer.from_pretrained(str(DISK / 'models' / m), local_files_only=True) for m in MODELS}
    capacity = Capacity(generation, catalog, tokenizers, False)
    all_rows = [json.loads(line) for line in pool.read_text(encoding='utf-8').splitlines() if line.strip()]
    packed, originals, ledger, excluded_before = [], [], [], sorted(excluded)
    for family in ('HotpotQA', 'RepoBench'):
        count = 0
        for row in ordered_candidates(all_rows, excluded, family, selection['selection_seed']):
            group = source(row)
            ns = 'auth-repair-' + hashlib.sha256(group.encode()).hexdigest()[:16]
            sample = {**row, 'revision_session_id': ns, 'phase19b_session_id': ns,
                      'revision_source_group': group, 'revision_family': family}
            critical = 'CODE_PREFIX' if family == 'RepoBench' else 'USER_QUERY'
            if not any(s['type'] == critical and s['text'] for s in sample['segments']):
                ledger.append(dict(source=group, status='missing_critical_field')); continue
            result = pack_task_input(sample, lambda x: capacity(x, False), validate=lambda x: capacity(x, True))
            ledger.append(dict(source=group, selection_hash=hashlib.sha256((str(selection['selection_seed'])+':'+group).encode()).hexdigest(),
                               packing={k:v for k,v in result.items() if k != 'sample'}))
            if result['sample'] is None: continue
            chosen = result['sample']
            chosen['revision_input_fidelity'] = {'protocol': 'structure-preserving-window-v2', 'status': result['status']}
            originals.append(sample); packed.append(chosen); excluded.add(group); count += 1
            print(json.dumps(dict(source=group, family=family, packing=result['status'])), flush=True)
            if count == 3: break
        assert count == 3
    for name, data in [('original_selected_sessions_v1.jsonl', originals), ('faithful_selected_sessions_v1.jsonl', packed)]:
        with (output / name).open('x', encoding='utf-8', newline='\n') as f:
            for row in data: f.write(json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n')
    cases_by_model = {}
    parent = read(root / 'results/tsc_revision_mechanism_controls_20261018/protocol_v1.json')
    synthetic = deepcopy(next(c for c in parent['manifest_cases'] if c['trusted_semantic_mislabel'] and c['case_id'].endswith('ALPHA')))
    # A new, predeclared synthetic marker; no model output enters its choice.
    marker = 'SYNTHETIC_AUTH_REPAIR_20261019_CANARY_NOT_PERSONAL_DATA'
    old_marker = synthetic['synthetic_marker']
    for segment in synthetic['segments']: segment['text'] = segment['text'].replace(old_marker, marker)
    for key in ('raw_messages', 'candidate_messages'):
        for message in synthetic[key]: message['content'] = message['content'].replace(old_marker, marker)
    synthetic['synthetic_marker'] = marker
    for model, tok in tokenizers.items():
        args = SimpleNamespace(protocol=generation, experiment='free-generation', output_budget=0,
                               model_identity=model, policy_hash='CPU-authorized-transport-only')
        cases = []
        for row in packed:
            sample = deepcopy(row); sample['shared_template_id'] = sample['revision_session_id']
            sample['revision_session_id'] += '-tenant00'
            case, raw, _, budget, scope = prepare(args, sample, 0)
            level = catalog['models'][model]['template-fanout'][row['revision_family']]['level']
            candidate, stable = raw, []
            order = layout_for_level(case, level, generation['layout']['ladder'])['topological_order']
            if level != 'L0':
                candidate = [raw[0], dict(role='user', content=ordered_text_preserving_segments(order, case['segments']))]
                byid = {s['segment_id']:s for s in case['segments']}
                for sid in order:
                    if byid[sid]['segment_type'] in {'TOOL_OBS', 'USER_QUERY', 'CHAT_HISTORY', 'SCRATCHPAD'}: break
                    stable.append(sid)
            prefix = [raw[0], dict(role='user', content=ordered_text_preserving_segments(stable, case['segments']))]
            ids = tok.apply_chat_template(candidate, tokenize=True, add_generation_prompt=True)
            raw_ids = tok.apply_chat_template(raw, tokenize=True, add_generation_prompt=True)
            prefix_ids = tok.apply_chat_template(prefix, tokenize=True, add_generation_prompt=False)
            end = lcp_length(prefix_ids, ids)
            assert max(len(ids), len(raw_ids)) + budget <= 16384
            cases.append(dict(case_id=row['revision_session_id'], source_group=row['revision_source_group'],
                family=row['revision_family'], dataset=row['dataset'], task=row['task'], answer=row.get('answer', ''),
                raw_messages=raw, candidate_messages=candidate, budget=budget, level=level,
                raw_prompt_token_ids=raw_ids, candidate_prompt_token_ids=ids,
                stable_prefix_end_token=end, stable_content_hash=digest(ids[:end]),
                layout_hash=digest(order), dependency_graph_hash=digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
                query_scope=digest(dict(raw_messages=raw, candidate_prompt_ids=ids, output_budget=budget)),
                output_contract='one_python_statement' if row['revision_family']=='RepoBench' else None))
        syn = deepcopy(synthetic)
        ids = tok.apply_chat_template(syn['candidate_messages'], tokenize=True, add_generation_prompt=True)
        # Existing manifest test's declared stable prefix ends before USER_QUERY.
        from scripts.tsc_revision_mechanism_cases_v1 import messages
        stable = [sid for sid in syn['candidate_order'] if sid != 'QUERY']
        prefix = tok.apply_chat_template(messages(syn, stable), tokenize=True, add_generation_prompt=False)
        syn.update(candidate_prompt_token_ids=ids, raw_prompt_token_ids=tok.apply_chat_template(syn['raw_messages'], tokenize=True, add_generation_prompt=True),
                   stable_prefix_end_token=lcp_length(prefix, ids), level='L3', budget=syn['output_budget'])
        syn['stable_content_hash']=digest(ids[:syn['stable_prefix_end_token']]); syn['layout_hash']=digest(syn['candidate_order'])
        syn['dependency_graph_hash']=digest([(s['segment_id'],s['dependencies']) for s in syn['segments']])
        syn['query_scope']=digest(dict(raw_messages=syn['raw_messages'], candidate_prompt_ids=ids, output_budget=syn['budget']))
        syn['case_id']='synthetic_authorized_cache_identity'
        cases_by_model[model] = dict(real_cases=cases, synthetic_case=syn)
    write(output/'cases_by_model_v1.json', cases_by_model)
    write(output/'preparation_receipt_v1.json', dict(selection_plan_sha256=sha(study/'selection_plan_v1.json'),
        selector_sha256=sha(Path(__file__)), excluded_sources_before=excluded_before,
        selected_source_groups=[r['revision_source_group'] for r in packed], selected_sources=6,
        source_pool_sha256=sha(pool), ledger=ledger, answer_location_or_model_outputs_used_for_selection=False,
        source_disjoint_by_identity=True, semantic_disjointness_not_claimed=True, new_GPU_requests=0,
        files=[dict(path=p.relative_to(root).as_posix(), sha256=sha(p), bytes=p.stat().st_size) for p in sorted(output.iterdir()) if p.is_file()]))


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    with installed_adapter(): main(p.parse_args().root.resolve())
