#!/usr/bin/env python3
"""Confidence and session-economics helpers for Phase 26R."""

from __future__ import annotations

import math
from typing import Any


def wilson_upper(failures: int, trials: int, z: float = 1.959963984540054) -> float:
    if trials <= 0:
        return 1.0
    p = failures / trials
    denominator = 1.0 + z * z / trials
    center = p + z * z / (2.0 * trials)
    radius = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
    return (center + radius) / denominator


def wilson_lower(successes: int, trials: int, z: float = 1.959963984540054) -> float:
    if trials <= 0:
        return 0.0
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = p + z * z / (2.0 * trials)
    radius = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
    value = (center - radius) / denominator
    return 0.0 if value < 1e-15 else min(1.0, value)


def session_benefit_gate(*, stable_prefix_tokens: int, prefill_ms_per_token: float,
                         remaining_future_turns: int, tool_slack_ms: float,
                         candidate_budget_tokens: int, decode_ms_per_token: float,
                         pass_probability_lcb: float, promotion_ms_estimate: float,
                         observation_scoped: bool = True) -> dict[str, Any]:
    # Observation-scoped behavior cannot spend future-turn safety evidence.
    expected_reuses = 1 if observation_scoped else max(1, remaining_future_turns)
    saved_per_reuse_ms = max(0.0, stable_prefix_tokens * prefill_ms_per_token)
    predicted_verify_ms = max(0.0, candidate_budget_tokens * decode_ms_per_token)
    predicted_total_cost_ms = predicted_verify_ms + max(0.0, promotion_ms_estimate)
    unhidden_cost_ms = max(0.0, predicted_total_cost_ms - max(0.0, tool_slack_ms))
    expected_saved_ms = (
        max(0.0, min(1.0, pass_probability_lcb))
        * expected_reuses * saved_per_reuse_ms
    )
    expected_gain_ms = expected_saved_ms - unhidden_cost_ms
    return {
        "stable_prefix_tokens": int(stable_prefix_tokens),
        "prefill_ms_per_token": float(prefill_ms_per_token),
        "remaining_future_turns": int(remaining_future_turns),
        "expected_reuses_charged": int(expected_reuses),
        "tool_slack_ms": float(tool_slack_ms),
        "candidate_budget_tokens": int(candidate_budget_tokens),
        "decode_ms_per_token": float(decode_ms_per_token),
        "pass_probability_lcb": float(pass_probability_lcb),
        "promotion_ms_estimate": float(promotion_ms_estimate),
        "predicted_verify_ms": predicted_verify_ms,
        "unhidden_cost_ms": unhidden_cost_ms,
        "expected_saved_ms": expected_saved_ms,
        "expected_gain_ms": expected_gain_ms,
        "admit": pass_probability_lcb > 0.0 and expected_gain_ms > 0.0,
        "scope_rule": "one_reuse_per_observation" if observation_scoped else "temporal",
    }


def observation_verification_gate(*, stable_prefix_tokens: int,
                                  prefill_ms_per_token: float,
                                  exact_pass_probability_lcb: float,
                                  preparation_p95_ms: float,
                                  tool_slack_ms: float) -> dict[str, Any]:
    """Admit verification only when its conservative observation utility is positive.

    The verifier publishes blocks for one observation only, so future turns cannot
    be charged as reuse.  The p95 preparation estimate is frozen from a disjoint
    calibration split; it must fit inside the request's declared tool slack.
    """
    saved_if_pass_ms = max(0.0, stable_prefix_tokens * prefill_ms_per_token)
    expected_saved_ms = (
        max(0.0, min(1.0, exact_pass_probability_lcb)) * saved_if_pass_ms
    )
    unhidden_cost_ms = max(0.0, preparation_p95_ms - max(0.0, tool_slack_ms))
    expected_gain_ms = expected_saved_ms - unhidden_cost_ms
    return {
        "stable_prefix_tokens": int(stable_prefix_tokens),
        "prefill_ms_per_token": float(prefill_ms_per_token),
        "exact_pass_probability_lcb": float(exact_pass_probability_lcb),
        "preparation_p95_ms": float(preparation_p95_ms),
        "tool_slack_ms": float(tool_slack_ms),
        "expected_reuses_charged": 1,
        "saved_if_pass_ms": saved_if_pass_ms,
        "expected_saved_ms": expected_saved_ms,
        "unhidden_cost_ms": unhidden_cost_ms,
        "expected_gain_ms": expected_gain_ms,
        "admit": exact_pass_probability_lcb > 0.0 and expected_gain_ms > 0.0,
        "scope_rule": "one_reuse_per_observation",
    }
