#!/usr/bin/env python3
"""Independent in-situ verifier contracts and robustness reserve math."""

from __future__ import annotations

import math
from dataclasses import dataclass

from scripts.contractkv_pstp import VerifyDecision


class VerificationIncomplete(RuntimeError):
    pass


@dataclass(frozen=True)
class RawAttestation:
    token_ids: tuple[int, ...]
    token_margins: tuple[float, ...]
    finish_reason: str
    stop_token_ids: tuple[int, ...]
    model_hash: str
    tokenizer_hash: str
    chat_template_hash: str


@dataclass(frozen=True)
class VerifyThresholds:
    tau_raw: float = 0.0
    tau_abs: float = 0.0
    tau_drop: float = 4.0


@dataclass(frozen=True)
class VerifyReport:
    decision: VerifyDecision
    failure_reason: str
    answer_tokens: int
    top1_matches: int
    stop_consistent: bool
    raw_margin_q05: float
    candidate_margin_q05: float
    degradation_q95: float
    robustness_reserve: float


def quantile(values: list[float] | tuple[float, ...], q: float) -> float:
    if not values:
        raise VerificationIncomplete("empty margin sequence")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def normalized_prompt_logprob_entries(entry: object) -> list[tuple[int, float, int | None]]:
    if not isinstance(entry, dict):
        raise VerificationIncomplete("prompt logprob entry is not a mapping")
    result = []
    for token_key, item in entry.items():
        if not isinstance(item, dict) or item.get("logprob") is None:
            continue
        try:
            token_id = int(token_key)
        except (TypeError, ValueError):
            token_id_value = item.get("token_id")
            if token_id_value is None:
                continue
            token_id = int(token_id_value)
        rank = int(item["rank"]) if item.get("rank") is not None else None
        result.append((token_id, float(item["logprob"]), rank))
    return result


def target_rank_and_margin(entry: object, target_id: int) -> tuple[int, float]:
    entries = normalized_prompt_logprob_entries(entry)
    targets = [item for item in entries if item[0] == int(target_id)]
    if not targets:
        raise VerificationIncomplete(f"target token {target_id} absent")
    competitors = [logprob for token_id, logprob, _ in entries if token_id != int(target_id)]
    if not competitors:
        raise VerificationIncomplete("no competitor logprob returned")
    _, target_logprob, target_rank = targets[0]
    if target_rank is None:
        raise VerificationIncomplete(f"target token {target_id} rank missing")
    return target_rank, target_logprob - max(competitors)


def make_verify_report(
    raw: RawAttestation,
    candidate_token_ids: list[int] | tuple[int, ...],
    candidate_margins: list[float] | tuple[float, ...],
    candidate_ranks: list[int] | tuple[int, ...],
    candidate_stop_token_id: int | None,
    thresholds: VerifyThresholds,
) -> VerifyReport:
    answer_tokens = len(raw.token_ids)
    if answer_tokens == 0:
        return incomplete_report("empty answer slice")
    if len(raw.token_margins) != answer_tokens:
        return incomplete_report("raw margin length mismatch")
    if len(candidate_token_ids) != answer_tokens or len(candidate_margins) != answer_tokens or len(candidate_ranks) != answer_tokens:
        return incomplete_report("candidate answer length mismatch")
    if raw.finish_reason == "length":
        return incomplete_report("raw finish_reason=length")
    if not raw.stop_token_ids:
        return incomplete_report("raw stop metadata missing")
    if candidate_stop_token_id is None:
        return incomplete_report("candidate stop token missing")

    matches = sum(
        int(target) == int(candidate) and int(rank) == 1
        for target, candidate, rank in zip(raw.token_ids, candidate_token_ids, candidate_ranks)
    )
    stop_consistent = int(candidate_stop_token_id) in set(raw.stop_token_ids)
    raw_q05 = quantile(raw.token_margins, 0.05)
    candidate_q05 = quantile(candidate_margins, 0.05)
    degradation = [float(raw_margin) - float(candidate_margin) for raw_margin, candidate_margin in zip(raw.token_margins, candidate_margins)]
    degradation_q95 = quantile(degradation, 0.95)
    reserve = min(
        raw_q05 - thresholds.tau_raw,
        candidate_q05 - thresholds.tau_abs,
        thresholds.tau_drop - degradation_q95,
    )
    reasons = []
    if matches != answer_tokens:
        reasons.append("top1_path_mismatch")
    if not stop_consistent:
        reasons.append("stop_mismatch")
    if reserve < 0:
        reasons.append("negative_robustness_reserve")
    decision = VerifyDecision.PASS if not reasons else VerifyDecision.FAIL
    return VerifyReport(
        decision=decision,
        failure_reason=";".join(reasons),
        answer_tokens=answer_tokens,
        top1_matches=matches,
        stop_consistent=stop_consistent,
        raw_margin_q05=raw_q05,
        candidate_margin_q05=candidate_q05,
        degradation_q95=degradation_q95,
        robustness_reserve=reserve,
    )


def incomplete_report(reason: str) -> VerifyReport:
    return VerifyReport(
        decision=VerifyDecision.INCOMPLETE,
        failure_reason=reason,
        answer_tokens=0,
        top1_matches=0,
        stop_consistent=False,
        raw_margin_q05=float("nan"),
        candidate_margin_q05=float("nan"),
        degradation_q95=float("nan"),
        robustness_reserve=float("-inf"),
    )
