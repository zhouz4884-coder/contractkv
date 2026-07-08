#!/usr/bin/env python3
"""Build Risk-Anchored Recompute residency plans for Phase 10.5."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


MUST_RESIDENT_TYPES = {"SYS_PROMPT", "TOOL_SCHEMA"}
MUST_RECONSTRUCT_TYPES = {"USER_QUERY"}
DROP_FORBIDDEN_TYPES = MUST_RESIDENT_TYPES | MUST_RECONSTRUCT_TYPES
LOW_RISK_DEFAULT = 0.01
HIGH_RISK_DEFAULT = 1.0


def compute_segment_block_span(token_start: int, token_count: int, block_size: int) -> dict[str, int]:
    token_end = token_start + token_count
    block_start = token_start // block_size
    block_end = (token_end + block_size - 1) // block_size
    return {
        "token_start": token_start,
        "token_end": token_end,
        "logical_block_start": block_start,
        "logical_block_end": block_end,
        "block_count": block_end - block_start,
    }


def _segment_risk(segment: dict[str, Any], risk_by_segment_type: dict[str, float]) -> float:
    seg_type = str(segment.get("type", "UNKNOWN"))
    if seg_type in MUST_RESIDENT_TYPES:
        return HIGH_RISK_DEFAULT
    if seg_type in MUST_RECONSTRUCT_TYPES:
        return 0.0
    return float(risk_by_segment_type.get(seg_type, LOW_RISK_DEFAULT))


def annotate_segments(
    segments: list[dict[str, Any]],
    risk_by_segment_type: dict[str, float],
    block_size: int,
) -> list[dict[str, Any]]:
    annotated = []
    cursor = 0
    for index, segment in enumerate(segments):
        token_count = int(segment.get("token_count") or 0)
        row = dict(segment)
        row.update(compute_segment_block_span(cursor, token_count, block_size))
        row["segment_id"] = str(row.get("segment_id", f"seg-{index}"))
        row["real_quality_risk"] = _segment_risk(row, risk_by_segment_type)
        row["must_resident"] = row.get("type") in MUST_RESIDENT_TYPES
        row["must_reconstruct"] = row.get("type") in MUST_RECONSTRUCT_TYPES
        row["drop_forbidden"] = row.get("type") in DROP_FORBIDDEN_TYPES
        annotated.append(row)
        cursor += token_count
    return annotated


def _keep_full_request(annotated: list[dict[str, Any]], block_size: int, boundary_guard_blocks: int, reason: str) -> dict[str, Any]:
    last = annotated[-1] if annotated else {"token_end": 0, "logical_block_end": 0}
    anchor_token_end = int(last["token_end"])
    boundary_guard_tokens = boundary_guard_blocks * block_size
    return {
        "candidate_anchor_id": str(last.get("segment_id", "none")),
        "residency_decision": "keep_full_request",
        "anchor_segment_index": len(annotated) - 1,
        "anchor_token_end": anchor_token_end,
        "anchor_block_end": int(last["logical_block_end"]),
        "suffix_blocks_releasable": 0,
        "reclaimed_blocks": 0,
        "estimated_recompute_tokens": 0,
        "estimated_recompute_ms": 0.0,
        "slack_ms": 0.0,
        "slo_margin_ms": 0.0,
        "slack_feasible": False,
        "anchor_utility": 0.0,
        "estimated_quality_risk": max([float(item["real_quality_risk"]) for item in annotated] or [0.0]),
        "boundary_guard_tokens": boundary_guard_tokens,
        "recompute_start_token": max(0, anchor_token_end - boundary_guard_tokens),
        "decision_reason": reason,
        "recomputed_segment_types": [],
        "dropped_segment_types": [],
    }


def choose_anchor_boundary(
    segments: list[dict[str, Any]],
    risk_by_segment_type: dict[str, float],
    block_size: int = 16,
    risk_threshold: float = 0.05,
    min_suffix_blocks: int = 64,
    slack_ms: float = 0.0,
    slo_margin_ms: float = 0.0,
    recompute_ms_per_token: float = 0.005,
    boundary_guard_blocks: int = 2,
) -> dict[str, Any]:
    annotated = annotate_segments(segments, risk_by_segment_type, block_size)
    if not annotated:
        return _keep_full_request([], block_size, boundary_guard_blocks, "empty_request")

    best: dict[str, Any] | None = None
    boundary_guard_tokens = boundary_guard_blocks * block_size
    for anchor_index, anchor in enumerate(annotated):
        prefix = annotated[: anchor_index + 1]
        suffix = annotated[anchor_index + 1 :]
        if not suffix:
            continue
        if any(item["type"] in MUST_RESIDENT_TYPES for item in suffix):
            continue
        if not any(item["type"] not in MUST_RECONSTRUCT_TYPES for item in suffix):
            continue
        suffix_blocks = sum(int(item["block_count"]) for item in suffix)
        suffix_tokens = sum(int(item["token_count"]) for item in suffix)
        suffix_risk = max([float(item["real_quality_risk"]) for item in suffix if item["type"] not in MUST_RECONSTRUCT_TYPES] or [0.0])
        if suffix_blocks < min_suffix_blocks or suffix_risk > risk_threshold:
            continue
        estimated_recompute_ms = round(suffix_tokens * recompute_ms_per_token, 6)
        feasible_budget = max(float(slack_ms), float(slo_margin_ms))
        slack_feasible = feasible_budget <= 0 or estimated_recompute_ms <= feasible_budget
        utility = round(suffix_blocks / max(estimated_recompute_ms, 1.0), 6)
        candidate = {
            "candidate_anchor_id": str(anchor["segment_id"]),
            "residency_decision": "release_suffix_candidate",
            "anchor_segment_index": anchor_index,
            "anchor_token_end": int(anchor["token_end"]),
            "anchor_block_end": int(anchor["logical_block_end"]),
            "suffix_blocks_releasable": suffix_blocks,
            "reclaimed_blocks": suffix_blocks,
            "estimated_recompute_tokens": suffix_tokens,
            "estimated_recompute_ms": estimated_recompute_ms,
            "slack_ms": float(slack_ms),
            "slo_margin_ms": float(slo_margin_ms),
            "slack_feasible": slack_feasible,
            "anchor_utility": utility if slack_feasible else 0.0,
            "estimated_quality_risk": suffix_risk,
            "boundary_guard_tokens": boundary_guard_tokens,
            "recompute_start_token": max(0, int(anchor["token_end"]) - boundary_guard_tokens),
            "decision_reason": "high_block_yield_with_safe_recompute" if slack_feasible else "recompute_budget_exceeded",
            "recomputed_segment_types": sorted({str(item["type"]) for item in suffix}),
            "dropped_segment_types": [],
            "prefix_segment_types": sorted({str(item["type"]) for item in prefix}),
        }
        if not slack_feasible:
            continue
        if best is None or candidate["anchor_utility"] > best["anchor_utility"]:
            best = candidate
    if best is not None:
        return best
    return _keep_full_request(annotated, block_size, boundary_guard_blocks, "no_safe_recompute_suffix")


def make_anchor_residency_record(
    trace_id: str,
    request_id: str,
    dataset: str,
    task: str,
    segments: list[dict[str, Any]],
    risk_by_segment_type: dict[str, float],
    block_size: int = 16,
    tool_slack_ms: float = 0.0,
    slo_margin_ms: float = 0.0,
    recompute_ms_per_token: float = 0.005,
    boundary_guard_blocks: int = 2,
) -> dict[str, Any]:
    annotated = annotate_segments(segments, risk_by_segment_type, block_size)
    decision = choose_anchor_boundary(
        segments=segments,
        risk_by_segment_type=risk_by_segment_type,
        block_size=block_size,
        slack_ms=tool_slack_ms,
        slo_margin_ms=slo_margin_ms,
        recompute_ms_per_token=recompute_ms_per_token,
        boundary_guard_blocks=boundary_guard_blocks,
    )
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "dataset": dataset,
        "task": task,
        "block_size": block_size,
        "candidate_anchor_id": decision["candidate_anchor_id"],
        "anchor_token_end": decision["anchor_token_end"],
        "anchor_block_end": decision["anchor_block_end"],
        "suffix_blocks_releasable": decision["suffix_blocks_releasable"],
        "reclaimed_blocks": decision["reclaimed_blocks"],
        "estimated_recompute_tokens": decision["estimated_recompute_tokens"],
        "estimated_recompute_ms": decision["estimated_recompute_ms"],
        "slack_ms": decision["slack_ms"],
        "slo_margin_ms": decision["slo_margin_ms"],
        "slack_feasible": decision["slack_feasible"],
        "anchor_utility": decision["anchor_utility"],
        "estimated_quality_risk": decision["estimated_quality_risk"],
        "boundary_guard_tokens": decision["boundary_guard_tokens"],
        "recompute_start_token": decision["recompute_start_token"],
        "decision_reason": decision["decision_reason"],
        "residency_decision": decision["residency_decision"],
        "recomputed_segment_types": decision["recomputed_segment_types"],
        "dropped_segment_types": decision["dropped_segment_types"],
        "segments": annotated,
    }


def load_risk_by_segment_type(path: Path) -> dict[str, float]:
    risks: dict[str, float] = {}
    if not path.exists():
        return risks
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("condition") not in {"segment_eviction", "context_truncation"}:
                continue
            risk = float(row.get("mean_quality_drop") or 0.0)
            dataset = row.get("dataset", "")
            task = row.get("task", "")
            if dataset == "RepoBench" or "repobench" in task.lower() or task == "lcc":
                key = "REPO_CONTEXT"
            elif dataset == "RULER":
                key = "SYNTHETIC_CONTEXT"
            else:
                key = "RAG_CHUNK"
            risks[key] = max(risks.get(key, 0.0), risk)
    risks.setdefault("CHAT_HISTORY", LOW_RISK_DEFAULT)
    risks.setdefault("SCRATCHPAD", LOW_RISK_DEFAULT)
    risks.setdefault("USER_QUERY", 0.0)
    return risks


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/anchor_residency_plan_v0.jsonl"))
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--recompute-ms-per-token", type=float, default=0.005)
    parser.add_argument("--boundary-guard-blocks", type=int, default=2)
    args = parser.parse_args()
    risk_by_segment_type = load_risk_by_segment_type(args.risk_summary)
    rows = []
    for index, trace in enumerate(load_jsonl(args.traces)):
        rows.append(
            make_anchor_residency_record(
                trace_id=str(trace.get("trace_id", index)),
                request_id=str(trace.get("request_id", trace.get("trace_id", index))),
                dataset=str(trace.get("dataset", "")),
                task=str(trace.get("task", "")),
                segments=list(trace.get("segments", [])),
                risk_by_segment_type=risk_by_segment_type,
                block_size=args.block_size,
                tool_slack_ms=float(trace.get("tool_slack_ms") or 0.0),
                slo_margin_ms=float(trace.get("slo_ttft_ms") or 0.0),
                recompute_ms_per_token=args.recompute_ms_per_token,
                boundary_guard_blocks=args.boundary_guard_blocks,
            )
        )
    write_jsonl(args.output, rows)
    print(f"anchor_plan_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
