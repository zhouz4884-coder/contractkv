#!/usr/bin/env python3
"""Run or summarize Phase 10.5 recompute policy pressure evaluation."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any


POLICIES = [
    "vllm-default",
    "full-recompute",
    "greedy-rar-exact",
    "contractkv-rar-exact",
]

RAW_FIELDS = [
    "policy",
    "dataset",
    "trace_id",
    "model",
    "configured_max_model_len",
    "max_num_seqs",
    "completed",
    "slo_violation",
    "latency_ms",
    "ttft_ms",
    "tpot_ms",
    "blocks_freed",
    "free_gpu_blocks_before",
    "free_gpu_blocks_after",
    "full_recompute_tokens",
    "anchored_recompute_tokens",
    "recompute_events",
    "error_type",
    "error_message",
]

SUMMARY_FIELDS = [
    "policy",
    "attempted_requests",
    "completed_requests",
    "slo_compliant_requests",
    "capacity_failures",
    "completion_rate",
    "slo_compliant_req_per_sec",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "total_blocks_freed",
    "mean_block_headroom_gain",
    "total_recompute_tokens_saved_vs_full",
    "completion_lift_vs_default",
    "capacity_failure_reduction",
    "slo_goodput_delta_vs_default",
]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * q))
    return ordered[max(0, min(index, len(ordered) - 1))]


def aggregate_pressure_metrics(rows: list[dict[str, Any]], duration_sec: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["policy"]), []).append(row)

    raw_summaries = []
    for policy, items in grouped.items():
        completed = [item for item in items if _truthy(item.get("completed"))]
        slo_ok = [item for item in completed if not _truthy(item.get("slo_violation"))]
        headroom = [
            _int(item.get("free_gpu_blocks_after")) - _int(item.get("free_gpu_blocks_before"))
            for item in items
        ]
        capacity_failures = [
            item for item in items
            if str(item.get("error_type", "")).lower() in {"capacity_failure", "oom_startup", "oom_runtime", "context_overflow"}
        ]
        token_savings = [
            max(0, _int(item.get("full_recompute_tokens")) - _int(item.get("anchored_recompute_tokens")))
            for item in items
        ]
        ttft = [_float(item.get("ttft_ms")) for item in completed if _float(item.get("ttft_ms")) > 0]
        tpot = [_float(item.get("tpot_ms")) for item in completed if _float(item.get("tpot_ms")) > 0]
        raw_summaries.append({
            "policy": policy,
            "attempted_requests": len(items),
            "completed_requests": len(completed),
            "slo_compliant_requests": len(slo_ok),
            "capacity_failures": len(capacity_failures),
            "completion_rate": round(len(completed) / len(items), 6) if items else 0.0,
            "slo_compliant_req_per_sec": round(len(slo_ok) / duration_sec, 6) if duration_sec > 0 else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6) if ttft else 0.0,
            "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
            "p95_tpot_ms": round(percentile(tpot, 0.95), 6) if tpot else 0.0,
            "total_blocks_freed": sum(_int(item.get("blocks_freed")) for item in items),
            "mean_block_headroom_gain": round(sum(headroom) / len(headroom), 6) if headroom else 0.0,
            "total_recompute_tokens_saved_vs_full": sum(token_savings),
        })

    default = next((row for row in raw_summaries if row["policy"] == "vllm-default"), None)
    default_completed = int(default["completed_requests"]) if default else 0
    default_failures = int(default["capacity_failures"]) if default else 0
    default_slo = float(default["slo_compliant_req_per_sec"]) if default else 0.0
    for row in raw_summaries:
        row["completion_lift_vs_default"] = int(row["completed_requests"]) - default_completed
        row["capacity_failure_reduction"] = default_failures - int(row["capacity_failures"])
        row["slo_goodput_delta_vs_default"] = round(float(row["slo_compliant_req_per_sec"]) - default_slo, 6)
    return sorted(raw_summaries, key=lambda item: POLICIES.index(item["policy"]) if item["policy"] in POLICIES else 99)


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-input", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_eval_v0.csv"))
    parser.add_argument("--duration-sec", type=float, default=1.0)
    args = parser.parse_args()
    rows = read_csv(args.raw_input)
    summary = aggregate_pressure_metrics(rows, args.duration_sec)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"pressure_summary_rows={len(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
