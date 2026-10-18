#!/usr/bin/env python3
"""Join Phase 14B live replay rows with V1 scheduler prefix observations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


JOIN_FIELDS = [
    "request_id", "policy", "trajectory_id", "turn_id", "case_type", "real_ttft_ms",
    "estimated_lcp_tokens", "estimated_new_prefill_tokens", "prompt_tokens",
    "prefix_lookup_tokens", "prefix_hit_tokens", "new_prefill_tokens",
    "reused_physical_blocks", "newly_allocated_blocks", "scheduler_wait_ms",
    "metric_availability", "join_success", "claim_boundary",
]
SUMMARY_FIELDS = [
    "policy", "requests", "joined_requests", "join_success_rate", "mean_real_ttft_ms",
    "p95_real_ttft_ms", "mean_observed_prefix_hit_tokens", "mean_observed_new_prefill_tokens",
    "mean_estimated_new_prefill_tokens", "mean_reused_physical_blocks",
    "mean_newly_allocated_blocks", "pearson_observed_new_prefill_vs_ttft",
    "pearson_estimated_vs_observed_new_prefill", "claim_boundary",
]


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 2 or len(x) != len(y):
        return 0.0
    mean_x, mean_y = statistics.mean(x), statistics.mean(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y))
    return numerator / denominator if denominator else 0.0


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_join(live_rows: list[dict[str, Any]], metric_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    metrics = {str(row.get("request_id")): row for row in metric_rows}
    joined = []
    for live in live_rows:
        request_id = str(live.get("request_id") or "")
        metric = metrics.get(request_id, {})
        joined.append({
            "request_id": request_id,
            "policy": live.get("policy"),
            "trajectory_id": live.get("trajectory_id"),
            "turn_id": live.get("turn_id"),
            "case_type": live.get("case_type"),
            "real_ttft_ms": live.get("real_ttft_ms"),
            "estimated_lcp_tokens": live.get("estimated_lcp_tokens"),
            "estimated_new_prefill_tokens": live.get("estimated_new_prefill_tokens"),
            "prompt_tokens": metric.get("prompt_tokens", ""),
            "prefix_lookup_tokens": metric.get("prefix_lookup_tokens", ""),
            "prefix_hit_tokens": metric.get("prefix_hit_tokens", ""),
            "new_prefill_tokens": metric.get("new_prefill_tokens", ""),
            "reused_physical_blocks": metric.get("reused_physical_blocks", ""),
            "newly_allocated_blocks": metric.get("newly_allocated_blocks", ""),
            "scheduler_wait_ms": metric.get("scheduler_wait_ms", ""),
            "metric_availability": metric.get("metric_availability", "unavailable"),
            "join_success": bool(metric),
            "claim_boundary": "Live API row joined by server-issued request_id to a read-only V1 scheduler observation; physical block values are documented scheduler derivations.",
        })
    return joined


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_policy.setdefault(str(row.get("policy")), []).append(row)
    summary = []
    for policy, group in sorted(by_policy.items()):
        observed = [row for row in group if row.get("join_success")]
        ttft = [_number(row.get("real_ttft_ms")) for row in observed]
        new_prefill = [_number(row.get("new_prefill_tokens")) for row in observed]
        estimated = [_number(row.get("estimated_new_prefill_tokens")) for row in observed]
        summary.append({
            "policy": policy,
            "requests": len(group),
            "joined_requests": len(observed),
            "join_success_rate": round(len(observed) / len(group), 6) if group else 0.0,
            "mean_real_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_real_ttft_ms": round(_percentile(ttft, 0.95), 6),
            "mean_observed_prefix_hit_tokens": round(statistics.mean(_number(row.get("prefix_hit_tokens")) for row in observed), 6) if observed else 0.0,
            "mean_observed_new_prefill_tokens": round(statistics.mean(new_prefill), 6) if new_prefill else 0.0,
            "mean_estimated_new_prefill_tokens": round(statistics.mean(estimated), 6) if estimated else 0.0,
            "mean_reused_physical_blocks": round(statistics.mean(_number(row.get("reused_physical_blocks")) for row in observed), 6) if observed else 0.0,
            "mean_newly_allocated_blocks": round(statistics.mean(_number(row.get("newly_allocated_blocks")) for row in observed), 6) if observed else 0.0,
            "pearson_observed_new_prefill_vs_ttft": round(_pearson(new_prefill, ttft), 6),
            "pearson_estimated_vs_observed_new_prefill": round(_pearson(estimated, new_prefill), 6),
            "claim_boundary": "Observed values are from the V1 scheduler probe; missing worker-level eviction/GPU timing values remain unavailable.",
        })
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--joined-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_join(load_jsonl(args.live), load_csv(args.metrics))
    write_csv(args.joined_output, rows, JOIN_FIELDS)
    write_csv(args.summary_output, summarize(rows), SUMMARY_FIELDS)
    print(f"joined_rows={len(rows)}")
    return 0 if rows and all(row["join_success"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
