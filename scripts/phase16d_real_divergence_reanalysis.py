#!/usr/bin/env python3
"""Recompute Phase 16D false-safe risk from real raw/candidate outputs."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase16d_drift_budget_lifecycle import wilson_upper


FIELDS = [
    "scope", "covered_future_turns", "raw_candidate_divergences",
    "conditional_divergence_rate", "conditional_divergence_wilson95_upper",
    "renewed_or_raw_turns_excluded", "claim_boundary",
]


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def reanalyze(rows: list[dict[str, str]]) -> dict[str, Any]:
    future = [row for row in rows if int(row["turn_id"]) > 0]
    covered = [
        row for row in future
        if as_bool(row.get("certificate_active"))
        and row.get("deployed_policy") == "contractkv-caposc"
    ]
    divergences = sum(not as_bool(row.get("output_contract_match")) for row in covered)
    return {
        "scope": "phase15d_real_qwen3_8b_covered_future_turns",
        "covered_future_turns": len(covered),
        "raw_candidate_divergences": divergences,
        "conditional_divergence_rate": round(divergences / max(len(covered), 1), 9),
        "conditional_divergence_wilson95_upper": round(wilson_upper(divergences, len(covered)), 9),
        "renewed_or_raw_turns_excluded": len(future) - len(covered),
        "claim_boundary": "Real Phase 15D raw-vs-candidate output contracts; conditional on CAPOSC-covered turns, task-sanity rather than full official scoring.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/end_to_end/phase15d_task_bearing_raw_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/phase16d_real_divergence_reanalysis_v0.csv"))
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as handle:
        result = reanalyze(list(csv.DictReader(handle)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(result)


if __name__ == "__main__":
    main()
