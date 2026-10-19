#!/usr/bin/env python3
"""Build Phase 5 controller input tables from characterization artifacts."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


RISK_SUMMARY_FIELDS = [
    "dataset",
    "task",
    "segment_type",
    "action",
    "num_records",
    "mean_quality_drop",
    "p50_quality_drop",
    "p95_quality_drop",
    "max_quality_drop",
    "risk_level",
    "allowed_under_1pct",
    "allowed_under_2pct",
]

COST_FIELDS = [
    "action",
    "segment_type",
    "estimated_latency_ms",
    "estimated_memory_delta_mb",
    "estimated_transfer_mb",
    "estimated_bandwidth_gbps",
    "estimated_interference_penalty_ms",
    "source",
    "notes",
]

ACTIONS = [
    "reuse_exact",
    "reuse_shifted_proxy",
    "repair_boundary_proxy",
    "recompute_full",
    "precision_fp16",
    "precision_int8_proxy",
    "precision_int4_proxy",
    "placement_vram",
    "placement_host",
    "prefetch_host_to_gpu",
    "offload_gpu_to_host",
    "evict_segment",
]

SEGMENT_COMPLEXITY = {
    "SYS_PROMPT": 0.7,
    "USER_QUERY": 0.6,
    "RAG_CHUNK": 1.15,
    "HAYSTACK": 1.2,
    "NEEDLE": 0.9,
    "REPO_CONTEXT": 1.1,
    "CODE_PREFIX": 1.0,
    "ANSWER": 0.7,
}


def _float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        return float(value if value != "" else default)
    except (TypeError, ValueError):
        return default


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * pct
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    frac = index - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def risk_level(mean_drop: float, p95_drop: float, max_drop: float) -> str:
    eps = 1e-12
    if max_drop >= 0.5:
        return "forbidden"
    if mean_drop <= 0.01 + eps and p95_drop <= 0.02 + eps:
        return "low"
    if mean_drop <= 0.03 + eps:
        return "medium"
    return "high"


def build_risk_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["task"], row["segment_type"], row["action"])].append(_float(row, "quality_drop"))

    summary = []
    for (dataset, task, segment_type, action), drops in sorted(groups.items()):
        mean_drop = statistics.mean(drops)
        p50 = percentile(drops, 0.5)
        p95 = percentile(drops, 0.95)
        max_drop = max(drops)
        summary.append(
            {
                "dataset": dataset,
                "task": task,
                "segment_type": segment_type,
                "action": action,
                "num_records": len(drops),
                "mean_quality_drop": round(mean_drop, 6),
                "p50_quality_drop": round(p50, 6),
                "p95_quality_drop": round(p95, 6),
                "max_quality_drop": round(max_drop, 6),
                "risk_level": risk_level(mean_drop, p95, max_drop),
                "allowed_under_1pct": mean_drop <= 0.01 and p95 <= 0.01,
                "allowed_under_2pct": mean_drop <= 0.02 and p95 <= 0.02,
            }
        )
    return summary


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _best_bandwidth(path: Path) -> float:
    rows = _read_csv(path)
    values = [max(_float(row, "bandwidth_GBps"), _float(row, "bandwidth_gbps")) for row in rows]
    return max(values) if values else 12.0


def _interference_penalty(path: Path) -> float:
    rows = _read_csv(path)
    penalties = []
    for row in rows:
        if row.get("mode", "").startswith("decode_plus"):
            with_copy = _float(row, "decode_tpot_ms_with_copy")
            without_copy = _float(row, "decode_tpot_ms_without_copy")
            if with_copy > 0 and without_copy > 0:
                penalties.append(max(0.0, with_copy - without_copy))
    return round(statistics.mean(penalties), 3) if penalties else 5.0


def build_cost_rows(
    segment_types: list[str],
    h2d_gbps: float,
    d2h_gbps: float,
    interference_ms: float,
) -> list[dict[str, Any]]:
    rows = []
    for segment_type in sorted(set(segment_types)):
        complexity = SEGMENT_COMPLEXITY.get(segment_type, 1.0)
        for action in ACTIONS:
            latency = 1.0 * complexity
            memory_delta = 0.0
            transfer_mb = 0.0
            bandwidth = 0.0
            penalty = 0.0
            source = "phase5_proxy"
            notes = "Estimated per 1K segment tokens; trace-level proxy, not a vLLM kernel measurement."
            if action == "reuse_exact":
                latency = 1.5 * complexity
            elif action == "reuse_shifted_proxy":
                latency = 6.0 * complexity
                source = "quality_risk_ledger_v0"
            elif action == "repair_boundary_proxy":
                latency = 10.0 * complexity
                source = "quality_risk_ledger_v0"
            elif action == "recompute_full":
                latency = 24.0 * complexity
                memory_delta = 18.0 * complexity
                source = "phase2_5_actual_context_scaling"
            elif action == "precision_fp16":
                latency = 0.5 * complexity
            elif action == "precision_int8_proxy":
                latency = 2.0 * complexity
                memory_delta = -8.0 * complexity
            elif action == "precision_int4_proxy":
                latency = 3.5 * complexity
                memory_delta = -12.0 * complexity
            elif action == "placement_vram":
                latency = 0.5 * complexity
                memory_delta = 16.0 * complexity
            elif action == "placement_host":
                latency = 1.0 * complexity
                memory_delta = -16.0 * complexity
            elif action == "prefetch_host_to_gpu":
                transfer_mb = 16.0 * complexity
                bandwidth = h2d_gbps
                penalty = interference_ms
                latency = (transfer_mb / max(h2d_gbps, 0.001)) + penalty
                source = "phase2_6_h2d_and_interference"
            elif action == "offload_gpu_to_host":
                transfer_mb = 16.0 * complexity
                bandwidth = d2h_gbps
                penalty = interference_ms
                latency = (transfer_mb / max(d2h_gbps, 0.001)) + penalty
                source = "phase2_6_d2h_and_interference"
            elif action == "evict_segment":
                latency = 0.4 * complexity
                memory_delta = -18.0 * complexity
                source = "quality_risk_ledger_v0"

            rows.append(
                {
                    "action": action,
                    "segment_type": segment_type,
                    "estimated_latency_ms": round(latency, 4),
                    "estimated_memory_delta_mb": round(memory_delta, 4),
                    "estimated_transfer_mb": round(transfer_mb, 4),
                    "estimated_bandwidth_gbps": round(bandwidth, 4),
                    "estimated_interference_penalty_ms": round(penalty, 4),
                    "source": source,
                    "notes": notes,
                }
            )
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--risk-ledger", type=Path, default=Path("results/risk_ledger/quality_risk_ledger_v0.csv"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/risk_ledger/quality_risk_summary_v0.csv"))
    parser.add_argument("--cost-table", type=Path, default=Path("results/cost/segment_action_cost_table_v0.csv"))
    parser.add_argument("--h2d", type=Path, default=Path("results/hardware/h2d_bandwidth.csv"))
    parser.add_argument("--d2h", type=Path, default=Path("results/hardware/d2h_bandwidth.csv"))
    parser.add_argument("--interference", type=Path, default=Path("results/hardware/copy_decode_interference.csv"))
    args = parser.parse_args()

    ledger_rows = _read_csv(args.risk_ledger)
    summary = build_risk_summary(ledger_rows)
    write_csv(args.risk_summary, RISK_SUMMARY_FIELDS, summary)
    segment_types = sorted({row["segment_type"] for row in ledger_rows})
    cost_rows = build_cost_rows(
        segment_types,
        h2d_gbps=_best_bandwidth(args.h2d),
        d2h_gbps=_best_bandwidth(args.d2h),
        interference_ms=_interference_penalty(args.interference),
    )
    write_csv(args.cost_table, COST_FIELDS, cost_rows)
    print(f"risk_summary_rows={len(summary)}")
    print(f"cost_rows={len(cost_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
