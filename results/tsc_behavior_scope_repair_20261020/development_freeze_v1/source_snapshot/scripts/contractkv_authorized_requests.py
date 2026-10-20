"""Minimal authorized transport; preserve all existing behavioral admission.

Historical measurement clients are immutable. New serving integrations use this
adapter for every Raw, fallback, compiled and verification request.
"""
import ast
from copy import deepcopy
import hashlib
import inspect
from pathlib import Path

from scripts import tsc_revision_r2_admission as base
from scripts.tsc_revision_r2_business_stream import business_generate


def authorized_business_generate(authority, identity, args, messages, budget, request_id, witness=False):
    # Revalidate immediately before every dispatch; no implicit unsalted fallback.
    salt = authority.require(identity)
    return business_generate(args, messages, budget, request_id, witness=witness, salt=salt)


def adapted_register():
    tree = ast.parse(inspect.getsource(base))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SingleShotRegistrar')
    old = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'register')
    new = deepcopy(old)
    calls = [n for n in ast.walk(new) if isinstance(n, ast.Call) and
             isinstance(n.func, ast.Name) and n.func.id == 'verification_request']
    assert len(calls) == 1 and len(calls[0].args) == 7
    original_salt = deepcopy(calls[0].args[4])
    assert ast.dump(original_salt, include_attributes=False) == ast.dump(
        ast.parse("args.policy_hash+':'+namespace", mode='eval').body, include_attributes=False)
    calls[0].args[4] = ast.parse('self.authority.require(self.cache_identity)', mode='eval').body
    proof_old, proof_new = deepcopy(old), deepcopy(new)
    for fn in (proof_old, proof_new):
        call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call) and
                    isinstance(n.func, ast.Name) and n.func.id == 'verification_request')
        call.args[4] = ast.Constant(value='AUTHORIZED_CACHE_IDENTITY_ONLY')
    assert ast.dump(proof_old, include_attributes=False) == ast.dump(proof_new, include_attributes=False)
    space = base.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[])),
                 '<authorized-cache-salt-only>', 'exec'), space)
    proof = dict(changed_expression="args.policy_hash+':'+namespace -> authority.require(cache_identity)",
                 all_other_registration_AST_identical=True,
                 parent_source_sha256=hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest(),
                 scope_margin_EOS_output_budget_and_PSTP_unchanged=True)
    return space['register'], proof


_register, REGISTRAR_ADAPTER_PROOF = adapted_register()
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register
from scripts.contractkv_verifier import VerificationIncomplete
_register = repaired_register(_register, VerificationIncomplete)
REGISTRAR_ADAPTER_PROOF['existing_narrow_INCOMPLETE_fix_v5_reused'] = True


class AuthorizedRegistrar(base.SingleShotRegistrar):
    def __init__(self, raw_floor, candidate_floor, authority, cache_identity, poster=base.post_json):
        super().__init__(raw_floor, candidate_floor, poster=poster)
        authority.require(cache_identity)
        self.authority, self.cache_identity = authority, cache_identity

    def register(self, args, namespace, scope, business, gate, record=lambda row: None):
        self.authority.require(self.cache_identity)
        return _register(self, args, namespace, scope, business, gate, record)
