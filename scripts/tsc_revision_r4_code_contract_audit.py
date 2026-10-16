"""CPU diagnostics of CODE_PREFIX metadata and standalone-statement admission.

Reference labels are post-output diagnostics only, not new admission inputs.
Parsing is not an oracle for next-line completion correctness.
"""
import ast
import codeop
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase12e_cache_aware_posc import _is_stable
from scripts.phase14c_full_pool_qc_inputs import CODE_TYPES
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level
from scripts.phase20a_official_quality import references
from scripts.tsc_revision_r3_output_contract import python_statement_contract


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_probe(text):
    try:
        tree = ast.parse(text)
        syntax = {'parsed': True, 'top_level_nodes': len(tree.body)}
    except (SyntaxError, ValueError) as error:
        syntax = {'parsed': False, 'error_type': type(error).__name__, 'message': str(error)[:240]}
    try:
        compiled = codeop.compile_command(text, symbol='exec')
        continuation = 'incomplete' if compiled is None else 'complete'
    except (SyntaxError, ValueError, OverflowError) as error:
        continuation = 'syntax_or_context_error:' + type(error).__name__
    return {'ast_syntax': syntax, 'compile_command_status': continuation}


def probes(prefix, completion):
    # Keep the complete served output. Removing an explicit filename line below
    # affects only a parser probe of prompt metadata, never serving or scoring.
    result = {'verbatim_prefix_plus_output': parse_probe(prefix + completion)}
    first, separator, rest = prefix.partition('\n')
    path_line = bool(separator and re.fullmatch(r'[A-Za-z0-9_./\\-]+\.py', first.strip()))
    result['first_prefix_line_is_path_metadata'] = path_line
    if path_line:
        result['path_metadata_excluded_probe'] = parse_probe(rest + completion)
    return result


