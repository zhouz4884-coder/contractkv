#!/usr/bin/env python3
"""Recompute Phase 7 live replay rows under multiple SLO budgets."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any


SLO_BUCKETS_MS = [200, 300, 500, 800, 1000]

FIELDS = [
    "policy",
    "dataset",
    "slo_budget_ms",
    "num_requests",
    "admission_rate",
    "slo_violation_rate",
    "quality_violation_rate",
    "slo_compliant_req_per_sec",
    "admitted_req_per_sec",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "mean_residual_stall_ms",
    "mean_controller_overhead_ms",
]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _window_sec(group: list[dict[str, Any]]) -> float:
    starts = [_float(row, "arrival_time_ms") for row in group]
    ends = [_float(row, "arrival_time_ms") + _float(row, "total_latency_ms") for row in group]
    return max(0.001, (max(ends) - min(starts)) / 1000.0)


def recompute_slo_rows(rows: list[dict[str, Any]], slo_buckets: list[int] | None = None) -> list[dict[str, Any]]:
    slo_buckets = slo_buckets or SLO_BUCKETS_MS
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["policy"], row["dataset"]), []).append(row)

    out = []
    for (policy, dataset), group in sorted(groups.items()):
        ttft = [_float(row, "ttft_ms") for row in group]
        tpot = [_float(row, "tpot_ms") for row in group]
        stall = [_float(row, "copy_residual_stall_ms") for row in group]
        overhead = [_float(row, "controller_overhead_ms") for row in group]
        quality_flags = [_bool(row.get("quality_budget_violation", False)) for row in group]
        admitted_flags = [_bool(row.get("admitted", False)) for row in group]
        window_sec = _window_sec(group)
        for slo in slo_buckets:
            slo_flags = [value > slo for value in ttft]
            admitted = [a and not q for a, q in zip(admitted_flags, quality_flags)]
            compliant = [a and not q and not s for a, q, s in zip(admitted_flags, quality_flags, slo_flags)]
            out.append(
                {
                    "policy": policy,
                    "dataset": dataset,
                    "slo_budget_ms": slo,
                    "num_requests": len(group),
                    "admission_rate": round(sum(admitted) / len(group), 6),
                    "slo_violation_rate": round(sum(slo_flags) / len(group), 6),
                    "quality_violation_rate": round(sum(quality_flags) / len(group), 6),
                    "slo_compliant_req_per_sec": round(sum(compliant) / window_sec, 6),
                    "admitted_req_per_sec": round(sum(admitted) / window_sec, 6),
                    "mean_ttft_ms": round(statistics.mean(ttft), 6),
                    "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
                    "mean_tpot_ms": round(statistics.mean(tpot), 6),
                    "mean_residual_stall_ms": round(statistics.mean(stall), 6),
                    "mean_controller_overhead_ms": round(statistics.mean(overhead), 6),
                }
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-csv", type=Path, default=Path("results/workload/live_replay_raw_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/workload/slo_sensitivity_v0.csv"))
    parser.add_argument("--slo-buckets-ms", default="200,300,500,800,1000")
    args = parser.parse_args()
    buckets = [int(item) for item in args.slo_buckets_ms.split(",") if item]
    rows = recompute_slo_rows(read_csv(args.raw_csv), buckets)
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
