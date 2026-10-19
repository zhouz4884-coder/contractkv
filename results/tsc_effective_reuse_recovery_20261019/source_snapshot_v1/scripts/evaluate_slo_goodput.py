#!/usr/bin/env python3
"""Convert Phase 7 live replay rows into SLO goodput proxy metrics."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any


FIELDS = [
    "policy",
    "dataset",
    "admitted_requests_per_sec",
    "slo_compliant_requests_per_sec",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "quality_violation_rate",
    "slo_violation_rate",
    "mean_residual_stall_ms",
    "mean_controller_overhead_ms",
]


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def aggregate_goodput(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["policy"], row["dataset"]), []).append(row)
    out = []
    for (policy, dataset), group in sorted(groups.items()):
        starts = [float(r["arrival_time_ms"]) for r in group]
        ends = [float(r["arrival_time_ms"]) + float(r["total_latency_ms"]) for r in group]
        window_sec = max(0.001, (max(ends) - min(starts)) / 1000.0)
        admitted = [r for r in group if _bool(r["admitted"])]
        compliant = [r for r in admitted if not _bool(r["slo_violation"]) and not _bool(r["quality_budget_violation"])]
        ttft = [float(r["ttft_ms"]) for r in group]
        tpot = [float(r["tpot_ms"]) for r in group]
        stall = [float(r["copy_residual_stall_ms"]) for r in group]
        overhead = [float(r.get("controller_overhead_ms", 0.0)) for r in group]
        out.append(
            {
                "policy": policy,
                "dataset": dataset,
                "admitted_requests_per_sec": round(len(admitted) / window_sec, 6),
                "slo_compliant_requests_per_sec": round(len(compliant) / window_sec, 6),
                "mean_ttft_ms": round(statistics.mean(ttft), 6),
                "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6),
                "quality_violation_rate": round(sum(_bool(r["quality_budget_violation"]) for r in group) / len(group), 6),
                "slo_violation_rate": round(sum(_bool(r["slo_violation"]) for r in group) / len(group), 6),
                "mean_residual_stall_ms": round(statistics.mean(stall), 6),
                "mean_controller_overhead_ms": round(statistics.mean(overhead), 6),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-csv", type=Path, default=Path("results/workload/live_replay_raw_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/workload/slo_goodput_proxy_v0.csv"))
    args = parser.parse_args()
    rows = aggregate_goodput(read_csv(args.raw_csv))
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
