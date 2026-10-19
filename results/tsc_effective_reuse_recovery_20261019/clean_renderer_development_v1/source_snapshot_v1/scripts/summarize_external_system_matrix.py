#!/usr/bin/env python3
"""Build the paired vLLM/SGLang B1-B4 external system matrix."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
    "model", "cell", "runtime", "prompt_layout", "fresh_process_repeats",
    "mean_ttft_ms", "mean_p95_ttft_ms", "mean_tpot_ms",
    "mean_prompt_tokens", "mean_new_prefill_tokens", "mean_prefix_hit_tokens",
    "prefill_counter_scope", "total_observed_new_prefill_tokens",
    "total_observed_prefix_hit_tokens", "peak_kv_usage_fraction",
    "peak_kv_token_slots",
    "mean_wall_slo_goodput", "mean_task_score", "completion_rate",
    "peak_kv_blocks", "claim_boundary",
]


def mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) not in {None, ""}]
    return statistics.fmean(values) if values else 0.0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)


def parse_sglang_log(path: Path) -> dict[str, float]:
    text = path.read_text(encoding="utf-8", errors="replace")
    cached = [int(value) for value in re.findall(r"#cached-token: (\d+)", text)]
    new = [int(value) for value in re.findall(r"#new-token: (\d+)", text)]
    usage = [float(value) for value in re.findall(r"token usage: ([0-9.]+)", text)]
    pool = [int(value) for value in re.findall(r"KV Cache is allocated\. #tokens: (\d+)", text)]
    peak_usage = max(usage, default=0.0)
    pool_tokens = max(pool, default=0)
    return {
        "total_cached_tokens": float(sum(cached)),
        "total_new_prefill_tokens": float(sum(new)),
        "peak_kv_usage_fraction": peak_usage,
        "peak_kv_token_slots": peak_usage * pool_tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-summary", type=Path, required=True)
    parser.add_argument("--external-dir", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    log_dir = args.log_dir or args.external_dir.parents[1] / "logs" / "external_baseline"
    submission = json.loads(args.submission_summary.read_text(encoding="utf-8"))
    matrix: list[dict[str, Any]] = []
    vllm_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in submission["cells"]:
        vllm_groups[(row["model"], row["policy"])].append(row)
    for model in ("qwen", "mistral"):
        for policy, cell, layout in (
            ("raw-order", "B1", "raw-order"),
            ("contractkv-full", "B3", "verified-compiled"),
        ):
            rows = vllm_groups[(model, policy)]
            matrix.append({
                "model": model, "cell": cell, "runtime": "vLLM-0.10.2-APC",
                "prompt_layout": layout, "fresh_process_repeats": len(rows),
                "mean_ttft_ms": mean(rows, "mean_ttft_ms"),
                "mean_p95_ttft_ms": mean(rows, "p95_ttft_ms"),
                "mean_tpot_ms": mean(rows, "mean_tpot_ms"),
                "mean_prompt_tokens": mean(rows, "mean_prompt_tokens"),
                "mean_new_prefill_tokens": mean(rows, "mean_new_prefill_tokens"),
                "mean_prefix_hit_tokens": mean(rows, "mean_prefix_hit_tokens"),
                "prefill_counter_scope": "future_requests_only",
                "total_observed_new_prefill_tokens": sum(float(row["mean_new_prefill_tokens"]) * float(row["future_requests"]) for row in rows),
                "total_observed_prefix_hit_tokens": sum(float(row["mean_prefix_hit_tokens"]) * float(row["future_requests"]) for row in rows),
                "peak_kv_usage_fraction": "unavailable_from_vllm_scheduler_probe",
                "peak_kv_token_slots": "unavailable_from_vllm_scheduler_probe",
                "mean_wall_slo_goodput": mean(rows, "slo_compliant_req_per_sec"),
                "mean_task_score": mean(rows, "mean_task_score"),
                "completion_rate": mean(rows, "completion_rate"),
                "peak_kv_blocks": max((float(row.get("peak_used_kv_blocks") or 0)
                                        for row in rows), default=0.0),
                "claim_boundary": "B3 includes scoped online verification and PSTP; B1 is native raw-order APC.",
            })

    external_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in args.external_dir.glob("sglang-*_summary.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        row.update(parse_sglang_log(log_dir / f"{row['backend']}.log"))
        parts = row["backend"].split("-")
        model = parts[1]
        external_groups[(model, row["policy"])].append(row)
    for model in ("qwen", "mistral"):
        for policy, cell, layout in (
            ("raw-order", "B2", "raw-order"),
            ("offline-safe-compiled", "B4", "offline-frozen-safe-compiled"),
        ):
            rows = external_groups[(model, policy)]
            if len(rows) != 3:
                raise ValueError(f"expected 3 SGLang repeats for {(model, policy)}, got {len(rows)}")
            matrix.append({
                "model": model, "cell": cell, "runtime": "SGLang-0.4.9-RadixAttention",
                "prompt_layout": layout, "fresh_process_repeats": len(rows),
                "mean_ttft_ms": mean(rows, "mean_ttft_ms"),
                "mean_p95_ttft_ms": mean(rows, "p95_ttft_ms"),
                "mean_tpot_ms": mean(rows, "mean_tpot_ms"),
                "mean_prompt_tokens": mean(rows, "mean_prompt_tokens"),
                "mean_new_prefill_tokens": "unavailable",
                "mean_prefix_hit_tokens": mean(rows, "total_cached_tokens") / max(mean(rows, "sessions") * 10, 1.0),
                "prefill_counter_scope": "server_log_all_requests_including_turn0_warmup",
                "total_observed_new_prefill_tokens": mean(rows, "total_new_prefill_tokens"),
                "total_observed_prefix_hit_tokens": mean(rows, "total_cached_tokens"),
                "peak_kv_usage_fraction": max(float(row["peak_kv_usage_fraction"]) for row in rows),
                "peak_kv_token_slots": max(float(row["peak_kv_token_slots"]) for row in rows),
                "mean_wall_slo_goodput": mean(rows, "slo_compliant_req_per_sec"),
                "mean_task_score": mean(rows, "mean_task_score"),
                "completion_rate": mean(rows, "completion_rate"),
                "peak_kv_blocks": "unavailable_without_backend_block_metric",
                "claim_boundary": rows[0]["claim_boundary"],
            })
    by_key = {(row["model"], row["cell"]): row for row in matrix}
    comparisons = []
    for model in ("qwen", "mistral"):
        b2, b4 = by_key[(model, "B2")], by_key[(model, "B4")]
        comparisons.append({
            "model": model,
            "b4_mean_ttft_reduction_vs_b2": (
                float(b2["mean_ttft_ms"]) - float(b4["mean_ttft_ms"]))
                / max(float(b2["mean_ttft_ms"]), 1e-9),
            "b4_p95_ttft_reduction_vs_b2": (
                float(b2["mean_p95_ttft_ms"]) - float(b4["mean_p95_ttft_ms"]))
                / max(float(b2["mean_p95_ttft_ms"]), 1e-9),
            "b4_task_score_delta_vs_b2": (
                float(b4["mean_task_score"]) - float(b2["mean_task_score"])),
        })
    write_csv(args.csv_output, matrix)
    payload = {
        "status": "complete", "matrix": matrix, "comparisons": comparisons,
        "claim_boundary": "B4 is offline frozen layout portability on SGLang, not online ContractKV; backend-hidden block metrics are unavailable, not inferred.",
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
