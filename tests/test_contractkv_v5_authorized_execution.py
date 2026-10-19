"""Meaningful authorization/admission regressions; no model efficacy claim."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from scripts import contractkv_v5_authorized_execution as execution
from scripts import tsc_revision_r2_admission as admission
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register
from scripts.contractkv_verifier import VerificationIncomplete
from scripts.contractkv_cache_identity import CacheAuthorizationError
from scripts.tsc_effective_authorized_client_v1 import adapted_main
from tests.test_tsc_revision_r2_admission import fixture


def context(tmp_path, lazy=True):
    args, witness, gate = fixture()
    args.protocol = {'runtime': {'seed': 14014, 'concurrency': 2}, 'layout': {'ladder': {}}}
    args.model_identity = 'Qwen3-8B'
    args.study = 'template-fanout'
    witness['output_text'] = 'ACK'
    identity = dict(model_revision='weights', tokenizer='tokenizer', chat_template_hash='chat', runtime_revision='runtime')
    ctx = execution.AuthorizedExecution(args, identity, [{'revision_session_id': 'n'}], 2,
                                        tmp_path / 'authorization.jsonl', lazy=lazy)
    return ctx, args, witness, gate


def guard_gate(gate, lazy=True):
    result = dict(gate, scope_case={'segments': [{'segment_id': 'document', 'segment_type': 'RAG_CHUNK', 'text': 'ACK'}]},
        max_literal_answer_words=16, nonliteral_ambiguity_boundary=.125, output_contract=None,
        declared_remaining_reuse_hint=5, deferred_candidate_preparation=lazy, pre_business_gate_cpu_ms=0.,
        fine_cost_features=dict(p_joint_lower=1., p_eligible_upper=1., p_pass_given_eligible_lower=1.,
            save_per_reuse_ms=1000., gpu_registration_cost_ms=1., information_cost_ms=0., minimum_net_ms=0.,
            baseline_ttft_p95_ms=1., tail_budget_ms=100., tail_budget_enforced=False))
    if lazy:
        result['plan'] = None
    return result


def install(monkeypatch):
    monkeypatch.setattr(admission.SingleShotRegistrar, 'register',
                        repaired_register(execution.authorized_register_method(), VerificationIncomplete))


def test_full_runner_scheduler_and_other_AST_are_preserved():
    _, proof = adapted_main(None)
    assert proof['scheduler_arrival_wave_loop_and_business_scoring_AST_unchanged']
    assert proof['call_hooks'] == {'build_gate': 1, 'business_generate': 1}


def test_raw_l0_and_compiled_dispatch_always_have_same_authorized_identity(tmp_path, monkeypatch):
    ctx, args, _, _ = context(tmp_path)
    seen = []
    def generate(*values, **kw):
        seen.append(kw['salt'])
        return dict(success=True)
    monkeypatch.setattr(execution, 'business_generate', generate)
    ctx.business(args, [], 64, 'test-n-tenant00-t0')
    ctx.business(args, [], 64, 'test-n-tenant01-t1', salt='p:n')
    assert len(seen) == 2 and len(set(seen)) == 1 and seen[0].startswith('ckv-auth-v1:')
    ctx.authority.advance_epoch(ctx.domain, 2)
    with pytest.raises(CacheAuthorizationError):
        ctx.business(args, [], 64, 'test-n-tenant00-t2')
    assert len(seen) == 2


def test_wrong_controller_routing_cannot_choose_an_arbitrary_legacy_salt(tmp_path, monkeypatch):
    ctx, args, _, _ = context(tmp_path)
    monkeypatch.setattr(execution, 'business_generate', lambda *v, **k: pytest.fail('must not dispatch'))
    with pytest.raises(AssertionError):
        ctx.business(args, [], 64, 'test-n-tenant00-t0', salt='p:foreign-template')


@pytest.mark.parametrize('text,contract,reason', [
    ('Not enough information is provided.', None, 'observation_scope_has_no_declared_exact_reuse'),
    ('if broken:', 'one_python_statement', 'raw_output_contract:python_syntax_IndentationError')])
def test_same_deterministic_reject_avoids_all_candidate_preparation(tmp_path, monkeypatch, text, contract, reason):
    ctx, args, witness, base = context(tmp_path)
    witness['output_text'] = text
    gate = guard_gate(base)
    gate['scope_case']['segments'][0]['text'] = text
    gate['output_contract'] = contract
    install(monkeypatch)
    monkeypatch.setattr(ctx, 'materialize', lambda *v: pytest.fail('a rejected reference must not prepare candidate'))
    reg = ctx.registrar(.0625, .125)
    reg.poster = lambda *v: pytest.fail('a rejected reference must not call GPU')
    result = reg.register(args, 'n', 'scope', witness, gate)
    assert not result['certificate_issued'] and result['attempts'] == []
    assert result['failure_reason'] == reason and result['candidate_preparation_skipped']


@pytest.mark.parametrize('raw_eos,server_margin,expected', [(2., .5, 'PASS'), (0., .5, 'RAW_REJECT'), (2., .001, 'FATAL')])
def test_positive_and_EOS_paths_keep_original_strict_admission(tmp_path, monkeypatch, raw_eos, server_margin, expected):
    ctx, args, witness, base = context(tmp_path)
    gate, fine = guard_gate(base), guard_gate(base, False)
    witness['reference_margins'][-1] = raw_eos
    calls, planned = [], []
    def materialize(*values):
        planned.append(True)
        return fine
    monkeypatch.setattr(ctx, 'materialize', materialize)
    install(monkeypatch)
    reg = ctx.registrar(.0625, .125)
    def post(url, payload, timeout):
        assert payload['cache_salt'] == ctx.salt('n')
        assert payload['reference_raw_margins'] == [witness['reference_margins'][0]]
        calls.append(payload)
        return dict(certificate_issued=True, committed_tokens=16, minimum_margin_guard_passed=True,
            raw_margin_min=1., candidate_margin_min=server_margin, terminal_stop_margin=.5, certificate_hash='cert')
    reg.poster = post
    if expected == 'FATAL':
        with pytest.raises(RuntimeError, match='violates'):
            reg.register(args, 'n', 'scope', witness, gate)
    else:
        result = reg.register(args, 'n', 'scope', witness, gate)
        assert bool(result['certificate_issued']) == (expected == 'PASS')
        assert len(calls) == (1 if expected == 'PASS' else 0)
    assert len(planned) == 1


def test_rejected_server_publication_is_still_fatal(tmp_path, monkeypatch):
    ctx, args, witness, base = context(tmp_path, False)
    install(monkeypatch)
    reg = ctx.registrar(.0625, .125)
    reg.poster = lambda *v: dict(certificate_issued=False, committed_tokens=16)
    with pytest.raises(RuntimeError, match='published'):
        reg.register(args, 'n', 'scope', witness, guard_gate(base, False))


def test_signed_scope_generation_and_runtime_binding_is_checked_before_compiled(tmp_path, monkeypatch):
    ctx, args, _, _ = context(tmp_path)
    monkeypatch.setattr(execution, 'layout_for_level', lambda *v: {'topological_order': ['stable', 'query']})
    sample = dict(revision_session_id='n-tenant01', shared_template_id='n')
    prepared = ({'segments': []}, [], 'L2', 64, 'scope')
    cert = dict(certificate_issued=True, certificate_hash='cert', stable_prefix_hash='prefix', selected_level='L2', query_scope='scope')
    assert not ctx.admit(args, sample, prepared, cert)
    ctx.bind_certificate(args, sample, prepared, cert)
    assert ctx.admit(args, sample, prepared, cert)
    bad = deepcopy(cert)
    bad['stable_prefix_hash'] = 'different-prefix'
    assert not ctx.admit(args, sample, prepared, bad)
    assert not ctx.admit(args, sample, (*prepared[:3], 128, 'scope'), cert)
    assert not ctx.admit(args, sample, (*prepared[:4], 'different-query'), cert)
    bad = deepcopy(cert)
    bad['binding_signature'] = 'forged'
    assert not ctx.admit(args, sample, prepared, bad)


def test_coarse_gate_does_not_materialize_or_run_HTTP(tmp_path, monkeypatch):
    ctx, args, _, _ = context(tmp_path)
    calibration = dict(prefix_states={'cold': dict(cost_quantiles={'0.9': dict(information_ms=1., gpu_registration_ms=1.)},
        p_joint_lower=1., p_eligible_upper=1., p_pass_given_eligible_lower=1.)},
        save_per_reuse_median_ms=1000., raw_family_ttft_p95_ms=1., raw_global_ready_p99_ms=100.)
    monkeypatch.setattr(execution.cost, 'candidate_plan', lambda *v: pytest.fail('coarse path must not tokenize'))
    gate = ctx.build_gate(args, ({'segments': []}, [], 'L2', 64, 'scope'), calibration, 'balanced', 'n', 0, 2, {})
    assert gate['allow_verification'] and gate['plan'] is None and gate['deferred_candidate_preparation']
