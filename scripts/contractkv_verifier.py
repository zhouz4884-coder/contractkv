#!/usr/bin/env python3
"""Independent in-situ verifier contracts and robustness reserve math."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

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
    # Disabled by default for backward compatibility with pre-Phase-26R
    # manifests. New observation-scoped policies must freeze a finite value.
    tau_stop: float = float("-inf")


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
    terminal_stop_margin: float
    robustness_reserve: float
    policy_hash: str = ""
    policy_version: str = ""
    attestation_mode: str = ""


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
    candidate_stop_margin: float | None = None,
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
    if math.isfinite(thresholds.tau_stop) and candidate_stop_margin is None:
        return incomplete_report("terminal stop margin unavailable")

    matches = sum(
        int(target) == int(candidate) and int(rank) == 1
        for target, candidate, rank in zip(raw.token_ids, candidate_token_ids, candidate_ranks)
    )
    stop_consistent = candidate_stop_token_id is not None and int(candidate_stop_token_id) in set(raw.stop_token_ids)
    raw_q05 = quantile(raw.token_margins, 0.05)
    candidate_q05 = quantile(candidate_margins, 0.05)
    degradation = [float(raw_margin) - float(candidate_margin) for raw_margin, candidate_margin in zip(raw.token_margins, candidate_margins)]
    degradation_q95 = quantile(degradation, 0.95)
    reserve_terms = [
        raw_q05 - thresholds.tau_raw,
        candidate_q05 - thresholds.tau_abs,
        thresholds.tau_drop - degradation_q95,
    ]
    if math.isfinite(thresholds.tau_stop):
        assert candidate_stop_margin is not None
        reserve_terms.append(float(candidate_stop_margin) - thresholds.tau_stop)
    reserve = min(reserve_terms)
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
        terminal_stop_margin=(float(candidate_stop_margin)
                              if candidate_stop_margin is not None
                              else float("nan")),
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
        terminal_stop_margin=float("nan"),
        robustness_reserve=float("-inf"),
    )


def split_terminal_stop_token(
    token_ids: list[int] | tuple[int, ...],
    token_margins: list[float] | tuple[float, ...],
    finish_reason: str,
) -> tuple[list[int], list[float], int]:
    """Separate the single terminal stop token from a stopped completion.

    vLLM's token-ID completion payload includes EOS in the returned sequence.
    The verifier must teacher-force answer tokens followed by that same EOS
    exactly once; treating EOS as an answer token shifts the stop check by one.
    """
    ids = [int(value) for value in token_ids]
    margins = [float(value) for value in token_margins]
    if finish_reason != "stop":
        raise VerificationIncomplete(f"raw finish_reason={finish_reason}")
    if len(ids) < 2 or len(margins) != len(ids):
        raise VerificationIncomplete("raw completion lacks one answer token plus terminal stop")
    return ids[:-1], margins[:-1], ids[-1]


def report_from_prompt_logprob_tensors(payload: dict, tensors: object) -> VerifyReport:
    """Build a compact report inside EngineCore before scheduler cleanup."""
    try:
        lists = tensors.tolist() if hasattr(tensors, "tolist") else tensors.tolists()
        token_rows = lists.logprob_token_ids
        logprob_rows = lists.logprobs
        ranks_all = lists.sampled_token_ranks
        raw_ids = [int(value) for value in payload["raw_token_ids"]]
        raw_margins = [float(value) for value in payload["raw_token_margins"]]
        answer_start = int(payload["candidate_answer_start"])
        stop_token_ids = tuple(int(value) for value in payload["stop_token_ids"])
        candidate_margins = []
        candidate_ranks = []
        for offset, target in enumerate(raw_ids):
            row_index = answer_start - 1 + offset
            ids = [int(value) for value in token_rows[row_index]]
            values = [float(value) for value in logprob_rows[row_index]]
            target_values = [value for token_id, value in zip(ids, values) if token_id == target]
            competitors = [value for token_id, value in zip(ids, values) if token_id != target]
            if not target_values or not competitors:
                raise VerificationIncomplete(f"candidate target/competitor unavailable at answer offset {offset}")
            candidate_margins.append(target_values[0] - max(competitors))
            candidate_ranks.append(int(ranks_all[row_index]))
        stop_row = answer_start - 1 + len(raw_ids)
        stop_target = int(payload["candidate_stop_token_id"])
        stop_rank = int(ranks_all[stop_row])
        stop_ids = [int(value) for value in token_rows[stop_row]]
        stop_values = [float(value) for value in logprob_rows[stop_row]]
        stop_targets = [value for token_id, value in zip(stop_ids, stop_values)
                        if token_id == stop_target]
        stop_competitors = [value for token_id, value in zip(stop_ids, stop_values)
                            if token_id != stop_target]
        if not stop_targets or not stop_competitors:
            raise VerificationIncomplete("terminal stop target/competitor unavailable")
        stop_margin = stop_targets[0] - max(stop_competitors)
        candidate_stop = stop_target if stop_rank == 1 and stop_target in stop_ids else None
        raw = RawAttestation(
            token_ids=tuple(raw_ids), token_margins=tuple(raw_margins),
            finish_reason=str(payload["raw_finish_reason"]),
            stop_token_ids=stop_token_ids,
            model_hash=str(payload["model_hash"]),
            tokenizer_hash=str(payload["tokenizer_hash"]),
            chat_template_hash=str(payload["chat_template_hash"]),
        )
        thresholds = VerifyThresholds(**dict(payload["thresholds"]))
        report = make_verify_report(
            raw, raw_ids, candidate_margins, candidate_ranks, candidate_stop,
            thresholds, candidate_stop_margin=stop_margin)
        return replace(report,
                       policy_hash=str(payload.get("policy_hash", "")),
                       policy_version=str(payload.get("policy_version", "")),
                       attestation_mode=str(payload.get("attestation_mode", "")))
    except Exception as exc:
        return replace(incomplete_report(str(exc)),
                       policy_hash=str(payload.get("policy_hash", "")),
                       policy_version=str(payload.get("policy_version", "")),
                       attestation_mode=str(payload.get("attestation_mode", "")))
