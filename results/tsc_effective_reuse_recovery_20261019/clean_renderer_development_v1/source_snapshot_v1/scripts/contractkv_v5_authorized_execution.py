"""Trusted full-runner authorization and deferred deterministic admission work.

The benchmark identities are configured by the internal controller. This is not
public authentication, semantic privacy detection, or a timing-channel defense.
"""
import ast
from copy import deepcopy
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import secrets
from threading import Lock
import time

from scripts.contractkv_cache_identity import CacheAuthority
from scripts.contractkv_certificate_binding import CertificateBinding, RequestBinding, sign, validation_errors
from scripts import tsc_revision_r2_admission as admission
from scripts import tsc_revision_r4_cost_policy as cost
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_r1r_live import prepare as original_prepare
from scripts.phase17_live_common import digest
from scripts.phase22_llama_layout_ladder import layout_for_level


def authorized_register_method():
    tree = ast.parse(inspect.getsource(admission))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SingleShotRegistrar')
    old = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'register')
    new = deepcopy(old)
    def call(fn):
        found = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == 'verification_request']
        assert len(found) == 1
        return found[0]
    assert ast.unparse(call(new).args[4]) == "args.policy_hash + ':' + namespace"
    call(new).args[4] = ast.parse('self._context.salt(namespace)', mode='eval').body
    a, b = deepcopy(old), deepcopy(new)
    call(a).args[4] = ast.Constant(value='ONLY_AUTHORIZED_CACHE_SALT')
    call(b).args[4] = ast.Constant(value='ONLY_AUTHORIZED_CACHE_SALT')
    assert ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
    space = admission.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[])),
                 '<full-v5-authorized-cache-only>', 'exec'), space)
    return space['register']


