#!/usr/bin/env python3
"""Summarize the paired fresh SGLang Llama RadixAttention replay."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q + .999999)))] if ordered else 0.0


def read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(paths: list[Path], policy: str) -> dict[str, Any]:
    repeats = []
    for path in paths:
        rows = [row for row in read(path) if row.get("row_type") == "future"]
        success = [row for row in rows if row.get("success")]
        ttft = [float(row["ttft_ms"]) for row in success]
        latency = [float(row["latency_ms"]) for row in success]
        repeat = {
            "file": path.name, "future_requests": len(rows), "completed_requests": len(success),
            "completion_rate": len(success) / max(1, len(rows)),
            "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
            "p95_ttft_ms": percentile(ttft, .95),
            "p99_ttft_ms": percentile(ttft, .99),
            "mean_latency_ms": statistics.fmean(latency) if latency else 0.0,
            "mean_task_score": statistics.fmean(float(row["task_score"]) for row in success) if success else 0.0,
            "qualified_future_fraction": statistics.fmean(float(bool(row.get("qualified_family"))) for row in rows) if rows else 0.0,
        }
        repeats.append(repeat)
    return {
        "runtime": "SGLang-0.4.9.post6-RadixAttention", "policy": policy,
        "fresh_process_repeats": len(repeats), "repeats": repeats,
        "mean_ttft_ms": statistics.fmean(row["mean_ttft_ms"] for row in repeats),
        "mean_p95_ttft_ms": statistics.fmean(row["p95_ttft_ms"] for row in repeats),
        "mean_p99_ttft_ms": statistics.fmean(row["p99_ttft_ms"] for row in repeats),
        "mean_latency_ms": statistics.fmean(row["mean_latency_ms"] for row in repeats),
        "mean_task_score": statistics.fmean(row["mean_task_score"] for row in repeats),
        "mean_completion_rate": statistics.fmean(row["completion_rate"] for row in repeats),
        "mean_qualified_future_fraction": statistics.fmean(row["qualified_future_fraction"] for row in repeats),
    }


def paired_quality(raw_paths: list[Path], compiled_paths: list[Path]) -> dict[str, Any]:
    deltas: list[float] = []
    below_threshold = 0
    for raw_path, compiled_path in zip(raw_paths, compiled_paths):
        raw = {(row["session_id"], row["turn_id"]): row for row in read(raw_path)
               if row.get("row_type") == "future"}
        compiled = {(row["session_id"], row["turn_id"]): row for row in read(compiled_path)
                    if row.get("row_type") == "future"}
        for key in raw.keys() & compiled.keys():
            delta = float(compiled[key]["task_score"]) - float(raw[key]["task_score"])
            deltas.append(delta)
            below_threshold += int(delta < -0.03)
    return {
        "paired_requests": len(deltas),
        "mean_compiled_minus_raw_task_score": statistics.fmean(deltas) if deltas else 0.0,
        "requests_with_drop_gt_0_03": below_threshold,
        "drop_gt_0_03_rate": below_threshold / max(1, len(deltas)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--compiled-mode", choices=("frozen", "certified"), default="frozen")
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    raw = [args.directory / f"llama-r{repeat}-raw.jsonl" for repeat in (1, 2, 3)]
    compiled_paths = [args.directory / f"llama-r{repeat}-{args.compiled_mode}.jsonl" for repeat in (1, 2, 3)]
    missing = [str(path) for path in raw + compiled_paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing completed repeats: " + ", ".join(missing))
    baseline = summarize(raw, "raw-order")
    compiled = summarize(compiled_paths, "offline-vllm-certified-layout" if args.compiled_mode == "certified" else "offline-frozen-ladder")
    reduction = (baseline["mean_ttft_ms"] - compiled["mean_ttft_ms"]) / max(baseline["mean_ttft_ms"], 1e-9)
    payload = {
        "schema_version": "contractkv.external.llama-radix.v1",
        "cells": [baseline, compiled],
        "compiled_mean_ttft_reduction_vs_raw": reduction,
        "paired_quality": paired_quality(raw, compiled_paths),
        "claim_boundary": "SGLang consumes the frozen Llama layout map. This demonstrates layout portability, not online ContractKV verification or PSTP inside SGLang.",
    }
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "runtime", "policy", "fresh_process_repeats", "mean_ttft_ms", "mean_p95_ttft_ms", "mean_p99_ttft_ms",
            "mean_latency_ms", "mean_task_score", "mean_completion_rate", "mean_qualified_future_fraction"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row[field] for field in fields} for row in (baseline, compiled)])
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
