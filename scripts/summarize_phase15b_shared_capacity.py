#!/usr/bin/env python3
"""Summarize the strict finite-capacity Phase 15B grid by policy and rate."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
    "policy", "arrival_rate_rps", "seeds", "cells", "all_seeds_stable",
    "min_completed_requests", "min_second_half_samples_required", "mean_completion_rate",
    "max_p95_ttft_ms", "mean_slo_goodput_rps", "max_end_backlog",
    "max_queue_slope", "mean_primer_latency_ms", "mean_cold_start_amortized_latency_ms",
    "mean_new_prefill_tokens", "claim_boundary",
]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def load(cell_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(cell_dir.glob("*_summary.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                match = re.search(r"_s(\d+)_", path.name)
                row["_seed"] = match.group(1) if match else ""
                rows.append(row)
    return rows


def summarize(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["policy"], row["arrival_rate_rps"])].append(row)
    output = []
    for (policy, rate), group in sorted(groups.items(), key=lambda item: (item[0][0], number(item[0][1]))):
        output.append({
            "policy": policy, "arrival_rate_rps": number(rate),
            "seeds": ",".join(sorted({row["_seed"] for row in group})), "cells": len(group),
            "all_seeds_stable": len(group) == 3 and all(truth(row["capacity_stable"]) for row in group),
            "min_completed_requests": min(int(number(row["completed_requests"])) for row in group),
            "min_second_half_samples_required": max(int(number(row.get("min_second_half_samples_required"))) for row in group),
            "mean_completion_rate": statistics.mean(number(row["completion_rate"]) for row in group),
            "max_p95_ttft_ms": max(number(row["p95_ttft_ms"]) for row in group),
            "mean_slo_goodput_rps": statistics.mean(number(row["slo_compliant_req_per_sec"]) for row in group),
            "max_end_backlog": max(int(number(row["end_backlog"])) for row in group),
            "max_queue_slope": max(number(row["second_half_wait_slope_sec_per_sec"]) for row in group),
            "mean_primer_latency_ms": statistics.mean(number(row["primer_latency_ms"]) for row in group),
            "mean_cold_start_amortized_latency_ms": statistics.mean(number(row["cold_start_amortized_latency_ms"]) for row in group),
            "mean_new_prefill_tokens": statistics.mean(number(row["mean_observed_new_prefill_tokens"]) for row in group),
            "claim_boundary": "Finite capacity requires all three seeds to satisfy completion, SLO, queue-slope, drain, and minimum-sample gates.",
        })
    return output


def write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load(args.cell_dir)
    if not rows:
        raise SystemExit("no capacity summary cells")
    write(args.output, summarize(rows))
    print(f"phase15b_cells={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
