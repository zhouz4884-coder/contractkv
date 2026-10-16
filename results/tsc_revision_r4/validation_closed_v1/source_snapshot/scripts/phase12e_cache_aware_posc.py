#!/usr/bin/env python3
"""Phase 12E cache-aware POSC compiler utilities.

The Phase 12D POSC compiler optimizes a single prompt DAG. Phase 12E adds a
stateful prefix ledger so the compiler can preserve the de facto vLLM prefix
cache layout from previous turns when doing so is still topologically valid.
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_posc_layout_compiler import (
    boolean_guard_order,
    compile_layout,
    prefix_max_topological_order,
    raw_order,
    validate_topological_order,
)
from scripts.phase12_prefix_cache_ab import percentile


POLICIES = [
    "raw-order",
    "boolean-guarded",
    "posc",
    "cache-aware-posc",
    "cache-aware-posc-rebase",
]

RAW_FIELDS = [
    "trajectory_id",
    "turn_id",
    "case_type",
    "policy",
    "selected_policy",
    "layout_decision",
    "success",
    "quality_score",
    "quality_sanity",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "slo_ttft_ms",
    "actual_prompt_tokens",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "estimated_future_stable_tokens",
    "violated_edges",
    "topological_order",
    "matched_ledger_id",
    "matched_segment_ids",
    "rebase_performed",
    "rebase_hidden_fraction",
    "rebase_cost_ms",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "policy",
    "slo_ttft_ms",
    "num_requests",
    "completed_requests",
    "completion_rate",
    "quality_score_mean",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "mean_total_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "mean_actual_prompt_tokens",
    "mean_estimated_lcp_tokens",
    "mean_estimated_new_prefill_tokens",
    "mean_estimated_future_stable_tokens",
    "rebase_count",
    "rebase_hidden_fraction_mean",
    "claim_boundary",
]

CASE_SUMMARY_FIELDS = [
    "case_type",
    "policy",
    "num_requests",
    "quality_score_mean",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_estimated_lcp_tokens",
    "mean_estimated_new_prefill_tokens",
    "selected_policy_counts",
    "claim_boundary",
]


def _segment_by_id(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(segment["segment_id"]): segment for segment in segments}


def _segment_hash(segment: dict[str, Any]) -> str:
    payload = {
        "segment_id": str(segment.get("segment_id", "")),
        "segment_type": str(segment.get("segment_type", "")),
        "text": str(segment.get("text", "")),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _token_count(segment: dict[str, Any]) -> int:
    return int(segment.get("token_count") or 0)


def _is_stable(segment: dict[str, Any]) -> bool:
    return float(segment.get("cache_stability", 0.0)) >= 0.5 and float(segment.get("volatility", 0.0)) < 0.5


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class SegmentPrefixLedger:
    """In-memory record of layouts previously sent for each trajectory."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def update(self, session_id: str, turn_id: int, segments: list[dict[str, Any]], order: list[str], policy: str = "") -> None:
        by_id = _segment_by_id(segments)
        ordered = []
        for sid in order:
            if sid not in by_id:
                continue
            segment = by_id[sid]
            ordered.append(
                {
                    "segment_id": sid,
                    "segment_hash": _segment_hash(segment),
                    "token_count": _token_count(segment),
                    "segment_type": segment.get("segment_type", ""),
                }
            )
        self.entries.append(
            {
                "ledger_id": f"{session_id}:turn{turn_id}:{len(self.entries)}",
                "session_id": session_id,
                "turn_id": turn_id,
                "policy": policy,
                "ordered_segments": ordered,
            }
        )

    def matching_entries(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            return list(self.entries)
        return [entry for entry in self.entries if entry.get("session_id") == session_id]


def estimate_lcp_tokens(order: list[str], segments: list[dict[str, Any]], ledger: SegmentPrefixLedger, session_id: str | None = None) -> dict[str, Any]:
    """Estimate reusable prefix tokens by segment id+hash against ledger entries."""

    by_id = _segment_by_id(segments)
    current = []
    for sid in order:
        if sid not in by_id:
            continue
        segment = by_id[sid]
        current.append((sid, _segment_hash(segment), _token_count(segment)))

    best = {"matched_tokens": 0, "matched_segment_ids": [], "matched_ledger_id": ""}
    for entry in ledger.matching_entries(session_id):
        tokens = 0
        matched: list[str] = []
        for current_item, previous_item in zip(current, entry.get("ordered_segments", [])):
            sid, segment_hash, token_count = current_item
            if sid != previous_item.get("segment_id") or segment_hash != previous_item.get("segment_hash"):
                break
            tokens += token_count
            matched.append(sid)
        if tokens > best["matched_tokens"]:
            best = {
                "matched_tokens": tokens,
                "matched_segment_ids": matched,
                "matched_ledger_id": str(entry.get("ledger_id", "")),
            }
    return best


def _future_stable_tokens(order: list[str], segments: list[dict[str, Any]]) -> int:
    by_id = _segment_by_id(segments)
    total = 0
    for sid in order:
        segment = by_id[sid]
        if not _is_stable(segment):
            break
        total += _token_count(segment)
    return total


def _layout_decision(order: list[str], segments: list[dict[str, Any]]) -> str:
    raw = raw_order(segments)
    if order == raw:
        return "raw_order"
    return "partial_canonical"


def _cache_preserving_topological_order(segments: list[dict[str, Any]], ledger: SegmentPrefixLedger, session_id: str | None) -> list[str]:
    """Prefer the previous cached order while respecting current DAG edges."""

    by_id = _segment_by_id(segments)
    remaining = set(by_id)
    order: list[str] = []
    best_entry = None
    best_tokens = -1
    for entry in ledger.matching_entries(session_id):
        tokens = sum(int(item.get("token_count") or 0) for item in entry.get("ordered_segments", []))
        if tokens > best_tokens:
            best_tokens = tokens
            best_entry = entry

    def deps_satisfied(sid: str) -> bool:
        return all(str(dep) in order for dep in by_id[sid].get("dependencies", []))

    if best_entry:
        progress = True
        previous_ids = [str(item["segment_id"]) for item in best_entry.get("ordered_segments", [])]
        while progress:
            progress = False
            for sid in previous_ids:
                if sid in remaining and deps_satisfied(sid):
                    order.append(sid)
                    remaining.remove(sid)
                    progress = True

    static = prefix_max_topological_order(segments)
    while remaining:
        ready = [sid for sid in static if sid in remaining and deps_satisfied(sid)]
        if not ready:
            raise ValueError(f"dependency cycle or missing dependency among segments: {sorted(remaining)}")
        sid = ready[0]
        order.append(sid)
        remaining.remove(sid)
    return order


def layout_rebase_decision(rebase_cost_ms: float, future_saving_ms: float, expected_future_turns: int, tool_slack_ms: float) -> dict[str, Any]:
    gross_saving = max(0.0, future_saving_ms) * max(0, expected_future_turns)
    should = gross_saving > rebase_cost_ms and tool_slack_ms >= rebase_cost_ms
    hidden = min(1.0, max(0.0, tool_slack_ms) / max(rebase_cost_ms, 1e-9))
    return {
        "should_rebase": should,
        "gross_future_saving_ms": round(gross_saving, 6),
        "net_future_saving_ms": round(gross_saving - rebase_cost_ms, 6),
        "rebase_hidden_fraction": round(hidden, 6),
    }


def _candidate(
    policy: str,
    order: list[str],
    segments: list[dict[str, Any]],
    ledger: SegmentPrefixLedger,
    session_id: str | None,
    rebase_performed: bool = False,
    rebase_hidden_fraction: float = 0.0,
    rebase_cost_ms: float = 0.0,
) -> dict[str, Any]:
    violations = validate_topological_order(order, segments)
    lcp = estimate_lcp_tokens(order, segments, ledger, session_id=session_id)
    actual_tokens = sum(_token_count(segment) for segment in segments)
    stable_tokens = _future_stable_tokens(order, segments)
    new_prefill = max(0, actual_tokens - int(lcp["matched_tokens"]))
    return {
        "policy": policy,
        "selected_policy": policy,
        "topological_order": order,
        "layout_decision": _layout_decision(order, segments),
        "violated_edges": violations,
        "actual_prompt_tokens": actual_tokens,
        "estimated_lcp_tokens": int(lcp["matched_tokens"]),
        "estimated_new_prefill_tokens": new_prefill,
        "estimated_future_stable_tokens": stable_tokens,
        "matched_ledger_id": lcp["matched_ledger_id"],
        "matched_segment_ids": lcp["matched_segment_ids"],
        "rebase_performed": rebase_performed,
        "rebase_hidden_fraction": rebase_hidden_fraction,
        "rebase_cost_ms": rebase_cost_ms,
    }


def cache_aware_posc_compile(
    segments: list[dict[str, Any]],
    ledger: SegmentPrefixLedger,
    session_id: str,
    turn_id: int,
    tool_slack_ms: float = 0.0,
    expected_future_turns: int = 3,
    rebase_cost_ms: float = 80.0,
) -> dict[str, Any]:
    """Select the best valid layout under current cache state.

    The selector is no-regret in the estimated-prefix model because it keeps the
    boolean-guarded layout in the candidate set and selects the lowest estimated
    new-prefill cost among valid candidates.
    """

    raw = raw_order(segments)
    boolean = boolean_guard_order(segments)
    static = prefix_max_topological_order(segments)
    cache_order = _cache_preserving_topological_order(segments, ledger, session_id)

    static_candidate = _candidate("posc", static, segments, ledger, session_id)
    cache_candidate = _candidate("cache-aware-posc", cache_order, segments, ledger, session_id)
    rebase = layout_rebase_decision(
        rebase_cost_ms=rebase_cost_ms,
        future_saving_ms=max(0.0, (static_candidate["estimated_future_stable_tokens"] - cache_candidate["estimated_future_stable_tokens"]) * 0.02),
        expected_future_turns=expected_future_turns,
        tool_slack_ms=tool_slack_ms,
    )
    rebase_order = static if rebase["should_rebase"] else cache_order
    candidates = [
        _candidate("raw-order", raw, segments, ledger, session_id),
        _candidate("boolean-guarded", boolean, segments, ledger, session_id),
        static_candidate,
        cache_candidate,
        _candidate(
            "cache-aware-posc-rebase",
            rebase_order,
            segments,
            ledger,
            session_id,
            rebase_performed=bool(rebase["should_rebase"]),
            rebase_hidden_fraction=float(rebase["rebase_hidden_fraction"]),
            rebase_cost_ms=rebase_cost_ms if rebase["should_rebase"] else 0.0,
        ),
    ]
    valid = [item for item in candidates if not item["violated_edges"]]
    if not valid:
        raise ValueError("no valid layout candidate")
    preference = {
        "cache-aware-posc": 0,
        "cache-aware-posc-rebase": 1,
        "boolean-guarded": 2,
        "posc": 3,
        "raw-order": 4,
    }
    selected = min(
        valid,
        key=lambda item: (
            item["estimated_new_prefill_tokens"],
            -item["estimated_future_stable_tokens"],
            preference.get(item["policy"], 99),
        ),
    )
    result = dict(selected)
    result["selected_policy"] = selected["policy"]
    result["turn_id"] = turn_id
    result["session_id"] = session_id
    result["candidates"] = candidates
    result["reason"] = "cache_state_aware_no_regret_candidate_selection"
    return result


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def aggregate_phase12e_results(rows: list[dict[str, Any]], slo_buckets_ms: list[float]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["policy"]), []).append(row)
    out = []
    for policy, group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("success"))]
        ttft = [_float(row.get("ttft_ms")) for row in successes]
        tpot = [_float(row.get("tpot_ms")) for row in successes]
        latency = [_float(row.get("total_latency_ms")) for row in successes]
        total_latency_sec = max(sum(latency) / 1000.0, 1e-9)
        for slo in slo_buckets_ms:
            compliant = [row for row in successes if _float(row.get("ttft_ms")) <= float(slo)]
            record = {
                "policy": policy,
                "slo_ttft_ms": int(slo) if float(slo).is_integer() else slo,
                "num_requests": len(group),
                "completed_requests": len(successes),
                "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
                "quality_score_mean": round(statistics.mean(_float(row.get("quality_score")) for row in successes), 6) if successes else 0.0,
                "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
                "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
                "p95_tpot_ms": round(percentile(tpot, 0.95), 6),
                "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
                "slo_compliant_requests": len(compliant),
                "slo_compliant_req_per_sec": round(len(compliant) / total_latency_sec, 6),
                "mean_actual_prompt_tokens": round(statistics.mean(_float(row.get("actual_prompt_tokens")) for row in group), 6) if group else 0.0,
                "mean_estimated_lcp_tokens": round(statistics.mean(_float(row.get("estimated_lcp_tokens")) for row in group), 6) if group else 0.0,
                "mean_estimated_new_prefill_tokens": round(statistics.mean(_float(row.get("estimated_new_prefill_tokens")) for row in group), 6) if group else 0.0,
                "mean_estimated_future_stable_tokens": round(statistics.mean(_float(row.get("estimated_future_stable_tokens")) for row in group), 6) if group else 0.0,
                "rebase_count": sum(_bool(row.get("rebase_performed")) for row in group),
                "rebase_hidden_fraction_mean": round(statistics.mean(_float(row.get("rebase_hidden_fraction")) for row in group), 6) if group else 0.0,
                "claim_boundary": "Phase 12E ledger-estimated LCP; cached-token hit rate is not claimed unless vLLM exposes it.",
            }
            out.append({field: record.get(field, "") for field in SUMMARY_FIELDS})
    return out


