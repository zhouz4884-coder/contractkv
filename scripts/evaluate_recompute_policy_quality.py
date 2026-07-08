#!/usr/bin/env python3
"""Evaluate real output quality for Phase 10.5 recompute policies."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = [
    "policy",
    "dataset",
    "num_samples",
    "successful_samples",
    "mean_score",
    "baseline_mean_score",
    "quality_drop",
    "quality_close_to_default",
    "error_count",
]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def compute_policy_quality_summary(rows: list[dict[str, Any]], close_threshold: float = 0.03) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["policy"]), str(row.get("dataset", ""))), []).append(row)

    baseline_by_dataset: dict[str, float] = {}
    for (policy, dataset), items in grouped.items():
        if policy != "vllm-default":
            continue
        ok_scores = [_float(item.get("score")) for item in items if str(item.get("error_type", "none")) == "none"]
        if ok_scores:
            baseline_by_dataset[dataset] = statistics.mean(ok_scores)

    summaries = []
    for (policy, dataset), items in sorted(grouped.items()):
        ok_scores = [_float(item.get("score")) for item in items if str(item.get("error_type", "none")) == "none"]
        mean_score = statistics.mean(ok_scores) if ok_scores else 0.0
        baseline = baseline_by_dataset.get(dataset, mean_score)
        quality_drop = max(0.0, baseline - mean_score)
        summaries.append({
            "policy": policy,
            "dataset": dataset,
            "num_samples": len(items),
            "successful_samples": len(ok_scores),
            "mean_score": round(mean_score, 6),
            "baseline_mean_score": round(baseline, 6),
            "quality_drop": round(quality_drop, 6),
            "quality_close_to_default": quality_drop <= close_threshold,
            "error_count": len(items) - len(ok_scores),
        })
    return summaries


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = SUMMARY_FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-input", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_quality_eval_v0.csv"))
    parser.add_argument("--close-threshold", type=float, default=0.03)
    args = parser.parse_args()
    summary = compute_policy_quality_summary(read_csv(args.raw_input), args.close_threshold)
    write_csv(args.summary_output, summary)
    print(f"quality_summary_rows={len(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
