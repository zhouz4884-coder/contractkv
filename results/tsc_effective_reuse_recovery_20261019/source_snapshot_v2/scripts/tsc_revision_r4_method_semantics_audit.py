"""Static protocol/implementation audit for revision scope; no model requests."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function(path, name):
    text = path.read_text(encoding='utf-8')
    matches = [node for node in ast.walk(ast.parse(text))
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise ValueError('Ambiguous/missing implementation function: ' + str(path) + ':' + name)
    node = matches[0]
    return node, {'path': path.as_posix(), 'sha256': sha(path), 'function': name,
                  'first_line': node.lineno, 'last_line': node.end_lineno,
                  'function_AST_sha256': hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()}


def pass_body(node):
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.If) or not candidate.body:
            continue
        first = candidate.body[0]
        if (isinstance(first, ast.Assign) and isinstance(first.value, ast.Constant)
                and first.value.value == 'PASS'
                and any(isinstance(target, ast.Name) and target.id == 'decision' for target in first.targets)):
            return ast.dump(ast.Module(body=candidate.body, type_ignores=[]), include_attributes=False)
    raise ValueError('Missing verified-pass publication branch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve method semantics audit version')
    entries = []
    old, entry = function(Path('scripts/tsc_service_template_quality_live.py'), 'verify_template')
    entries.append(entry)
    calls = [n for n in ast.walk(old) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'generate_raw']
    assert len(calls) == 1 and isinstance(calls[0].args[3], ast.Name) and calls[0].args[3].id == 'candidate_messages'
    scope, entry = function(Path('scripts/tsc_service_template_quality_live.py'), 'scope_record')
    entries.append(entry)
    scope_returns = [n.value for n in ast.walk(scope) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert len(scope_returns) == 1
    scope_keys = [n.value for n in scope_returns[0].keys if isinstance(n, ast.Constant)]
    query, entry = function(Path('scripts/tsc_revision_r1r_query_scope.py'), 'query_scope')
    entries.append(entry)
    query_calls = [n for n in ast.walk(query) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Name) and n.func.id == 'digest']
    query_keys = [n.value for n in query_calls[0].args[0].keys if isinstance(n, ast.Constant)]
    for path, name in [
        ('scripts/tsc_revision_r1r_live.py', 'register'),
        ('scripts/tsc_revision_r2_admission.py', 'register'),
        ('scripts/tsc_revision_r3_output_contract.py', 'register'),
        ('scripts/tsc_revision_r4_cost_policy.py', 'register'),
        ('scripts/tsc_revision_r2_candidate_plan.py', 'verification_request'),
        ('scripts/tsc_revision_r4_live.py', 'main'),
        ('scripts/tsc_revision_r4_live_fixed.py', 'main'),
        ('scripts/tsc_real_task_open_loop.py', 'check_binding'),
    ]:
        _, entry = function(Path(path), name)
        entries.append(entry)
    snapshot = Path('results/tsc_revision_r4/validation_closed_v1/source_snapshot/third_party')
    old_backend = snapshot / 'vllm-contractkv-tsc-r1r-slice/vllm/v1/core/sched/scheduler.py'
    new_backend = snapshot / 'vllm-contractkv-tsc-r2-margin/vllm/v1/core/sched/scheduler.py'
    left, entry = function(old_backend, '_finalize_contractkv_verify')
    entries.append(entry)
    right, entry = function(new_backend, '_finalize_contractkv_verify')
    entries.append(entry)
    publication_body_unchanged = pass_body(left) == pass_body(right)
    if not publication_body_unchanged:
        raise ValueError('Inspect actual publication-body changes before claiming it unchanged')
    floors = {}
    for version, name in [('R2', 'configs/tsc_revision_r2_selected_catalog_v2.json'),
                          ('R3', 'configs/tsc_revision_r3_catalog_v1.json')]:
        path = Path(name)
        catalog = json.loads(path.read_text())
        floors[version] = {'path': name, 'sha256': sha(path),
                           'raw_floor': catalog['raw_token_margin_floor'],
                           'candidate_floor': catalog['candidate_token_margin_floor'],
                           'online_verification_attempt_limit': catalog['online_verification_attempt_limit']}
    result = {
        'schema_version': 'tsc-r4.method-semantics-audit.v1',
        'analysis_added_after_primary_freeze': True,
        'source_sha256': sha(Path(__file__)), 'new_GPU_requests': 0,
        'submitted_tex': {'path': 'submission/contractkv_tsc.tex', 'sha256': sha(Path('submission/contractkv_tsc.tex')),
                          'modified_by_this_audit': False},
        'source_functions': entries,
        'observed_static_facts': {
            'original_template_task_runner_reference_prompt': 'compiled candidate_messages',
            'original_template_scope_record_keys': scope_keys,
            'query_bound_scope_hash_keys': query_keys,
            'metadata_only_values_bound_by_query_hash': False,
            'R1R_slice_to_R2_margin_verified_PASS_publication_body_AST_equal': publication_body_unchanged,
            'formal_positive_floor_versions': floors,
        },
        'interpretation': [
            'Original deployment-template attestation follows prior route qualification and compiled-path self-consistency. It does not directly attest raw equivalence of every future private query.',
            'R1R changes witness provenance to the actual first raw business answer and changes behavioral reuse keys to (template namespace, query scope). It is a controlled mode change, not merely a renamed original template check.',
            'R2 adds one-shot admission, pointwise margins/EOS evidence and complete prompt IDs/cost gates; R3 tightens floors and Python-output eligibility. These are bounded admission repairs, not new CALC or PSTP algorithms.',
            'R4 adds restrictive empirical scope eligibility and engineering cost/tail admission. Do not introduce these as new headline contributions or continue optimizing every performance cell.',
            'The verified-PASS publication branch is structurally equal between the frozen R1R-slice and R2-margin backends. This static check does not prove every original/backend code byte unchanged or replace live publication tests.',
            'Template namespaces still permit cross-tenant physical prefix sharing. Distinct behavioral scope count U changes full qualification work; fixed-U tenant amortization is supported separately from arbitrary unique-query streams.',
            'Old scope failures remain failures within the old declared empirical range. A later contraction cannot retroactively relabel them outside the original scope.',
            'R4 clients and original signed real-task binding controls must be described with their actual enforcement boundaries; do not claim two independent certificate objects or a new adversarial public-endpoint defense.',
        ],
        'revision_scope': {'retain_contributions': ['CALC', 'Scoped Behavioral Certification', 'PSTP', 'Service-Template Certificate'],
                           'no_new_certificate_system': True, 'no_new_performance_optimization_matrix': True,
                           'finish_running_frozen_independent_validation': True,
                           'continue_only_for_core_in_scope_reproducible_failure_or_invariant_violation': True},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'source_functions_checked': len(entries), 'reference_mode_change_confirmed': True,
                      'verified_PASS_publication_body_AST_equal': publication_body_unchanged, 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
