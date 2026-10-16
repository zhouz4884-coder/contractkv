"""Independent stored-byte, omission-ledger and metadata-only layout audit."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.tsc_revision_r4_fidelity_adapter import build_faithful_case, installed_adapter
from scripts.tsc_revision_r1r_live import prepare


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def textsha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    directory = Path('results/tsc_revision_r4/input_fidelity_development_inputs_v2')
    output = directory / 'independent_input_integrity_v1.json'
    if output.exists():
        raise ValueError('Preserve independent audit versions')
    record_path = directory / 'preparation_record_v2.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    freeze = json.loads(Path('results/tsc_revision_r4/validation_closed_v1/freeze.json').read_text(encoding='utf-8'))
    protocol = deepcopy(json.loads(Path(freeze['protocol']['generation_protocol']).read_text(encoding='utf-8')))
    protocol['layout']['stable_word_limit'] = 0
    original_path = Path(freeze['protocol']['input_files']['single-session'])
    originals = {r['revision_session_id']: r for r in read(original_path)}
    assert sha(original_path) == record['original_input_sha256']
    for item in record['data_files']:
        assert sha(Path(item['path'])) == item['sha256']
    faithful = read(directory / 'all_known_faithful_sessions_v2.jsonl')
    ledgers = {r['namespace']: r for r in record['source_ledgers']}
    counts = Counter()
    rows = []
    checks = 0
    for sample in faithful:
        before = originals[sample['revision_session_id']]
        ledger = ledgers[sample['revision_session_id']]
        metadata = deepcopy(sample)
        metadata.pop('revision_input_fidelity')
        metadata['segments'] = before['segments']
        assert metadata == before, 'Only segment text and declared fidelity metadata may differ'
        assert len(before['segments']) == len(sample['segments'])
        optional = {s['segment_index']: s for s in ledger['segment_ledger']}
        protected = []
        for index, (old, new) in enumerate(zip(before['segments'], sample['segments'])):
            old_meta, new_meta = dict(old), dict(new)
            old_meta.pop('text'); new_meta.pop('text')
            assert old_meta == new_meta
            if index not in optional:
                assert old['text'] == new['text']
                protected.append({'index': index, 'type': old['type'], 'text_sha256': textsha(new['text'])})
                continue
            entry = optional[index]
            text = old['text']
            assert textsha(text) == entry['original_text_sha256']
            ranges = entry['kept_original_character_ranges']
            omitted = entry['omitted_original_character_range']
            if omitted is None:
                rebuilt = text
            else:
                start, end = omitted
                marker = ('\n# CONTEXT_OMITTED_BY_WINDOW_BUDGET\n' if old['type'].startswith('REPO_')
                          else '\n\n[CONTEXT_OMITTED_BY_WINDOW_BUDGET]\n\n')
                rebuilt = text[:start] + marker + text[end:]
                assert all(0 <= a <= b <= len(text) for a, b in ranges)
                assert sum(b-a for a,b in ranges) == len(text[:start]) + len(text[end:])
            assert rebuilt == new['text']
            assert textsha(rebuilt) == entry['packed_text_sha256']
        final_fit = ledger['fit_calls'][-1]['result']
        assert final_fit['fits'] and final_fit['all_declared_variants_checked']
        assert final_fit['checked_request_variants'] == 300
        assert max(final_fit['max_prompt_plus_budget_by_model'].values()) <= 16384
        old_case = expand_stable_segments(build_case(sample, 0), 16)
        new_case = expand_stable_segments(build_faithful_case(sample, 0), 16)
        stripped = deepcopy(new_case)
        for old_seg, new_seg in zip(old_case['segments'], stripped['segments']):
            if old_seg['segment_type'] == 'CODE_PREFIX':
                assert new_seg['volatility'] == 0 and new_seg['cache_stability'] == 1
                new_seg['volatility'] = old_seg['volatility']
        assert old_case == stripped
        for level in ('L0', 'L1', 'L2', 'L3'):
            a = layout_for_level(old_case, level, protocol['layout']['ladder'])
            b = layout_for_level(new_case, level, protocol['layout']['ladder'])
            assert a == b and not a['violated_edges']
            assert _ordered_text(a['topological_order'], old_case['segments']) == _ordered_text(b['topological_order'], new_case['segments'])
            checks += 1
        # Exercise the actual serving/audit adapter path as well as direct builders.
        sample_args = SimpleNamespace(protocol=protocol, experiment='free-generation', output_budget=0,
                                      model_identity='Qwen3-8B', policy_hash='CPU-identity-proof')
        prior = [prepare(sample_args, sample, turn) for turn in range(3)]
        with installed_adapter():
            after = [prepare(sample_args, sample, turn) for turn in range(3)]
        for a, b in zip(prior, after):
            assert a[1:] == b[1:], 'Metadata-only correction changed rendered prompt/scope/budget'
        counts[(sample['revision_family'], ledger['status'])] += 1
        rows.append({'namespace': sample['revision_session_id'], 'family': sample['revision_family'],
                     'status': ledger['status'], 'protected_fields': protected,
                     'final_max_prompt_plus_budget_by_model': final_fit['max_prompt_plus_budget_by_model'],
                     'four_layouts_and_rendered_text_unchanged_by_type_fix': True,
                     'query_scope_and_budget_unchanged_by_type_fix': True})
    result = {'schema_version': 'tsc-r4.fidelity-independent-input-proof.v1',
              'analysis_source_sha256': sha(Path(__file__)),
              'preparation_record_sha256': sha(record_path),
              'adapter_source_sha256': sha(Path('scripts/tsc_revision_r4_fidelity_adapter.py')),
              'sources': len(rows), 'layout_checks': checks, 'new_GPU_requests': 0,
              'counts': [{'family': f, 'status': s, 'sources': n} for (f, s), n in counts.items()],
              'rows': rows, 'execution_complete': True,
              'boundary': 'Stored input bytes and CPU layout/scope identity only; no model quality or serving behavior claim.'}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('sources', 'layout_checks', 'execution_complete', 'counts')}))


if __name__ == '__main__':
    main()
