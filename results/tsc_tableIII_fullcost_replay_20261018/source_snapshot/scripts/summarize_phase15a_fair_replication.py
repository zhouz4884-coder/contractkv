#!/usr/bin/env python3
"""Aggregate fresh-process Phase 15A natural mixed-agent cells."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile


SUMMARY_FIELDS = [
    "concurrency", "policy", "seeds", "fresh_process_cells", "requests",
    "completion_rate", "quality_sanity_rate", "fair_content_signature_match",
    "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "p95_tpot_ms",
    "mean_prefix_hit_tokens", "mean_observed_new_prefill_tokens",
    "p95_compiler_overhead_ms", "slo_1000_goodput_rps", "slo_2000_goodput_rps",
    "slo_3000_goodput_rps", "mean_metric_join_success_rate", "claim_boundary",
]


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def load_rows(cell_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(cell_dir.glob("*_raw.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_cell_path"] = str(path)
                match = re.search(r"_s(\d+)_c(\d+)_", path.name)
                row["_seed"] = match.group(1) if match else ""
                rows.append(row)
    return rows


def summarize(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(int(row["concurrency"]), row["policy"])].append(row)
    signature_by_seed: dict[tuple[str, int], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        signature_by_seed[(row["_seed"], int(row["concurrency"]))][row["policy"]].add(row["segment_multiset_sha256"])
    output = []
    for (concurrency, policy), group in sorted(groups.items()):
        ttft = [as_float(row["ttft_ms"]) for row in group if as_bool(row["success"])]
        tpot = [as_float(row["tpot_ms"]) for row in group if as_bool(row["success"])]
        cells = {row["_cell_path"] for row in group}
        seeds = sorted({row["_seed"] for row in group})
        fair = all(
            all(values == next(iter(policies.values())) for values in policies.values())
            for (seed, level), policies in signature_by_seed.items()
            if level == concurrency and len(policies) == 3
        )
        wall_by_cell = {path: max(as_float(row["batch_wall_time_ms"]) for row in group if row["_cell_path"] == path) for path in cells}
        record = {
            "concurrency": concurrency, "policy": policy, "seeds": ",".join(seeds),
            "fresh_process_cells": len(cells), "requests": len(group),
            "completion_rate": sum(as_bool(row["success"]) for row in group) / max(1, len(group)),
            "quality_sanity_rate": sum(as_bool(row["quality_sanity"]) for row in group) / max(1, len(group)),
            "fair_content_signature_match": fair,
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
            "p95_ttft_ms": percentile(ttft, .95),
            "mean_tpot_ms": statistics.mean(tpot) if tpot else 0.0,
            "p95_tpot_ms": percentile(tpot, .95),
            "mean_prefix_hit_tokens": statistics.mean(as_float(row["prefix_hit_tokens"]) for row in group),
            "mean_observed_new_prefill_tokens": statistics.mean(as_float(row["observed_new_prefill_tokens"]) for row in group),
            "p95_compiler_overhead_ms": percentile([as_float(row["compiler_overhead_ms"]) for row in group], .95),
            "mean_metric_join_success_rate": statistics.mean(1.0 if as_bool(row["metric_join_success"]) else 0.0 for row in group),
            "claim_boundary": "Fresh process and empty prefix cache per policy/concurrency/seed cell; identical segment-content multiset is checked across policies.",
        }
        for slo in (1000, 2000, 3000):
            values = []
            for path in cells:
                cell_rows = [row for row in group if row["_cell_path"] == path]
                compliant = sum(as_bool(row["success"]) and as_bool(row["quality_sanity"]) and as_float(row["ttft_ms"]) <= slo for row in cell_rows)
                values.append(compliant / max(1e-9, wall_by_cell[path] / 1000.0))
            record[f"slo_{slo}_goodput_rps"] = statistics.mean(values) if values else 0.0
        output.append(record)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.cell_dir)
    if not rows:
        raise SystemExit("no Phase 15A raw cell files found")
    fields = list(rows[0].keys())
    write_csv(args.raw_output, rows, fields)
    write_csv(args.summary_output, summarize(rows), SUMMARY_FIELDS)
    print(f"phase15a_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