class AuthorizedExecution:
    def __init__(self, args, identity, samples, tenants, trace, lazy=False, level_overrides=None):
        self.args, self.identity, self.trace, self.lazy = args, identity, trace, lazy
        self.level_overrides = level_overrides or {}
        self.domain, self.epoch = 'benchmark-authorized-service', 1
        self.principals = {}
        for sample in samples:
            ns = sample['revision_session_id']
            for tenant in range(tenants):
                sid = ns + f'-tenant{tenant:02d}' if tenants > 1 else ns
                self.principals[sid] = ns
        memberships = {sid: {self.domain} for sid in self.principals}
        memberships['_controller'] = {self.domain}
        self.authority = CacheAuthority(secrets.token_bytes(32), digest(identity), args.policy_hash,
                                        {self.domain: self.epoch}, memberships)
        self.binding_key = secrets.token_bytes(32)
        self.deferred = {}
        self.lock = Lock()
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.touch(exist_ok=False)

    def event(self, event, **values):
        with self.lock:
            with self.trace.open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(dict(event=event, epoch_s=time.time(),
                    monotonic_s=time.perf_counter(), **values), ensure_ascii=False, allow_nan=False) + '\n')

    def salt(self, namespace):
        identity = self.authority.bind('_controller', self.domain, self.epoch, namespace)
        return self.authority.require(identity)

    def prepare(self, args, sample, turn):
        case, raw, maximum, budget, scope = original_prepare(args, sample, turn)
        selected = self.level_overrides.get(sample['revision_family'])
        if selected and selected != 'L0' and int(selected[1:]) > int(maximum[1:]):
            # Only a separately declared development probe or frozen catalog
            # may enable a structurally legal candidate; behavioral gates stay.
            maximum = selected
        return case, raw, maximum, budget, scope

    def business(self, args, messages, budget, rid, witness=False, salt=None):
        stem = args.cell_id + '-'
        assert rid.startswith(stem)
        sid, turn = rid[len(stem):].rsplit('-t', 1)
        assert turn.isdigit() and sid in self.principals
        namespace = self.principals[sid]
        before = time.perf_counter()
        identity = self.authority.bind(sid, self.domain, self.epoch, namespace)
        actual = self.authority.require(identity)
        binding_ms = (time.perf_counter() - before) * 1000
        if salt is not None:
            assert salt == args.policy_hash + ':' + namespace, 'Unexpected legacy compiled salt input'
        self.event('business_dispatch', request_id=rid, principal=sid, namespace=namespace,
                   cache_salt=actual, witness=witness, identity_binding_ms=binding_ms,
                   started_monotonic_s=before)
        result = business_generate(args, messages, budget, rid, witness=witness, salt=actual)
        self.event('business_complete', request_id=rid, success=result['success'])
        result.update(actual_authorized_cache_salt=actual, authorization_domain=self.domain,
                      active_service_epoch=self.epoch, cache_identity_binding_ms=binding_ms)
        return result

    def generation_hash(self, args, prepared):
        return digest(dict(seed=args.protocol['runtime']['seed'], temperature=0, top_p=1,
                           budget=prepared[3], query_scope=prepared[4]))

    def common_binding(self, args, namespace, prepared, certificate):
        identity = self.identity
        order = layout_for_level(prepared[0], certificate['selected_level'],
                                 args.protocol['layout']['ladder'])['topological_order']
        return dict(model_id=args.model_identity, model_revision=identity['model_revision'],
            tokenizer_hash=identity['tokenizer'], chat_template_hash=identity['chat_template_hash'],
            serving_runtime='vllm', runtime_revision=identity['runtime_revision'],
            generation_config_hash=self.generation_hash(args, prepared),
            qualification_manifest_hash=args.policy_hash, policy_hash=args.policy_hash,
            tenant_id='*', authorization_domain=self.domain, service_template_id=namespace,
            service_template_epoch=self.epoch, stable_prefix_hash=certificate['stable_prefix_hash'],
            layout_hash=digest(order))

    def bind_certificate(self, args, sample, prepared, certificate):
        if not certificate.get('certificate_issued'):
            return
        started = time.perf_counter()
        ns = sample.get('shared_template_id', sample['revision_session_id'])
        binding = CertificateBinding(schema_version='contractkv.full-v5-binding.v1',
            certificate_id=certificate['certificate_hash'], expires_at_epoch=self.epoch,
            **self.common_binding(args, ns, prepared, certificate))
        certificate['signed_binding'] = asdict(binding)
        certificate['binding_signature'] = sign(binding, self.binding_key)
        self.event('certificate_bound', namespace=ns, query_scope=prepared[4],
                   elapsed_ms=(time.perf_counter() - started) * 1000)

    def admit(self, args, sample, prepared, certificate):
        if not certificate or not certificate.get('certificate_issued'):
            return False
        started = time.perf_counter()
        sid = sample['revision_session_id']
        ns = sample.get('shared_template_id', sid)
        identity = self.authority.bind(sid, self.domain, self.epoch, ns)
        self.authority.require(identity)
        errors = []
        if certificate.get('query_scope') != prepared[4]:
            errors.append('query_scope_mismatch')
        if not certificate.get('signed_binding'):
            errors.append('signed_binding_missing')
        else:
            request = RequestBinding(current_epoch=self.epoch, private_suffix_excluded=True,
                                     **self.common_binding(args, ns, prepared, certificate))
            errors.extend(validation_errors(CertificateBinding(**certificate['signed_binding']), request,
                                             certificate.get('binding_signature', ''), self.binding_key))
        self.event('compiled_binding_check', principal=sid, namespace=ns, query_scope=prepared[4],
                   errors=errors, admitted=not errors, elapsed_ms=(time.perf_counter() - started) * 1000)
        return not errors

    def build_gate(self, args, prepared, calibration, profile, namespace, turn, tenants, prefixes):
        if not self.lazy:
            return cost.build_gate(args, prepared, calibration, profile, namespace, turn, tenants, prefixes)
        begin = time.perf_counter()
        state = 'warm' if prefixes.get(namespace, {}) else 'cold'
        reuses = cost.declared_reuses(turn, tenants, args.protocol['runtime']['concurrency'])
        coarse = cost.decide(cost.stage_features(calibration, profile, state, args.study), reuses)
        gate = dict(plan=None, scope_case={'segments': prepared[0]['segments']},
            max_literal_answer_words=16, nonliteral_ambiguity_boundary=.125, output_contract=None,
            declared_remaining_reuse_hint=reuses, prefix_state_hint=state,
            coarse_gate=coarse, deferred_candidate_preparation=True,
            pre_business_gate_cpu_ms=(time.perf_counter() - begin) * 1000)
        gate.update(coarse)
        if coarse['allow_verification']:
            self.deferred[namespace, prepared[4]] = (args, prepared, calibration, profile, namespace, turn, tenants, prefixes)
        return gate

    def materialize(self, namespace, scope, gate):
        started = time.perf_counter()
        result = cost.build_gate(*self.deferred[namespace, scope])
        result['output_contract'] = gate['output_contract']
        result['pre_business_gate_cpu_ms'] += gate['pre_business_gate_cpu_ms']
        result['deferred_candidate_preparation'] = True
        self.event('deferred_candidate_materialized', namespace=namespace, query_scope=scope,
                   started_monotonic_s=started, elapsed_ms=(time.perf_counter() - started) * 1000,
                   allow_verification=result['allow_verification'])
        return result

    def registrar(self, raw_floor, candidate_floor):
        context = self
        class Registrar(cost.StagedRegistrar):
            def __init__(self):
                super().__init__(raw_floor, candidate_floor)
                self._context = context

            def register(self, args, namespace, scope, business, gate, record=lambda row: None):
                started = time.perf_counter()
                context.event('registration_start', namespace=namespace, query_scope=scope)
                precheck = None
                skipped = False
                if gate.get('allow_verification') and gate.get('deferred_candidate_preparation'):
                    precheck = cost.reference_scope_contract(gate['scope_case'], business['output_text'],
                        gate['max_literal_answer_words'], business.get('reference_margins'), gate['nonliteral_ambiguity_boundary'])
                    reason = None
                    if not precheck['shareable_query_scope']:
                        reason = 'observation_scope_has_no_declared_exact_reuse'
                    elif gate.get('output_contract') == 'one_python_statement':
                        syntax = python_statement_contract(business['output_text'])
                        if not syntax['passed']:
                            reason = 'raw_output_contract:' + syntax['reason']
                    if reason:
                        skipped = True
                        record(dict(row_type='reference_scope_contract', certificate_namespace=namespace,
                                    query_scope=scope, check=precheck))
                        gate = {**gate, 'allow_verification': False, 'reason': reason}
                        context.event('candidate_preparation_skipped', namespace=namespace, query_scope=scope, reason=reason)
                    else:
                        gate = context.materialize(namespace, scope, gate)
                result = super().register(args, namespace, scope, business, gate, record)
                if skipped:
                    result['reference_scope_contract'] = precheck
                result['actual_registration_interval_ms'] = (time.perf_counter() - started) * 1000
                result['candidate_preparation_skipped'] = skipped
                context.event('registration_complete', namespace=namespace, query_scope=scope,
                    started_monotonic_s=started, elapsed_ms=result['actual_registration_interval_ms'],
                    certificate_issued=bool(result.get('certificate_issued')), reason=result.get('failure_reason', ''),
                    RPCs=len(result.get('attempts', [])), candidate_preparation_skipped=skipped)
                return result
        return Registrar()