def aggregate_phase12e_case_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["case_type"]), str(row["policy"])), []).append(row)
    out = []
    for (case_type, policy), group in sorted(groups.items()):
        ttft = [_float(row.get("ttft_ms")) for row in group]
        selected: dict[str, int] = {}
        for row in group:
            selected[str(row.get("selected_policy", row.get("policy", "")))] = selected.get(str(row.get("selected_policy", row.get("policy", ""))), 0) + 1
        record = {
            "case_type": case_type,
            "policy": policy,
            "num_requests": len(group),
            "quality_score_mean": round(statistics.mean(_float(row.get("quality_score")) for row in group), 6) if group else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_estimated_lcp_tokens": round(statistics.mean(_float(row.get("estimated_lcp_tokens")) for row in group), 6) if group else 0.0,
            "mean_estimated_new_prefill_tokens": round(statistics.mean(_float(row.get("estimated_new_prefill_tokens")) for row in group), 6) if group else 0.0,
            "selected_policy_counts": json.dumps(selected, sort_keys=True),
            "claim_boundary": "case-type breakdown for Phase 12E ledger-model replay.",
        }
        out.append({field: record.get(field, "") for field in CASE_SUMMARY_FIELDS})
    return out


def compile_static_policy(segments: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    compiled = compile_layout(segments, policy="posc" if policy == "posc" else policy)
    return {
        "policy": policy,
        "topological_order": compiled["topological_order"],
        "layout_decision": compiled["layout_decision"],
        "violated_edges": compiled["violated_edges"],
    }
