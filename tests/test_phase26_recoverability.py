from scripts.phase26_recoverability_common import (
    benefit_utility, classify_recoverability, freeze_budget, regret_statistics,
)
from scripts.phase26_typed_behavior_contracts import evaluate_typed_contract
from scripts.phase26d_fused_live import exact_free_path


def test_freeze_budget_is_aligned_and_bounded():
    assert freeze_budget([8, 10, 100]) == 160
    assert freeze_budget([2000]) == 1024


def test_regret_is_negative_margin_clipped_at_zero():
    result = regret_statistics([1.0, -2.0, -1.0, 3.0], [1, 2, 2, 1],
                               [1, 2, 3, 4], [1, 9, 3, 4])
    assert result["regret_max"] == 2.0
    assert result["regret_cumulative"] == 3.0
    assert result["max_consecutive_teacher_forced_divergence"] == 2
    assert result["first_free_token_divergence"] == 1


def test_typed_contracts_are_deterministic_and_fail_closed():
    ruler = evaluate_typed_contract("RULER", "niah_single_1", "Answer: 42", "42")
    assert ruler.decision == "PASS"
    qa = evaluate_typed_contract("LongBench", "hotpotqa", "New York", "NYC")
    assert qa.decision == "UNKNOWN"
    code = evaluate_typed_contract("RepoBench", "python_v1.1", "x = 1", "x=1")
    assert code.decision == "PASS"
    unsupported = evaluate_typed_contract("Other", "task", "a", "a")
    assert unsupported.decision == "UNKNOWN"


def test_bounded_qa_contract_rejects_numeric_and_polarity_changes():
    numeric = evaluate_typed_contract(
        "LongBench", "hotpotqa", "The answer is 12 and is valid.",
        "The answer is 13 and is valid.", qa_f1_threshold=.5)
    assert numeric.decision == "FAIL"
    assert numeric.failure_reason == "numeric_field_mismatch"
    polarity = evaluate_typed_contract(
        "LongBench", "qasper", "The method is valid.",
        "The method is not valid.", qa_f1_threshold=.5)
    assert polarity.decision == "FAIL"
    assert polarity.failure_reason == "polarity_marker_mismatch"


def test_fused_exact_path_requires_complete_tokens_and_terminal_match():
    raw = {"complete": True, "token_ids": [1, 2, 3], "terminal_stop_token_id": 99}
    assert exact_free_path(raw, dict(raw)) is True
    assert exact_free_path(raw, {**raw, "token_ids": [1, 2, 4]}) is False
    assert exact_free_path(raw, {**raw, "terminal_stop_token_id": 100}) is False
    assert exact_free_path(raw, {**raw, "complete": False}) is False


def test_classification_and_benefit_gate():
    assert classify_recoverability(raw_complete=True, candidate_complete=True,
                                   quality_drop=0.0, typed_decision="PASS",
                                   exact_pass=False) == "exact_path_false_negative"
    assert classify_recoverability(raw_complete=True, candidate_complete=True,
                                   quality_drop=.1, typed_decision="PASS",
                                   exact_pass=False) == "genuine_unsafe_divergence"
    assert benefit_utility(pass_probability=.5, expected_reuses=9,
                           saved_ms_per_request=100, verify_ms=300,
                           slack_ms=200)["admit"] is True