def main():
    output = Path('results/tsc_revision_r4/code_prefix_contract_audit_v1.json')
    if output.exists():
        raise ValueError('Preserve code-contract audit version')
    root = Path('results/tsc_revision_r4/validation_closed_v1')
    freeze_path = root / 'freeze.json'
    config = json.loads(freeze_path.read_text(encoding='utf-8'))['protocol']
    input_path = root / 'source_snapshot' / config['input_files']['single-session']
    samples = [json.loads(line) for line in input_path.open(encoding='utf-8')]
    samples = {s['revision_session_id']: s for s in samples if s['revision_family'] == 'RepoBench'}
    generation = json.loads((root / 'source_snapshot' / config['generation_protocol']).read_text(encoding='utf-8'))
    records = []
    for namespace, sample in samples.items():
        full = build_case(sample, 0)
        capped = build_case(sample, generation['layout']['stable_word_limit'])
        prefix = next(r for r in full['segments'] if r['segment_type'] == 'CODE_PREFIX')
        old_prefix = next(r for r in capped['segments'] if r['segment_type'] == 'CODE_PREFIX')
        normalized = deepcopy(full)
        next(r for r in normalized['segments'] if r['segment_type'] == 'CODE_PREFIX')['volatility'] = 0.0
        before, after = expand_stable_segments(full, 16), expand_stable_segments(normalized, 16)
        levels = {}
        for level in ('L0', 'L1', 'L2', 'L3'):
            one = layout_for_level(before, level, generation['layout']['ladder'])
            two = layout_for_level(after, level, generation['layout']['ladder'])
            levels[level] = one == two
        if not all(levels.values()):
            raise ValueError('Metadata normalization changes the R4 layout recipe')
        gold = []
        for target in references(sample.get('answer', '')):
            gold.append({'reference_text': target, 'reference_lines': len(target.splitlines()),
                         'independent_statement_check': python_statement_contract(target),
                         'full_prefix_continuation_probes': probes(prefix['text'], target),
                         'old_capped_prefix_continuation_probes': probes(old_prefix['text'], target)})
        records.append({'namespace': namespace, 'source_group': sample['revision_source_group'],
                        'query': next(s['text'] for s in sample['segments'] if s['type'] == 'USER_QUERY'),
                        'CODE_PREFIX_original_words': len(prefix['text'].split()),
                        'CODE_PREFIX_capped_words': len(old_prefix['text'].split()),
                        'volatility': prefix['volatility'], 'cache_stability': prefix['cache_stability'],
                        'older_cache_aware_stability_predicate': _is_stable(prefix),
                        'R4_fixed_recipe_unchanged_if_volatility_set_zero': levels,
                        'reference_targets': gold})
    observed = []
    for cell in sorted((root / 'cells').glob('*_risk-tail_r1')):
        path = cell / 'raw.jsonl'
        summary = cell / 'summary.json'
        if not path.exists() or not summary.exists():
            continue
        if sha(path) != json.loads(summary.read_text(encoding='utf-8'))['raw_file_sha256']:
            raise ValueError('Changed observed cell')
        rows = [json.loads(line) for line in path.open(encoding='utf-8')]
        for row in rows:
            if row['row_type'] != 'output_contract_check':
                continue
            namespace, scope = row['certificate_namespace'], row['query_scope']
            sample = samples.get(namespace)
            if sample is None:
                continue
            witness = next(r for r in rows if r['row_type'] in ('warm', 'future')
                           and r['certificate_namespace'] == namespace and r['query_scope'] == scope
                           and r['scope_first_raw_business'])
            actual = python_statement_contract(witness['output_text'])
            if actual != row['check']:
                raise ValueError('Observed online syntax-check outcome not replayed')
            prefix = next(s['text'] for s in sample['segments'] if s['type'] == 'CODE_PREFIX')
            observed.append({'cell': cell.name, 'namespace': namespace, 'query_scope': scope,
                             'actual_online_check': row['check'], 'output_text_unchanged': witness['output_text'],
                             'frozen_task_score': witness['task_score'],
                             'full_original_prefix_plus_output_probes': probes(prefix, witness['output_text']),
                             'raw_file_sha256': sha(path)})
    sources = ['scripts/prepare_dataset_samples.py', 'scripts/phase13b_fresh_policy_quality_replay.py',
               'scripts/phase12e_cache_aware_posc.py', 'scripts/phase14c_full_pool_qc_inputs.py',
               'scripts/phase22_llama_layout_ladder.py', 'scripts/tsc_revision_r3_output_contract.py',
               'scripts/tsc_revision_r4_live.py', 'scripts/tsc_revision_r4_live_fixed.py']
    result = {
        'schema_version': 'tsc-r4.CODE_PREFIX-output-contract-audit.v1',
        'source_sha256': sha(Path(__file__)), 'input_sha256': sha(input_path),
        'new_GPU_requests': 0, 'frozen_input_policy_or_scoring_changed': False,
        'source_provenance': [{'path': s, 'sha256': sha(Path(s))} for s in sources],
        'CODE_PREFIX_in_QC_CODE_TYPES': 'CODE_PREFIX' in CODE_TYPES,
        'source_records': records, 'observed_first_repeat_contract_checks': observed,
        'reference_targets_failing_independent_statement_check': sum(not t['independent_statement_check']['passed'] for r in records for t in r['reference_targets']),
        'reference_target_count': sum(len(r['reference_targets']) for r in records),
        'interpretation': [
            'CODE_PREFIX has inconsistent low-level stability annotations. The older cache-aware predicate reads volatility, whereas the current R4 fixed layout recipe uses explicit volatile types and ignores these two numeric fields.',
            'All four R4 layout outputs were CPU-checked unchanged after setting only CODE_PREFIX volatility to zero. This is not a live speed measurement or proof that older compiler paths were unaffected.',
            'A next-line reference can be an incomplete standalone statement. Reference incompatibility identifies a possible task-contract mismatch, not an automatic count of observed false rejections.',
            'Prefix concatenation and compile_command are diagnostics only. Filename metadata, surrounding incomplete scopes and legitimate fragments can prevent parsing; success does not prove semantic correctness.',
            'Observed syntax failures remain distinct from reference-target failures. For example explanatory prose around code may correctly fail the existing standalone check even when some references are fragments.',
            'All outputs and frozen scores remain unchanged. No new gate is selected or deployed by this audit.',
        ],
    }
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'Repo_sources': len(records), 'reference_targets': result['reference_target_count'],
                      'reference_targets_failing_standalone_check': result['reference_targets_failing_independent_statement_check'],
                      'observed_checks_replayed': len(observed), 'R4_recipe_checks_identical': len(records) * 4,
                      'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
