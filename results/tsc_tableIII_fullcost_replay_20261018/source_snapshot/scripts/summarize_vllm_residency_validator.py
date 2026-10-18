#!/usr/bin/env python3
"""Summarize Physical Prefix Residency Validator events."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


FIELDS = [
    "request_id", "cache_epoch", "expected_hit_blocks", "actual_hit_blocks",
    "mispredicted_block_count", "within_one_block", "residency_misprediction",
    "probe_ms", "prediction_ms", "validation_ms", "total_probe_overhead_ms",
]

SUMMARY_FIELDS = [
    "requests", "within_one_block_requests", "prefix_residency_prediction_accuracy",
    "residency_mispredictions", "mean_probe_overhead_ms", "p95_probe_overhead_ms",
    "gate_prediction_accuracy", "gate_probe_overhead", "phase14rc_gate_open",
    "claim_boundary",
]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def load_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    for event in events:
        if event.get("event") != "prefix_residency_validation":
            continue
        difference = abs(int(event.get("expected_hit_blocks") or 0) - int(event.get("actual_hit_blocks") or 0))
        overhead = sum(float(event.get(field) or 0.0) for field in ("probe_ms", "prediction_ms", "validation_ms"))
        rows.append({
            "request_id": event.get("request_id", ""),
            "cache_epoch": event.get("cache_epoch", 0),
            "expected_hit_blocks": event.get("expected_hit_blocks", 0),
            "actual_hit_blocks": event.get("actual_hit_blocks", 0),
            "mispredicted_block_count": difference,
            "within_one_block": difference <= 1,
            "residency_misprediction": difference > 1,
            "probe_ms": event.get("probe_ms", 0.0),
            "prediction_ms": event.get("prediction_ms", 0.0),
            "validation_ms": event.get("validation_ms", 0.0),
            "total_probe_overhead_ms": overhead,
        })
    overheads = [float(row["total_probe_overhead_ms"]) for row in rows]
    within = sum(bool(row["within_one_block"]) for row in rows)
    accuracy = within / len(rows) if rows else 0.0
    p95 = percentile(overheads, .95)
    summary = [{
        "requests": len(rows),
        "within_one_block_requests": within,
        "prefix_residency_prediction_accuracy": accuracy,
        "residency_mispredictions": len(rows) - within,
        "mean_probe_overhead_ms": sum(overheads) / len(overheads) if overheads else 0.0,
        "p95_probe_overhead_ms": p95,
        "gate_prediction_accuracy": accuracy >= .95,
        "gate_probe_overhead": p95 < .2,
        "phase14rc_gate_open": bool(rows) and accuracy >= .95 and p95 < .2,
        "claim_boundary": "Read-only vLLM V1 native block-hash prediction versus post-allocation request block table.",
    }]
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = summarize(load_events(args.events))
    write_csv(args.raw_output, rows, FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(json.dumps(summary[0], ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
