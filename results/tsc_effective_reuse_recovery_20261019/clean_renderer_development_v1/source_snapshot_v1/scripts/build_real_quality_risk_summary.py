#!/usr/bin/env python3
"""Build Phase 10.2B real quality risk summary from real model outputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path
from typing import Any


RISK_FIELDS = [
    "dataset",
    "task",
    "condition",
    "num_successful_requests",
    "num_context_overflow",
    "mean_score",
    "baseline_mean_score",
    "mean_quality_drop",
    "risk_source",
    "notes",
]

OVERFLOW_FIELDS = [
    "dataset",
    "task",
    "sample_id",
    "condition",
    "max_context_tokens",
    "actual_input_tokens",
    "status",
    "error_type",
    "error_message",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def is_context_overflow(row: dict[str, Any]) -> bool:
    message = str(row.get("error_message", "")).lower()
    error_type = str(row.get("error_type", "")).lower()
    if error_type not in {"httperror", "badrequesterror"}:
        return False
    return "maximum context length" in message or "400" in message or "bad request" in message


def _extract_context_counts(message: str) -> tuple[int, int]:
    max_match = re.search(r"maximum context length is\s+(\d+)", message)
    actual_match = re.search(r"request has\s+(\d+)\s+input tokens", message)
    return (
        int(max_match.group(1)) if max_match else 0,
        int(actual_match.group(1)) if actual_match else 0,
    )


def context_overflow_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if not is_context_overflow(row):
            continue
        max_tokens, actual_tokens = _extract_context_counts(str(row.get("error_message", "")))
        out.append(
            {
                "dataset": row.get("dataset", ""),
                "task": row.get("task", ""),
                "sample_id": row.get("sample_id", ""),
                "condition": row.get("condition", ""),
                "max_context_tokens": max_tokens,
                "actual_input_tokens": actual_tokens,
                "status": "capacity_failure",
                "error_type": row.get("error_type", ""),
                "error_message": row.get("error_message", ""),
            }
        )
    return out


def _note(dataset: str, task: str, condition: str) -> str:
    if dataset == "RepoBench" and condition == "boundary_repair":
        return "scoring_artifact_candidate_boundary_repair_improves_similarity"
    if dataset == "LongBench" and task == "narrativeqa":
        return "contains_32k_safe_subset_only_for_successful_requests"
    return ""


def aggregate_risk_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    successful = [row for row in rows if row.get("error_type") == "none"]
    overflows = context_overflow_rows(rows)
    overflow_counts: dict[tuple[str, str, str], int] = {}
    for row in overflows:
        key = (row["dataset"], row["task"], row["condition"])
        overflow_counts[key] = overflow_counts.get(key, 0) + 1

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in successful:
        groups.setdefault((row["dataset"], row["task"], row["condition"]), []).append(row)

    baseline: dict[tuple[str, str], float] = {}
    for (dataset, task, condition), group in groups.items():
        if condition == "full_context_baseline":
            baseline[(dataset, task)] = statistics.mean(float(row["score"]) for row in group)

    all_keys = sorted(set(groups) | set(overflow_counts))
    out = []
    for dataset, task, condition in all_keys:
        group = groups.get((dataset, task, condition), [])
        if group:
            mean_score = statistics.mean(float(row["score"]) for row in group)
        else:
            mean_score = 0.0
        base = baseline.get((dataset, task), mean_score)
        out.append(
            {
                "dataset": dataset,
                "task": task,
                "condition": condition,
                "num_successful_requests": len(group),
                "num_context_overflow": overflow_counts.get((dataset, task, condition), 0),
                "mean_score": round(mean_score, 6),
                "baseline_mean_score": round(base, 6),
                "mean_quality_drop": round(max(0.0, base - mean_score), 6),
                "risk_source": "real_qwen3_8b_output_successful_requests_only",
                "notes": _note(dataset, task, condition),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, default=Path("results/hard_systems/real_quality_outputs_qwen3_8b_v0.jsonl"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv"))
    parser.add_argument("--overflow-cases", type=Path, default=Path("results/hard_systems/context_overflow_cases_qwen3_8b_v0.csv"))
    args = parser.parse_args()
    rows = load_jsonl(args.outputs)
    write_csv(args.risk_summary, aggregate_risk_summary(rows), RISK_FIELDS)
    write_csv(args.overflow_cases, context_overflow_rows(rows), OVERFLOW_FIELDS)
    print(f"risk_rows={len(aggregate_risk_summary(rows))}")
    print(f"overflow_rows={len(context_overflow_rows(rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
