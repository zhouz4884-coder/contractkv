#!/usr/bin/env python3
"""Build a request-level, five-repeat Llama SOTA comparison table."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))] if ordered else 0.0


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def request_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("session_id", "")), int(row.get("turn_id", -1))


def score_rows(rows: list[dict[str, Any]], answers: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        if row.get("row_type") != "future" or not row.get("success"):
            continue
        if "output_text" not in row and row.get("task_score") not in (None, ""):
            row["_frozen_task_score"] = number(row["task_score"])
            row["_frozen_task_metric"] = row.get("task_metric", "runtime_frozen_scorer")
            row["_frozen_scoring_error"] = row.get("scoring_error", "")
            continue
        sample = answers.get(str(row.get("session_id", "")))
        if not sample:
            continue
        score, metric, error = standard_score(
            str(sample.get("dataset", row.get("dataset", ""))),
            str(sample.get("task", row.get("task", ""))),
            str(row.get("output_text", "")), sample.get("answer", ""))
        row["_frozen_task_score"] = score
        row["_frozen_task_metric"] = metric
        row["_frozen_scoring_error"] = error


def repeat_summary(path: Path, answers: dict[str, dict[str, Any]], slo_ms: float) -> tuple[dict[str, Any], dict[tuple[str, int], float]]:
    rows = [row for row in load(path) if row.get("row_type") == "future"]
    score_rows(rows, answers)
    success = [row for row in rows if row.get("success") is True]
    ttft = [number(row.get("ttft_ms")) for row in success]
    batches: dict[str, float] = {}
    for row in success:
        batch = str(row.get("batch_id") or f"request-{len(batches)}")
        wall = number(row.get("batch_wall_ms")) or number(row.get("latency_ms")) or number(row.get("total_latency_ms"))
        batches[batch] = max(batches.get(batch, 0.0), wall)
    wall_s = sum(batches.values()) / 1000.0
    scores = [number(row.get("_frozen_task_score")) for row in success if "_frozen_task_score" in row]
    prompt = [number(row.get("prompt_tokens")) for row in success if row.get("prompt_tokens") not in (None, "")]
    hits = [number(row.get("prefix_hit_tokens", row.get("cached_tokens"))) for row in success
            if row.get("prefix_hit_tokens", row.get("cached_tokens")) not in (None, "")]
    new_prefill = [number(row.get("new_prefill_tokens")) for row in success if row.get("new_prefill_tokens") not in (None, "")]
    if not new_prefill and prompt and len(hits) == len(prompt):
        new_prefill = [max(0.0, p - h) for p, h in zip(prompt, hits)]
    summary = {
        "future_requests": len(rows), "completed_requests": len(success),
        "completion_rate": len(success) / max(1, len(rows)),
        "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, .95), "p99_ttft_ms": percentile(ttft, .99),
        "mean_tpot_ms": statistics.fmean(number(row.get("tpot_ms")) for row in success) if success else 0.0,
        "mean_latency_ms": statistics.fmean(number(row.get("latency_ms", row.get("total_latency_ms"))) for row in success) if success else 0.0,
        "mean_prompt_tokens": statistics.fmean(prompt) if prompt else None,
        "mean_prefix_hit_tokens": statistics.fmean(hits) if hits else None,
        "mean_new_prefill_tokens": statistics.fmean(new_prefill) if new_prefill else None,
        "wall_clock_goodput_rps": len(success) / max(wall_s, 1e-9),
        "slo_compliant_goodput_rps": sum(value <= slo_ms for value in ttft) / max(wall_s, 1e-9),
        "mean_task_score": statistics.fmean(scores) if scores else None,
    }
    return summary, {request_key(row): number(row["_frozen_task_score"]) for row in success if "_frozen_task_score" in row}


def paths(root: Path, cell: str) -> list[Path]:
    if cell in {"vllm_apc", "contractkv"}:
        suffix = "raw" if cell == "vllm_apc" else "contract"
        return [*(root / "results/cross_model/llama_broad_generalization_r3" / f"repeat{i}" / f"r{i}-{suffix}.jsonl" for i in range(1, 4)),
                *(root / "results/external_baseline/llama_direct_v1" / f"llama-r{i}-{suffix}.jsonl" for i in range(4, 6))]
    if cell == "manual_oracle":
        return [root / "results/external_baseline/llama_direct_v1" / f"llama-r{i}-oracle.jsonl" for i in range(1, 6)]
    if cell in {"sglang_raw", "sglang_certified"}:
        suffix = "raw" if cell == "sglang_raw" else "certified"
        return [root / "results/external_baseline/llama_radix_certified" / f"llama-r{i}-{suffix}.jsonl" for i in range(1, 6)]
    suffix = {"lmcache": "lmcache", "cacheblend_raw": "blendraw", "cacheblend": "cacheblend"}[cell]
    return [root / "results/external_baseline/llama_lmcache_v1" / f"llama-r{i}-{suffix}.jsonl" for i in range(1, 6)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--slo-ms", type=float, default=1500.0)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    answers = {str(row["phase19b_session_id"]): row for row in load(args.sessions)}
    cells = ["vllm_apc", "manual_oracle", "contractkv", "sglang_raw", "sglang_certified",
             "lmcache", "cacheblend_raw", "cacheblend", "cacheslide"]
    labels = {
        "vllm_apc": "vLLM APC (raw order)",
        "manual_oracle": "Manual stable-layout oracle (offline upper bound)",
        "contractkv": "ContractKV", "sglang_raw": "SGLang RadixAttention (raw order)",
        "sglang_certified": "SGLang RadixAttention + frozen certified layout",
        "lmcache": "LMCache local-CPU connector", "cacheblend_raw": "LMCache matched separator baseline",
        "cacheblend": "LMCache CacheBlend (compatibility-shimmed lifecycle)",
        "cacheslide": "CacheSlide supplied artifact",
    }
    baseline_for = {"manual_oracle": "vllm_apc", "contractkv": "vllm_apc", "sglang_certified": "sglang_raw", "cacheblend": "cacheblend_raw"}
    summaries: dict[str, dict[str, Any]] = {}; score_maps: dict[str, list[dict[tuple[str, int], float]]] = {}
    for cell in cells:
        if cell == "cacheslide":
            audit_path = args.root / "results/external_baseline/artifact_audit/cacheslide_local_smoke_v0.json"
            llama_smoke_path = args.root / "results/external_baseline/artifact_audit/cacheslide_llama_smoke_v1.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
            llama_smoke = (json.loads(llama_smoke_path.read_text(encoding="utf-8"))
                           if llama_smoke_path.exists() else {})
            executed = llama_smoke.get("status") == "success"
            summaries[cell] = {
                "cell": cell, "label": labels[cell], "status": "external_artifact_blocked",
                "runtime": "CacheBlend vLLM fork 0.4.1 with exact Llama-3 RoPE compatibility backport",
                "entrypoint": llama_smoke.get("artifact", audit.get("entrypoint", "")),
                "artifact_path_executed": executed,
                "model_loaded": bool(llama_smoke.get("model_loaded")),
                "cache_fuse_metadata_present": bool(llama_smoke.get("cache_fuse_metadata_present")),
                "hack_kv_layers": llama_smoke.get("hack_kv_layers", 0),
                "diagnostic_cached_ttft_ms": llama_smoke.get("cached_ttft_ms"),
                "diagnostic_normal_ttft_ms": llama_smoke.get("normal_ttft_ms"),
                "diagnostic_quality_match": llama_smoke.get("quality_match"),
                "error_type": "common_protocol_unsupported" if executed else audit.get("error_type", "artifact_unavailable"),
                "error_message": (
                    "The supplied CacheSlide path executes, but its process-global old_kvs/cache_fuse_metadata "
                    "state is not request-isolated for concurrency=2, and the supplied Mistral-format entrypoint "
                    "does not preserve Llama-3.1 output equivalence. It is therefore excluded from the common "
                    "5x450-request service matrix rather than assigned a proxy number."
                    if executed else audit.get("error_message", "The supplied artifact did not expose its required vLLM hooks.")
                ),
            }
            continue
        cell_paths = paths(args.root, cell)
        missing = [str(path) for path in cell_paths if not path.exists()]
        if missing:
            summaries[cell] = {"cell": cell, "label": labels[cell], "status": "missing", "missing": missing}
            continue
        repeats = [repeat_summary(path, answers, args.slo_ms) for path in cell_paths]
        invalid = [
            {"path": str(path), "future_requests": repeat[0]["future_requests"],
             "completed_requests": repeat[0]["completed_requests"]}
            for path, repeat in zip(cell_paths, repeats)
            if repeat[0]["future_requests"] != 450 or repeat[0]["completed_requests"] != 450
        ]
        if invalid:
            summaries[cell] = {
                "cell": cell, "label": labels[cell], "status": "invalid_runtime",
                "invalid_repeats": invalid,
            }
            continue
        numeric = [key for key, value in repeats[0][0].items() if isinstance(value, (int, float)) and key not in {"future_requests", "completed_requests"}]
        row: dict[str, Any] = {"cell": cell, "label": labels[cell], "status": "complete", "fresh_process_repeats": len(repeats),
                               "future_requests_per_repeat": repeats[0][0]["future_requests"],
                               "completed_requests_per_repeat": repeats[0][0]["completed_requests"]}
        for key in numeric:
            values = [repeat[0][key] for repeat in repeats if repeat[0][key] is not None]
            row[key] = statistics.fmean(values) if values else None
        summaries[cell] = row; score_maps[cell] = [repeat[1] for repeat in repeats]
    for cell, baseline in baseline_for.items():
        if cell not in score_maps or baseline not in score_maps:
            continue
        candidate_summary = summaries[cell]
        baseline_summary = summaries[baseline]
        candidate_summary["mean_ttft_reduction_vs_matched_baseline"] = (
            1.0 - number(candidate_summary["mean_ttft_ms"]) /
            max(number(baseline_summary["mean_ttft_ms"]), 1e-12)
        )
        candidate_summary["slo_goodput_gain_vs_matched_baseline"] = (
            number(candidate_summary["slo_compliant_goodput_rps"]) /
            max(number(baseline_summary["slo_compliant_goodput_rps"]), 1e-12)
        )
        deltas = []
        delta_rows = []
        for candidate, raw in zip(score_maps[cell], score_maps[baseline]):
            for key in candidate.keys() & raw.keys():
                delta = candidate[key] - raw[key]
                deltas.append(delta)
                delta_rows.append({"session_id": key[0], "turn_id": key[1],
                                   "baseline_score": raw[key], "candidate_score": candidate[key],
                                   "delta": delta})
        summaries[cell]["paired_quality_requests"] = len(deltas)
        summaries[cell]["mean_task_score_delta_vs_matched_baseline"] = statistics.fmean(deltas) if deltas else None
        summaries[cell]["quality_drop_gt_0_03_rate"] = sum(delta < -.03 for delta in deltas) / max(1, len(deltas))
        summaries[cell]["quality_drop_gt_0_03_examples"] = [
            row for row in sorted(delta_rows, key=lambda item: item["delta"]) if row["delta"] < -.03
        ][:10]
    lmcache_accounting_path = (
        args.root / "results/external_baseline/llama_lmcache_v1/runtime_accounting_v1.json"
    )
    if lmcache_accounting_path.exists():
        accounting = json.loads(lmcache_accounting_path.read_text(encoding="utf-8"))
        by_mode = {row["mode"]: row for row in accounting.get("summaries", [])}
        for cell, mode in (("lmcache", "lmcache"), ("cacheblend_raw", "blendraw"),
                           ("cacheblend", "cacheblend")):
            if summaries.get(cell, {}).get("status") != "complete" or mode not in by_mode:
                continue
            runtime = by_mode[mode]
            summaries[cell]["connector_events"] = runtime["events"]
            summaries[cell]["mean_prefix_hit_tokens"] = runtime["mean_lmcache_hit_tokens"]
            summaries[cell]["mean_new_prefill_tokens"] = runtime["mean_new_prefill_tokens"]
            summaries[cell]["connector_hit_fraction"] = runtime["mean_hit_fraction"]
            summaries[cell]["positive_hit_event_rate"] = runtime["positive_hit_event_rate"]
    payload = {
        "schema_version": "contractkv.llama-sota-matrix.v1", "model": "Llama-3.1-8B-Instruct",
        "fresh_process_repeats": 5, "future_requests_per_repeat": 450, "slo_ttft_ms": args.slo_ms,
        "cells": [summaries[cell] for cell in cells],
        "claim_boundary": "Every complete row is a fresh real-runtime replay. The SGLang compiled row is an offline portability diagnostic; CacheSlide is reported separately when its supplied artifact cannot satisfy the frozen common protocol.",
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fields = sorted({key for row in payload["cells"] for key in row if key != "missing"})
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in payload["cells"])
    print(json.dumps(payload, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
