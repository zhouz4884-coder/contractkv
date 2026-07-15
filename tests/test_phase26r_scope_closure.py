from scripts.phase26r_policy import (
    observation_verification_gate,
    session_benefit_gate,
    wilson_lower,
    wilson_upper,
)
from scripts.contractkv_pstp import VerifyDecision
from scripts.contractkv_verifier import RawAttestation, VerifyThresholds, make_verify_report
from scripts.phase26r_typed_contracts import (
    contract_manifest,
    evaluate_typed_contract,
    normalize_full_answer,
    repository_context_text,
)


def test_open_qa_lexical_overlap_never_publishes() -> None:
    result = evaluate_typed_contract(
        "LongBench", "qasper",
        "The study supports method A because it improves recall.",
        "The study supports method B because it improves recall.",
    )
    assert result.lexical_f1_diagnostic > .8
    assert result.decision == "UNKNOWN"
    assert result.failure_reason == "lexical_f1_is_diagnostic_only"


def test_normalization_keeps_all_lines() -> None:
    left = normalize_full_answer("Evidence A\nFinal conclusion B")
    right = normalize_full_answer("Different evidence\nFinal conclusion B")
    assert left != right


def test_repobench_reinserts_frozen_context() -> None:
    context = "def f():\n    value = 1\n    "
    result = evaluate_typed_contract(
        "RepoBench", "python_v1.1", "return value", "return value",
        context_text=context,
    )
    assert result.decision == "PASS"
    assert result.contract_code_hash == contract_manifest()["contract_code_hash"]


def test_repository_context_excludes_dynamic_segments() -> None:
    case = {"segments": [
        {"segment_type": "REPO_CONTEXT", "text": "import x\n"},
        {"segment_type": "CODE_PREFIX", "text": "def f():\n"},
        {"segment_type": "TOOL_OBS", "text": "volatile"},
    ]}
    value = repository_context_text(case)
    assert "import x" in value and "def f" in value
    assert "volatile" not in value


def test_wilson_constraint_rejects_zero_of_five() -> None:
    assert wilson_upper(0, 5) > .4
    assert wilson_upper(0, 45) > .03
    assert wilson_upper(0, 125) < .03
    assert wilson_lower(0, 125) == 0.0


def test_observation_scope_never_amortizes_safety_over_future_turns() -> None:
    result = session_benefit_gate(
        stable_prefix_tokens=5000,
        prefill_ms_per_token=.1,
        remaining_future_turns=9,
        tool_slack_ms=0,
        candidate_budget_tokens=10,
        decode_ms_per_token=1,
        pass_probability_lcb=.8,
        promotion_ms_estimate=1,
        observation_scoped=True,
    )
    assert result["expected_reuses_charged"] == 1
    assert result["remaining_future_turns"] == 9
    assert result["admit"]


def test_zero_confidence_always_rejects_tier_b() -> None:
    result = session_benefit_gate(
        stable_prefix_tokens=100000,
        prefill_ms_per_token=1,
        remaining_future_turns=9,
        tool_slack_ms=100000,
        candidate_budget_tokens=1,
        decode_ms_per_token=1,
        pass_probability_lcb=0,
        promotion_ms_estimate=0,
        observation_scoped=True,
    )
    assert not result["admit"]


def test_observation_gate_requires_p95_cost_to_fit_slack() -> None:
    admitted = observation_verification_gate(
        stable_prefix_tokens=1200, prefill_ms_per_token=.105,
        exact_pass_probability_lcb=.6, preparation_p95_ms=6700,
        tool_slack_ms=7000)
    rejected = observation_verification_gate(
        stable_prefix_tokens=3200, prefill_ms_per_token=.105,
        exact_pass_probability_lcb=.6, preparation_p95_ms=27000,
        tool_slack_ms=7000)
    assert admitted["expected_reuses_charged"] == 1
    assert admitted["admit"]
    assert not rejected["admit"]


def test_observation_gate_rejects_zero_confidence() -> None:
    result = observation_verification_gate(
        stable_prefix_tokens=100000, prefill_ms_per_token=1,
        exact_pass_probability_lcb=0, preparation_p95_ms=1,
        tool_slack_ms=1000)
    assert not result["admit"]


def test_exact_certificate_requires_terminal_stop_reserve() -> None:
    raw = RawAttestation(
        token_ids=(10, 11), token_margins=(2.0, 2.0), finish_reason="stop",
        stop_token_ids=(2,), model_hash="m", tokenizer_hash="t",
        chat_template_hash="c",
    )
    thresholds = VerifyThresholds(
        tau_raw=1.0, tau_abs=1.0, tau_drop=1.0, tau_stop=1.0)
    unsafe = make_verify_report(
        raw, [10, 11], [2.0, 2.0], [1, 1], 2, thresholds,
        candidate_stop_margin=.05)
    safe = make_verify_report(
        raw, [10, 11], [2.0, 2.0], [1, 1], 2, thresholds,
        candidate_stop_margin=2.0)
    assert unsafe.decision is VerifyDecision.FAIL
    assert unsafe.robustness_reserve < 0
    assert safe.decision is VerifyDecision.PASS
    assert safe.terminal_stop_margin == 2.0
