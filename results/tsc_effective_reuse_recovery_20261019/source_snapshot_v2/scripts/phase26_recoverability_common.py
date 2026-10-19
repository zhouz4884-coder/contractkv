#!/usr/bin/env python3
"""Pure Phase 26 math and classification helpers."""

from __future__ import annotations

import math
import statistics
from typing import Any


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position); upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def freeze_budget(lengths: list[int], *, q: float = .99, delta: int = 32,
                  alignment: int = 32, minimum: int = 128,
                  maximum: int = 1024) -> int:
    target = math.ceil(percentile([float(value) for value in lengths], q) + delta)
    aligned = math.ceil(target / alignment) * alignment
    return max(minimum, min(maximum, aligned))


def regret_statistics(margins: list[float], ranks: list[int],
                      raw_ids: list[int], candidate_ids: list[int]) -> dict[str, Any]:
    regrets = [max(0.0, -float(value)) for value in margins]
    positive = [index for index, value in enumerate(regrets) if value > 0]
    runs: list[int] = []
    current = 0
    for value in regrets:
        if value > 0:
            current += 1
        elif current:
            runs.append(current); current = 0
    if current:
        runs.append(current)
    first_token_divergence = next(
        (index for index, pair in enumerate(zip(raw_ids, candidate_ids)) if pair[0] != pair[1]),
        min(len(raw_ids), len(candidate_ids)) if raw_ids != candidate_ids else -1,
    )
    reconverged = False
    if first_token_divergence >= 0:
        reconverged = any(
            raw_ids[index:index + 3] == candidate_ids[index:index + 3]
            for index in range(first_token_divergence + 1,
                               max(first_token_divergence + 1, min(len(raw_ids), len(candidate_ids)) - 2))
        )
    return {
        "regret_max": max(regrets, default=0.0),
        "regret_q95": percentile(regrets, .95),
        "regret_mean": statistics.mean(regrets) if regrets else 0.0,
        "regret_positive_fraction": len(positive) / max(1, len(regrets)),
        "regret_cumulative": sum(regrets),
        "terminal_regret": regrets[-1] if regrets else 0.0,
        "first_teacher_forced_divergence": positive[0] if positive else -1,
        "max_consecutive_teacher_forced_divergence": max(runs, default=0),
        "first_free_token_divergence": first_token_divergence,
        "free_path_reconverged": reconverged,
        "top1_match_fraction": sum(int(rank) == 1 for rank in ranks) / max(1, len(ranks)),
    }


def classify_recoverability(*, raw_complete: bool, candidate_complete: bool,
                            quality_drop: float | None, typed_decision: str,
                            exact_pass: bool, epsilon: float = .03) -> str:
    if exact_pass:
        return "exact_pass"
    if not raw_complete or not candidate_complete or quality_drop is None:
        return "protocol_unavailable"
    if quality_drop > epsilon:
        return "genuine_unsafe_divergence"
    if typed_decision == "PASS":
        return "exact_path_false_negative"
    return "bounded_task_safe_but_not_online_certified"


def benefit_utility(*, pass_probability: float, expected_reuses: int,
                    saved_ms_per_request: float, verify_ms: float,
                    slack_ms: float, interference_ms: float = 0.0) -> dict[str, float | bool]:
    effective_cost = max(0.0, verify_ms - slack_ms) + max(0.0, interference_ms)
    expected_gain = pass_probability * expected_reuses * saved_ms_per_request - effective_cost
    return {
        "effective_verify_cost_ms": effective_cost,
        "expected_gain_ms": expected_gain,
        "admit": expected_gain > 0.0,
    }
