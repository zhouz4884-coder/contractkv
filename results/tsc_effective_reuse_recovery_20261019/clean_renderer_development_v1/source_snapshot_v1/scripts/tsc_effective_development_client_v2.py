"""Bounded full-runner smoke and legal candidate feasibility on development only."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter, ordered_text_preserving_segments
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_cache_identity import CacheAuthority
from scripts.contractkv_authorized_requests import AuthorizedRegistrar, authorized_business_generate
from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.phase17_live_common import digest, tokenize
from scripts.phase20a_official_quality import standard_score


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(x, f, ensure_ascii=False, indent=2)
        f.write('\n')


def run(args):
    out = args.output.parent
    assert not args.output.exists()
    args.output.touch()
    study = args.study_root
    source = args.source_root
    model_names = {'qwen3-8b': 'Qwen3-8B', 'mistral-7b': 'Mistral-7B-Instruct-v0.3',
                   'llama-3.1-8b': 'Llama-3.1-8B-Instruct'}
    identity = model_names[args.model]
    def record(row):
        with args.output.open('a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(dict(event_epoch_s=time.time(), monotonic_s=time.perf_counter(), model=identity, **row),
                               ensure_ascii=False, allow_nan=False) + '\n')
    record(dict(event='development_started', no_formal_validation_sources_read=True))
    common = ['--protocol', str(source / 'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json'),
        '--catalog', str(source / 'results/tsc_revision_r4/development_fit_v3/calibration_v1.json'),
        '--previous-catalog', str(source / 'configs/tsc_revision_r3_catalog_v1.json'), '--profile', 'balanced',
        '--sessions', str(study / 'development_smoke_inputs_v1.jsonl'), '--model', args.model,
        '--model-identity', identity, '--study', 'template-fanout', '--base-url', args.base_url,
        '--policy-hash', args.policy_hash, '--repeat', '1', '--tenants-per-template', '2',
        '--arrival-trace', str(study / 'development_smoke_arrivals_v1.json'),
        '--metrics-events', str(out / 'metrics.jsonl')]
    for arm, policy, mode in [('raw_authorized', 'raw-order', 'existing'),
                              ('V5_authorized', 'risk-tail', 'existing'),
                              ('deferred_authorized', 'risk-tail', 'deferred')]:
        cell = out / arm
        cell.mkdir()
        command = [sys.executable, '-B', str(source / 'scripts/tsc_effective_authorized_client_v2.py'),
            '--identity', str(args.identity), '--authorization-trace', str(cell / 'authorization_trace.jsonl'),
            '--client-audit', str(cell / 'client_audit_v1.json'),
            '--cpu-prompt-shapes', str(study / 'development_smoke_CPU_shapes_v1.jsonl'),
            '--admission-mode', mode, '--policy', policy, '--cell-id', args.cell_id + '-' + arm,
            '--output', str(cell / 'raw.jsonl'), '--summary', str(cell / 'summary.json'), *common]
        write(cell / 'launch_v1.json', dict(command=command, developmental_shared_engine=True,
                                           no_fair_fresh_server_speedup_claim=True))
        started = time.perf_counter()
        with (cell / 'client.log').open('xb') as log:
            done = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
        assert done.returncode == 0, 'Preserve failed smoke arm: ' + arm
        summary = read(cell / 'summary.json')
        audit = read(cell / 'client_audit_v1.json')
        assert summary['execution_complete'] and summary['arrival_requests'] == 60 and summary['futures'] == 54
        assert audit['status'] == 'completed' and audit['actual_business_Prompt_IDs_checked'] == 60
        record(dict(event='full_runner_arm_complete', arm=arm, summary=summary,
                    actual_arm_total_elapsed_s=time.perf_counter() - started))
    raw, v5, lazy = [
        [json.loads(x) for x in (out / arm / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
        for arm in ['raw_authorized', 'V5_authorized', 'deferred_authorized']]
    key = lambda r: (r['source_group'], r['session_id'], r['turn_id'])
    b = {key(r): r for r in raw if r['row_type'] in {'warm', 'future'}}
    for arm, data in [('V5_authorized', v5), ('deferred_authorized', lazy)]:
        changes = [dict(key=key(r), reference=b[key(r)]['output_token_ids'], actual=r['output_token_ids'])
                   for r in data if r['row_type'] in {'warm', 'future'} and r['effective_level'] != 'L0'
                   and (r['output_token_ids'], r['finish_reason']) != (b[key(r)]['output_token_ids'], b[key(r)]['finish_reason'])]
        record(dict(event='full_runner_compiled_behavior_check', arm=arm, changes=changes))
        assert not changes, 'Compiled behavioral change: preserve and diagnose before any formal service'
    samples = [json.loads(x) for x in (study / 'inputs_development_v1/faithful_selected_sessions_v1.jsonl').read_text(encoding='utf-8').splitlines()]
    generation = read(source / 'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json')
    a = SimpleNamespace(protocol=generation, experiment='free-generation', output_budget=0,
        model_identity=identity, model=args.model, policy_hash=args.policy_hash, cell_id=args.cell_id + '-feasibility',
        base_url=args.base_url, timeout=600)
    import secrets
    authority = CacheAuthority(secrets.token_bytes(32), digest(read(args.identity)), args.policy_hash,
                               {'development': 1}, {'controller': {'development'}})
    probes = 0
    with installed_adapter():
        for sample0 in samples:
            sample = deepcopy(sample0)
            sample['shared_template_id'] = sample['revision_session_id']
            sample['revision_session_id'] += '-tenant00'
            case, messages, maximum, budget, query = prepare(a, sample, 0)
            ns = sample0['revision_session_id']
            cache_identity = authority.bind('controller', 'development', 1, ns)
            raw = authorized_business_generate(authority, cache_identity, a, messages, budget, a.cell_id + '-' + ns + '-raw', witness=True)
            repeat = authorized_business_generate(authority, cache_identity, a, messages, budget, a.cell_id + '-' + ns + '-repeat')
            assert raw['success'] and repeat['success']
            scope = reference_scope_contract({'segments': case['segments']}, raw['output_text'], 16,
                                             raw.get('reference_margins'), .125)
            syntax = python_statement_contract(raw['output_text']) if sample0['revision_family'] == 'RepoBench' else None
            record(dict(event='development_Raw_witness', source_group=sample0['revision_source_group'],
                family=sample0['revision_family'], raw=raw, repeat=repeat, scope_check=scope, syntax_check=syntax,
                task_score=standard_score(sample0['dataset'], sample0['task'], raw['output_text'], sample0.get('answer', ''))[0]))
            for level in ('L1', 'L2', 'L3'):
                started = time.perf_counter()
                order = layout_for_level(case, level, generation['layout']['ladder'])['topological_order']
                candidate = [messages[0], dict(role='user', content=ordered_text_preserving_segments(order, case['segments']))]
                ids = tokenize(a.base_url, a.model, candidate, True, 600)
                stable = []
                byid = {s['segment_id']: s for s in case['segments']}
                for sid in order:
                    if byid[sid]['segment_type'] in {'TOOL_OBS', 'USER_QUERY', 'CHAT_HISTORY', 'SCRATCHPAD'}:
                        break
                    stable.append(sid)
                prefix = tokenize(a.base_url, a.model, [messages[0], dict(role='user', content=ordered_text_preserving_segments(stable, case['segments']))], False, 600)
                end = lcp_length(ids, prefix)
                plan = dict(level=level, messages=candidate, prompt_token_ids=ids, prompt_ids_sha256=digest(ids),
                    stable_prefix_end_token=end, stable_full_blocks=end // 16, stable_content_hash=digest(ids[:end]),
                    layout_hash=digest(order), dependency_graph_hash=digest([(s['segment_id'], s.get('dependencies', [])) for s in case['segments']]),
                    query_scope=digest([query, level]), output_budget=budget,
                    cpu_http_preparation_ms=(time.perf_counter() - started) * 1000)
                allowed = scope['shareable_query_scope'] and (syntax is None or syntax['passed'])
                reason = 'development_candidate_feasibility_without_economic_claim' if allowed else (
                    'observation_scope_has_no_declared_exact_reuse' if not scope['shareable_query_scope'] else 'raw_output_contract:' + syntax['reason'])
                reg = AuthorizedRegistrar(.0625, .125, authority, cache_identity)
                rows = []
                result = reg.register(a, ns + '-' + level, plan['query_scope'], raw,
                    dict(allow_verification=allowed, reason=reason, plan=plan), record=rows.append)
                # Counterfactual failed candidates use a separate authorized
                # cache identity; ordinary generation never fills cert state.
                generated_identity = cache_identity if result['certificate_issued'] else authority.bind(
                    'controller', 'development', 1, ns + ':private-counterfactual:' + level)
                observed = authorized_business_generate(authority, generated_identity, a, candidate, budget,
                    a.cell_id + '-' + ns + '-' + level + '-observed')
                same = observed['success'] and (raw['output_token_ids'], raw['finish_reason']) == (observed['output_token_ids'], observed['finish_reason'])
                record(dict(event='candidate_feasibility', source_group=sample0['revision_source_group'],
                    family=sample0['revision_family'], level=level, production_inherited_level_override_is_diagnostic_only=True,
                    economics_not_evaluated_in_this_probe=True, plan=plan, result=result, verification_rows=rows,
                    observed=observed, behavior_equal=same, reference=raw,
                    Raw_repeat_ID_and_finish_equal=(raw['output_token_ids'], raw['finish_reason']) == (repeat['output_token_ids'], repeat['finish_reason']),
                    usable_development_evidence=bool(result['certificate_issued'] and same and
                        (raw['output_token_ids'], raw['finish_reason']) == (repeat['output_token_ids'], repeat['finish_reason'])),
                    complete_probe_elapsed_ms=(time.perf_counter() - started) * 1000))
                assert not result['certificate_issued'] or same, 'Accepted candidate failed actual free generation; preserve for attribution'
                probes += 1
    assert probes == 12
    record(dict(event='effective_development_cell_complete', counts=dict(full_runner_business=180,
        candidate_probes=12, probe_business=20), no_formal_validation_outputs_read=True,
        no_causal_full_service_speedup_claim_from_shared_engine=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ['study-root', 'source-root', 'identity', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    for n in ['base-url', 'model', 'cell-id', 'policy-hash']:
        p.add_argument('--' + n, required=True)
    run(p.parse_args())
