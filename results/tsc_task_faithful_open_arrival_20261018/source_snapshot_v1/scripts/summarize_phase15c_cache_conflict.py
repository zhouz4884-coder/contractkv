#!/usr/bin/env python3
"""Aggregate fresh-process Phase 15C conflict summaries."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

FIELDS = [
    "policy", "seeds", "cells", "turns", "completion_rate", "quality_sanity_rate",
    "mean_ttft_ms", "p95_ttft_ms", "mean_prefix_hit_tokens", "mean_new_prefill_tokens",
    "mean_used_block_high_water", "physical_feedback_rate", "within_one_block_rate",
    "claim_boundary",
]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load(cell_dir: Path) -> list[dict[str, str]]:
    rows = []
    for path in sorted(cell_dir.glob("*_summary.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def summarize(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["policy"]].append(row)
    output = []
    for policy, group in sorted(groups.items()):
        output.append({
            "policy": policy, "seeds": ",".join(sorted(row["seed"] for row in group)), "cells": len(group),
            "turns": sum(int(number(row["turns"])) for row in group),
            "completion_rate": statistics.mean(number(row["completion_rate"]) for row in group),
            "quality_sanity_rate": statistics.mean(number(row["quality_sanity_rate"]) for row in group),
            "mean_ttft_ms": statistics.mean(number(row["mean_ttft_ms"]) for row in group),
            "p95_ttft_ms": max(number(row["p95_ttft_ms"]) for row in group),
            "mean_prefix_hit_tokens": statistics.mean(number(row["mean_prefix_hit_tokens"]) for row in group),
            "mean_new_prefill_tokens": statistics.mean(number(row["mean_new_prefill_tokens"]) for row in group),
            "mean_used_block_high_water": statistics.mean(number(row["used_block_high_water"]) for row in group),
            "physical_feedback_rate": statistics.mean(number(row["physical_feedback_rate"]) for row in group),
            "within_one_block_rate": statistics.mean(number(row["within_one_block_rate"]) for row in group),
            "claim_boundary": "Real vLLM conflict across three fresh-process seeds; prior-request physical feedback, not general candidate RPC.",
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = summarize(load(args.cell_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    print(f"phase15c_policies={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
