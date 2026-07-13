#!/usr/bin/env python3
"""Summarize paired fresh-process submission repeats and bootstrap CIs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))] if ordered else 0.0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def summarize_cell(model: str, repeat: int, policy: str, path: Path, slo_ms: float) -> dict[str, Any]:
    rows = load(path)
    future = [row for row in rows if row.get("row_type") == "future"]
    successful = [row for row in future if row.get("success") is True]
    canary = [row for row in rows if row.get("row_type") == "canary"]
    batches: dict[str, float] = {}
    for row in successful:
        key = str(row.get("batch_id") or row.get("request_id"))
        batches[key] = max(batches.get(key, 0.0), float(row.get("batch_wall_ms", 0) or 0))
    wall_s = sum(batches.values()) / 1000.0
    ttft = [float(row["ttft_ms"]) for row in successful]
    tpot = [float(row["tpot_ms"]) for row in successful]
    prefill = [float(row["new_prefill_tokens"]) for row in successful if row.get("new_prefill_tokens") not in {None, ""}]
    prefix = [float(row["prefix_hit_tokens"]) for row in successful if row.get("prefix_hit_tokens") not in {None, ""}]
    prompt = [float(row["prompt_tokens"]) for row in successful if row.get("prompt_tokens") not in {None, ""}]
    task_scores = [float(row["task_score"]) for row in successful if row.get("task_score") not in {None, ""}]
    metrics_path = path.with_name(path.stem + "_metrics.jsonl")
    metric_rows = load(metrics_path) if metrics_path.exists() else []
    initial_metrics = [row for row in metric_rows
                       if row.get("event") == "prefix_cache_request_observation"
                       and row.get("initial_prefill_observation") is True]
    certified = [row for row in successful if row.get("certificate_issued") is True]
    verifier_total = sum(float(row.get("unhidden_verifier_ms", 0) or 0) for row in canary)
    verifier_per_request = verifier_total / max(1, len(certified))
    scope_invalid_rows = [row for row in successful
                          if row.get("certificate_scope_valid") is False]
    scope_invalid_fallback = sum(
        str(row.get("effective_policy", "raw-order")) == "raw-order"
        for row in scope_invalid_rows)
    scope_invalid_admitted = len(scope_invalid_rows) - scope_invalid_fallback
    return {
        "model": model, "repeat": repeat, "policy": policy,
        "source_path": str(path), "future_requests": len(future),
        "completed_requests": len(successful),
        "completion_rate": len(successful) / max(1, len(future)),
        "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, .95),
        "mean_tpot_ms": statistics.fmean(tpot) if tpot else 0.0,
        "p95_tpot_ms": percentile(tpot, .95),
        "mean_new_prefill_tokens": statistics.fmean(prefill) if prefill else 0.0,
        "mean_prefix_hit_tokens": statistics.fmean(prefix) if prefix else 0.0,
        "mean_prompt_tokens": statistics.fmean(prompt) if prompt else 0.0,
        "mean_task_score": statistics.fmean(task_scores) if task_scores else 0.0,
        "peak_used_kv_blocks": max((float(row.get("used_gpu_blocks") or 0)
                                    for row in initial_metrics), default=0.0),
        "minimum_free_kv_blocks": min((float(row.get("free_gpu_blocks") or 0)
                                       for row in initial_metrics), default=0.0),
        "unhidden_verifier_ms_per_request": verifier_per_request,
        "net_mean_ttft_ms": (statistics.fmean(ttft) if ttft else 0.0) + verifier_per_request,
        "slo_ms": slo_ms,
        "slo_compliant_requests": sum(value <= slo_ms for value in ttft),
        "slo_compliant_req_per_sec": sum(value <= slo_ms for value in ttft) / max(wall_s, 1e-9),
        "certificate_scope_invalid_fallback_requests": scope_invalid_fallback,
        "certificate_scope_invalid_admitted_requests": scope_invalid_admitted,
        "wall_time_s": wall_s,
    }


def bootstrap_ci(values: list[float], seed: int = 2101, samples: int = 10000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(samples)]
    return percentile(means, .025), percentile(means, .975)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", action="append", required=True, help="model,repeat,policy,path")
    parser.add_argument("--slo-ms", type=float, default=1500)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--paired-output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    cells = []
    for spec in args.cell:
        model, repeat, policy, path = spec.split(",", 3)
        cells.append(summarize_cell(model, int(repeat), policy, Path(path), args.slo_ms))
    by_key = {(row["model"], row["repeat"], row["policy"]): row for row in cells}
    pairs = []
    for model in sorted({row["model"] for row in cells}):
        for repeat in sorted({row["repeat"] for row in cells if row["model"] == model}):
            raw = by_key[(model, repeat, "raw-order")]
            contract = by_key[(model, repeat, "contractkv-full")]
            pairs.append({
                "model": model, "repeat": repeat,
                "raw_mean_ttft_ms": raw["mean_ttft_ms"],
                "contract_mean_ttft_ms": contract["mean_ttft_ms"],
                "contract_net_mean_ttft_ms": contract["net_mean_ttft_ms"],
                "net_mean_ttft_reduction": (raw["mean_ttft_ms"] - contract["net_mean_ttft_ms"]) / max(raw["mean_ttft_ms"], 1e-9),
                "raw_p95_ttft_ms": raw["p95_ttft_ms"],
                "contract_p95_ttft_ms": contract["p95_ttft_ms"],
                "p95_ttft_reduction": (raw["p95_ttft_ms"] - contract["p95_ttft_ms"]) / max(raw["p95_ttft_ms"], 1e-9),
                "raw_new_prefill_tokens": raw["mean_new_prefill_tokens"],
                "contract_new_prefill_tokens": contract["mean_new_prefill_tokens"],
                "new_prefill_reduction": (raw["mean_new_prefill_tokens"] - contract["mean_new_prefill_tokens"]) / max(raw["mean_new_prefill_tokens"], 1e-9),
                "raw_slo_req_per_sec": raw["slo_compliant_req_per_sec"],
                "contract_slo_req_per_sec": contract["slo_compliant_req_per_sec"],
                "slo_goodput_gain": (contract["slo_compliant_req_per_sec"] - raw["slo_compliant_req_per_sec"]) / max(raw["slo_compliant_req_per_sec"], 1e-9),
                "raw_completion_rate": raw["completion_rate"],
                "contract_completion_rate": contract["completion_rate"],
                "scope_invalid_fallback_requests": contract["certificate_scope_invalid_fallback_requests"],
                "scope_invalid_admitted_requests": contract["certificate_scope_invalid_admitted_requests"],
            })
    aggregates = []
    for model in sorted({row["model"] for row in pairs}):
        group = [row for row in pairs if row["model"] == model]
        record: dict[str, Any] = {"model": model, "fresh_process_repeats": len(group)}
        for key in ("net_mean_ttft_reduction", "p95_ttft_reduction", "new_prefill_reduction", "slo_goodput_gain"):
            values = [float(row[key]) for row in group]
            low, high = bootstrap_ci(values)
            record[f"mean_{key}"] = statistics.fmean(values)
            record[f"min_{key}"] = min(values)
            record[f"max_{key}"] = max(values)
            record[f"bootstrap95_low_{key}"] = low
            record[f"bootstrap95_high_{key}"] = high
        record["all_complete"] = all(row["raw_completion_rate"] == 1.0 and row["contract_completion_rate"] == 1.0 for row in group)
        record["scope_invalid_fallback_requests"] = sum(
            int(row["scope_invalid_fallback_requests"]) for row in group)
        record["scope_invalid_admitted_requests"] = sum(
            int(row["scope_invalid_admitted_requests"]) for row in group)
        aggregates.append(record)
    write_csv(args.raw_output, cells); write_csv(args.paired_output, pairs); write_csv(args.aggregate_output, aggregates)
    args.json_output.write_text(json.dumps({"cells": cells, "pairs": pairs, "aggregate": aggregates}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"paired": pairs, "aggregate": aggregates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
