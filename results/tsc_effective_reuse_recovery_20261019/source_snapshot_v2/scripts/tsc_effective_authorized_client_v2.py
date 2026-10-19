"""Full V5 fixed-wave runner with mandatory trusted authorization transport.

Only the declared execution/admission hooks and the existing final drain are
adapted. The historical V5 runner remains immutable and independently runnable.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r4_live_fixed as fixed
from scripts.tsc_revision_final_fixed_client_v2 import finish_after_backend_drain
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter, ordered_text_preserving_segments
from scripts import tsc_revision_r2_admission as admission
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register
from scripts.contractkv_verifier import VerificationIncomplete
from scripts.contractkv_v5_authorized_execution import AuthorizedExecution, authorized_register_method
from scripts.phase17_live_common import digest


def adapted_main(context):
    old = next(n for n in ast.parse(Path(fixed.__file__).read_text(encoding='utf-8')).body
               if isinstance(n, ast.FunctionDef) and n.name == 'main')
    new = deepcopy(old)
    replacements = dict(registrar='_context.registrar(catalog["raw_token_margin_floor"], catalog["candidate_token_margin_floor"])',
        prepared='_context.prepare(a, sample, turn)',
        compiled='a.policy != "raw-order" and _context.admit(a, sample, prepared, cert)',
        service_end='_finish_after_backend_drain(a)')
    for key, expression in replacements.items():
        found = [n for n in ast.walk(new) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == key for t in n.targets)]
        assert len(found) == 1, key
        found[0].value = ast.copy_location(ast.parse(expression, mode='eval').body, found[0].value)
    counts = {}
    for name, replacement in [('build_gate', '_context.build_gate'), ('business_generate', '_context.business')]:
        found = [n for n in ast.walk(new) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]
        assert len(found) == 1, name
        counts[name] = len(found)
        found[0].func = ast.copy_location(ast.parse(replacement, mode='eval').body, found[0].func)
    inserted = ast.parse('_context.bind_certificate(a, sample, prepared, cert)').body[0]
    target = [n for n in ast.walk(new) if isinstance(n, ast.Assign) and len(n.targets) == 1
              and ast.unparse(n.targets[0]) == 'certificates[key]']
    assert len(target) == 1
    def insert(nodes):
        for node in nodes:
            for _, value in ast.iter_fields(node):
                if isinstance(value, list):
                    if target[0] in value:
                        value.insert(value.index(target[0]) + 1, inserted)
                        return True
                    if insert([x for x in value if isinstance(x, ast.AST)]):
                        return True
        return False
    assert insert([new])
    a, b = deepcopy(old), deepcopy(new)
    def normalize(fn):
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in replacements for t in n.targets):
                n.value = ast.Constant(value='DECLARED_AUTHORIZATION_EXECUTION_HOOK')
            if isinstance(n, ast.Call):
                label = ast.unparse(n.func)
                if label in {'build_gate', '_context.build_gate'}:
                    n.func = ast.Name(id='SAME_GATE_HOOK', ctx=ast.Load())
                if label in {'business_generate', '_context.business'}:
                    n.func = ast.Name(id='SAME_BUSINESS_HOOK', ctx=ast.Load())
        for node in ast.walk(fn):
            for name, value in ast.iter_fields(node):
                if isinstance(value, list):
                    setattr(node, name, [x for x in value if not (
                        isinstance(x, ast.Expr) and isinstance(x.value, ast.Call) and
                        ast.unparse(x.value.func) == '_context.bind_certificate')])
        return fn
    assert ast.dump(normalize(a), include_attributes=False) == ast.dump(normalize(b), include_attributes=False)
    space = fixed.__dict__.copy()
    space.update(_context=context, _finish_after_backend_drain=finish_after_backend_drain)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[])),
                 str(fixed.__file__) + '[full-authorized-execution]', 'exec'), space)
    return space['main'], dict(original_fixed_source_sha256=hashlib.sha256(Path(fixed.__file__).read_bytes()).hexdigest(),
        changed_assignments=list(replacements), call_hooks=counts, added_existing_binding_call=1,
        scheduler_arrival_wave_loop_and_business_scoring_AST_unchanged=True,
        final_drain_reuses_existing_v2=True)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--authorization-trace', type=Path, required=True)
    parser.add_argument('--client-audit', type=Path, required=True)
    parser.add_argument('--cpu-prompt-shapes', type=Path, required=True)
    parser.add_argument('--admission-mode', choices=['existing', 'deferred'], required=True)
    parser.add_argument('--eligibility-overrides', type=Path)
    own, remaining = parser.parse_known_args()
    def arg(name):
        return remaining[remaining.index('--' + name) + 1]
    assert arg('policy') in {'raw-order', 'risk-tail'}
    proto = json.loads(Path(arg('protocol')).read_text(encoding='utf-8'))
    init = SimpleNamespace(policy_hash=arg('policy-hash'), model_identity=arg('model-identity'))
    samples = fixed.original.read_jsonl(Path(arg('sessions')))
    overrides = json.loads(own.eligibility_overrides.read_text(encoding='utf-8'))[init.model_identity] if own.eligibility_overrides else {}
    context = AuthorizedExecution(init, json.loads(own.identity.read_text(encoding='utf-8')), samples,
        int(arg('tenants-per-template')), own.authorization_trace,
        lazy=own.admission_mode == 'deferred', level_overrides=overrides)
    old_register, old_renderer = admission.SingleShotRegistrar.register, fixed._ordered_text
    record = dict(status='started', full_runner_AST_proof=None, admission_mode=own.admission_mode,
        mandatory_authorization_all_business_and_verification=True,
        per_request_signed_binding_checks=True, code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    assert not own.client_audit.exists()
    try:
        with installed_adapter():
            fixed._ordered_text = ordered_text_preserving_segments
            admission.SingleShotRegistrar.register = repaired_register(authorized_register_method(), VerificationIncomplete)
            run, proof = adapted_main(context)
            assert run.__globals__['_ordered_text'] is ordered_text_preserving_segments, 'Capture globals only after installing faithful renderer'
            record['full_runner_AST_proof'] = proof
            record['renderer_global_capture_checked_before_main'] = True
            sys.argv = [str(Path(fixed.__file__)), *remaining]
            code = run()
        shapes = {}
        for line in own.cpu_prompt_shapes.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            key = (row['model'], row['source_group'], row['tenant'], row['turn'], row['level'])
            assert key not in shapes
            shapes[key] = row
        count = 0
        output = Path(arg('output'))
        for line in output.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['row_type'] not in {'warm', 'future'}:
                continue
            tenant = int(row['tenant_id'].rsplit('-tenant', 1)[1]) if int(arg('tenants-per-template')) > 1 else 0
            shape = shapes[row['model'], row['source_group'], tenant, row['turn_id'], row['effective_level']]
            assert row['prompt_ids_sha256'] == shape['prompt_ids_sha256']
            assert len(row['prompt_token_ids']) == shape['prompt_tokens'] and row['output_budget'] == shape['output_budget']
            assert row['actual_authorized_cache_salt'].startswith('ckv-auth-v1:')
            count += 1
        assert count == len(samples) * int(arg('tenants-per-template')) * 10
        record.update(status='completed', returncode=code, actual_business_Prompt_IDs_checked=count,
                      raw_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        return code
    except BaseException as error:
        record.update(status='failure_preserved', error_type=type(error).__name__, error_message=str(error))
        raise
    finally:
        admission.SingleShotRegistrar.register = old_register
        fixed._ordered_text = old_renderer
        with own.client_audit.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')


if __name__ == '__main__':
    raise SystemExit(main())
