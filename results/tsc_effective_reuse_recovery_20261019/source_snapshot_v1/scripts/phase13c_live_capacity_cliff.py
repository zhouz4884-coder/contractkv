#!/usr/bin/env python3
"""Live heterogeneous pressure sweep for the Phase 13C RAR claim boundary."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase13b_fresh_policy_quality_replay import TASKS, _compile, _messages, build_case, load_jsonl
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger


POLICIES = ["contractkv-caposc-sspp", "contractkv-caposc-sspp-rar"]
RAW_FIELDS = [
    "policy", "concurrency", "dataset", "task", "sample_id", "request_id", "success", "capacity_failure",
    "error_type", "error_message", "ttft_ms", "tpot_ms", "total_latency_ms", "prompt_tokens", "output_tokens",
    "quality_score", "blocks_freed_planned", "rar_trigger_reason", "free_gpu_mem_before_gb", "free_gpu_mem_after_gb",
    "claim_boundary",
]
SUMMARY_FIELDS = [
    "policy", "concurrency", "attempted_requests", "completed_requests", "completion_rate", "capacity_failures",
    "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "slo_compliant_requests", "slo_compliant_req_per_sec",
    "rar_planned_rows", "total_blocks_freed_planned", "claim_boundary",
]


def _gpu_mem_gb() -> float:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=5
        )
        return round(float(output.splitlines()[0].strip()) / 1024.0, 6)
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return 0.0


def _capacity(result: dict[str, Any]) -> bool:
    if result.get("success"):
        return False
    value = f"{result.get('error_type', '')} {result.get('error_message', '')}".lower()
    return any(term in value for term in ("timeout", "oom", "capacity", "context", "400", "500"))


def _run_one(job: dict[str, Any], base_url: str, model: str, timeout: float, max_tokens: int) -> dict[str, Any]:
    before = _gpu_mem_gb()
    result = send_chat_stream(
        base_url, model, job["messages"], max_tokens, timeout,
        f"phase13c-cliff-{job['concurrency']}-{job['policy']}-{job['dataset']}-{job['task']}-{job['sample_id']}",
    )
    after = _gpu_mem_gb()
    return {
        "policy": job["policy"], "concurrency": job["concurrency"], "dataset": job["dataset"], "task": job["task"],
        "sample_id": job["sample_id"], "request_id": result.get("request_id", ""), "success": result.get("success", False),
        "capacity_failure": _capacity(result), "error_type": result.get("error_type", ""), "error_message": result.get("error_message", ""),
        "ttft_ms": result.get("ttft_ms", 0.0), "tpot_ms": result.get("tpot_ms", 0.0), "total_latency_ms": result.get("total_latency_ms", 0.0),
        "prompt_tokens": job["prompt_tokens"], "output_tokens": result.get("output_tokens", 0), "quality_score": result.get("quality_score", 0.0),
        "blocks_freed_planned": job["blocks_freed_planned"], "rar_trigger_reason": job["rar_trigger_reason"],
        "free_gpu_mem_before_gb": before, "free_gpu_mem_after_gb": after,
        "claim_boundary": "Live heterogeneous pressure row; RAR fields are planned unless joined with the separate vLLM actuator event log.",
    }


def _jobs(samples: list[dict[str, Any]], policy: str, concurrency: int, samples_per_task: int) -> list[dict[str, Any]]:
    selected = []
    for task in TASKS:
        selected.extend([item for item in samples if item.get("task") == task][:samples_per_task])
    jobs = []
    ledger = SegmentPrefixLedger()
    for sample in selected:
        case = build_case(sample, stable_word_limit=2600)
        compiled = _compile("contractkv-caposc", case, ledger)
        text = __import__("scripts.phase12f_real_vllm_caposc_replay", fromlist=["_ordered_text"])._ordered_text(compiled["topological_order"], case["segments"])
        suffix_tokens = max(0, sum(int(x.get("token_count") or 0) for x in case["segments"]) - int(compiled.get("estimated_lcp_tokens") or 0))
        blocks = max(1, (suffix_tokens + 15) // 16) if policy.endswith("rar") and concurrency >= 6 else 0
        jobs.append({
            "policy": policy, "concurrency": concurrency, "dataset": case["dataset"], "task": case["task"], "sample_id": case["sample_id"],
            "messages": _messages(case, text, policy), "prompt_tokens": sum(int(x.get("token_count") or 0) for x in case["segments"]),
            "quality_score": 0.0, "blocks_freed_planned": blocks, "rar_trigger_reason": "block_pressure" if blocks else "none",
        })
        ledger.update(case["trajectory_id"], 0, case["segments"], compiled["topological_order"], policy=policy)
    return jobs


def run(samples: list[dict[str, Any]], base_url: str, model: str, concurrencies: list[int], samples_per_task: int, timeout: float, max_tokens: int) -> list[dict[str, Any]]:
    rows = []
    for concurrency in concurrencies:
        for policy in POLICIES:
            jobs = _jobs(samples, policy, concurrency, samples_per_task)
            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(_run_one, job, base_url, model, timeout, max_tokens) for job in jobs]
                batch = [future.result() for future in concurrent.futures.as_completed(futures)]
            wall = max(time.perf_counter() - started, 1e-9)
            for row in batch:
                row["batch_wall_time_sec"] = wall
            rows.extend(batch)
    return rows


def summarize(rows: list[dict[str, Any]], slo_ms: float) -> list[dict[str, Any]]:
    groups = {}
    for row in rows:
        groups.setdefault((row["policy"], int(row["concurrency"])), []).append(row)
    output = []
    for (policy, concurrency), group in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        good = [row for row in group if str(row["success"]).lower() == "true"]
        ttft = [float(row["ttft_ms"]) for row in good if float(row["ttft_ms"]) > 0]
        tpot = [float(row["tpot_ms"]) for row in good if float(row["tpot_ms"]) > 0]
        compliant = [row for row in good if float(row["ttft_ms"]) <= slo_ms]
        wall = max(float(row.get("batch_wall_time_sec", 0.0)) for row in group) if group else 0.0
        output.append({
            "policy": policy, "concurrency": concurrency, "attempted_requests": len(group), "completed_requests": len(good),
            "completion_rate": round(len(good) / len(group), 6) if group else 0.0, "capacity_failures": sum(bool(row["capacity_failure"]) for row in group),
            "mean_ttft_ms": round(sum(ttft) / len(ttft), 6) if ttft else 0.0, "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_tpot_ms": round(sum(tpot) / len(tpot), 6) if tpot else 0.0, "slo_compliant_requests": len(compliant),
            "slo_compliant_req_per_sec": round(len(compliant) / wall, 6) if wall else 0.0,
            "rar_planned_rows": sum(int(row["blocks_freed_planned"]) > 0 for row in group),
            "total_blocks_freed_planned": sum(int(row["blocks_freed_planned"]) for row in group),
            "claim_boundary": "Live endpoint capacity-cliff sweep; planned RAR fields require actuator log join for hard-system attribution.",
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--concurrencies", default="2,4,6,8,10")
    parser.add_argument("--samples-per-task", type=int, default=3)
    parser.add_argument("--slo-ms", type=float, default=3000.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13c_live_capacity_cliff_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13c_live_capacity_cliff_summary_v0.csv"))
    args = parser.parse_args()
    rows = run(load_jsonl(args.samples), args.base_url, args.model, [int(x) for x in args.concurrencies.split(",")], args.samples_per_task, args.timeout, args.max_tokens)
    write_csv(args.raw_output, rows, RAW_FIELDS + ["batch_wall_time_sec"])
    write_csv(args.summary_output, summarize(rows, args.slo_ms), SUMMARY_FIELDS)
    print(f"capacity_rows={len(rows)} summary_rows={len(summarize(rows, args.slo_ms))}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
