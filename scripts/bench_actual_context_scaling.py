#!/usr/bin/env python3
"""Run actual-context streaming latency measurements against vLLM."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bench_openai_ttft_tpot import classify_error, current_commit, compute_tpot_ms


ACTUAL_CONTEXT_RAW_FIELDS = [
    "timestamp",
    "run_id",
    "model",
    "configured_max_model_len",
    "actual_prompt_tokens_after_chat_template",
    "target_tokens",
    "prompt_source",
    "prompt_entropy_type",
    "max_num_seqs",
    "temperature",
    "generation_max_tokens",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "peak_gpu_mem_gb",
    "vllm_kv_capacity",
    "startup_success",
    "runtime_success",
    "error_type",
    "error_message",
    "log_path",
    "gpu_monitor_path",
    "commit_hash",
]

ACTUAL_CONTEXT_SUMMARY_FIELDS = [
    "model",
    "configured_max_model_len",
    "target_tokens",
    "actual_prompt_tokens_after_chat_template",
    "prompt_source",
    "prompt_entropy_type",
    "max_num_seqs",
    "num_runs",
    "num_success",
    "avg_ttft_ms",
    "p50_ttft_ms",
    "p95_ttft_ms",
    "avg_tpot_ms",
    "p50_tpot_ms",
    "p95_tpot_ms",
    "avg_total_latency_ms",
    "peak_gpu_mem_gb",
    "error_types",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    idx = math.ceil((pct / 100.0) * len(ordered)) - 1
    return round(ordered[min(max(idx, 0), len(ordered) - 1)], 3)


def summarize_runs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in rows if row.get("error_type") == "none"]
    ttft = [float(row["ttft_ms"]) for row in ok if row.get("ttft_ms") not in ("", None)]
    tpot = [float(row["tpot_ms"]) for row in ok if row.get("tpot_ms") not in ("", None)]
    total = [float(row["total_latency_ms"]) for row in ok if row.get("total_latency_ms") not in ("", None)]
    peak = [float(row["peak_gpu_mem_gb"]) for row in rows if row.get("peak_gpu_mem_gb") not in ("", None)]
    return {
        "num_runs": len(rows),
        "num_success": len(ok),
        "avg_ttft_ms": round(sum(ttft) / len(ttft), 3) if ttft else "",
        "p50_ttft_ms": percentile(ttft, 50) if ttft else "",
        "p95_ttft_ms": percentile(ttft, 95) if ttft else "",
        "avg_tpot_ms": round(sum(tpot) / len(tpot), 3) if tpot else "",
        "p50_tpot_ms": percentile(tpot, 50) if tpot else "",
        "p95_tpot_ms": percentile(tpot, 95) if tpot else "",
        "avg_total_latency_ms": round(sum(total) / len(total), 3) if total else "",
        "peak_gpu_mem_gb": round(max(peak), 3) if peak else "",
        "error_types": ";".join(sorted(set(row.get("error_type", "") for row in rows))),
    }


def _iter_sse(response: Any):
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        yield json.loads(payload)


def stream_prompt(base_url: str, model: str, prompt: dict[str, Any], temperature: float, timeout: float) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": prompt["messages"],
        "max_tokens": int(prompt.get("generation_max_tokens", 128)),
        "temperature": temperature,
        "stream": True,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_token_time = None
    output_chunks = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for chunk in _iter_sse(response):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content") or ""
            if content and first_token_time is None:
                first_token_time = time.perf_counter()
            if content:
                output_chunks.append(content)
    ended = time.perf_counter()
    return {
        "ttft_ms": round((first_token_time - started) * 1000.0, 3) if first_token_time else "",
        "tpot_ms": compute_tpot_ms(first_token_time, ended, len(output_chunks)) or "",
        "total_latency_ms": round((ended - started) * 1000.0, 3),
        "completion_tokens": len(output_chunks),
        "runtime_success": bool(output_chunks),
        "error_type": "none" if output_chunks else "bad_output",
        "error_message": "",
    }


def start_gpu_monitor(path: Path, interval: float) -> subprocess.Popen | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = (
        "while true; do "
        "nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory "
        "--format=csv,noheader,nounits; "
        f"sleep {interval}; "
        "done"
    )
    handle = path.open("w", encoding="utf-8")
    handle.write("timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory\n")
    handle.flush()
    process = subprocess.Popen(["bash", "-lc", command], stdout=handle, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    process._contractkv_handle = handle  # type: ignore[attr-defined]
    return process


def stop_gpu_monitor(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=2)
    except Exception:
        process.kill()
    handle = getattr(process, "_contractkv_handle", None)
    if handle:
        handle.close()


def peak_gpu_mem_gb(path: Path) -> str:
    if not path.exists():
        return ""
    peak = 0.0
    with path.open("r", encoding="utf-8") as handle:
        next(handle, None)
        for line in handle:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 3:
                try:
                    peak = max(peak, float(parts[2]) / 1024.0)
                except ValueError:
                    pass
    return str(round(peak, 3)) if peak else ""


def append_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["target_tokens"], row["prompt_source"], row["configured_max_model_len"])].append(row)
    summary_rows = []
    for (_, _, _), group in groups.items():
        base = group[0]
        summary = summarize_runs(group)
        summary_rows.append(
            {
                "model": base["model"],
                "configured_max_model_len": base["configured_max_model_len"],
                "target_tokens": base["target_tokens"],
                "actual_prompt_tokens_after_chat_template": base["actual_prompt_tokens_after_chat_template"],
                "prompt_source": base["prompt_source"],
                "prompt_entropy_type": base["prompt_entropy_type"],
                "max_num_seqs": base["max_num_seqs"],
                **summary,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACTUAL_CONTEXT_SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_rows)


def load_prompts(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--prompts", default="configs/qwen3_8b_actual_context_prompts.jsonl")
    parser.add_argument("--raw-csv", default="results/baselines/qwen3_8b_actual_context_scaling_raw.csv")
    parser.add_argument("--summary-csv", default="results/baselines/qwen3_8b_actual_context_scaling_summary.csv")
    parser.add_argument("--configured-max-model-len", required=True)
    parser.add_argument("--max-num-seqs", default="1")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--target-tokens")
    parser.add_argument("--prompt-source")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--gpu-monitor-dir", default="logs/gpu_monitor")
    parser.add_argument("--gpu-monitor-prefix", default="phase2_5_qwen3_8b")
    parser.add_argument("--vllm-kv-capacity", default="")
    parser.add_argument("--commit-hash", default=None)
    args = parser.parse_args()

    prompts = load_prompts(Path(args.prompts))
    if args.target_tokens:
        prompts = [p for p in prompts if str(p["target_tokens"]) == str(args.target_tokens)]
    if args.prompt_source:
        prompts = [p for p in prompts if p["prompt_source"] == args.prompt_source]

    commit = args.commit_hash or current_commit()
    rows = []
    exit_code = 0
    for prompt in prompts:
        for index in range(args.warmup + args.repeat):
            measured = index >= args.warmup
            run_id = f"{prompt['prompt_source']}_{prompt['target_tokens']}_run{index - args.warmup + 1}" if measured else "warmup"
            monitor_path = Path(args.gpu_monitor_dir) / (
                f"{args.gpu_monitor_prefix}_{prompt['target_tokens']}_{prompt['prompt_source']}_{run_id}.csv"
            )
            monitor = start_gpu_monitor(monitor_path, 0.5) if measured else None
            try:
                result = stream_prompt(args.base_url, args.model, prompt, args.temperature, args.timeout)
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                result = {
                    "ttft_ms": "",
                    "tpot_ms": "",
                    "total_latency_ms": "",
                    "completion_tokens": 0,
                    "runtime_success": False,
                    "error_type": classify_error(str(exc)),
                    "error_message": str(exc),
                }
                exit_code = 1
            finally:
                stop_gpu_monitor(monitor)

            if not measured:
                continue
            peak = peak_gpu_mem_gb(monitor_path)
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "model": args.model,
                "configured_max_model_len": args.configured_max_model_len,
                "actual_prompt_tokens_after_chat_template": prompt["actual_prompt_tokens_after_chat_template"],
                "target_tokens": prompt["target_tokens"],
                "prompt_source": prompt["prompt_source"],
                "prompt_entropy_type": prompt["prompt_entropy_type"],
                "max_num_seqs": args.max_num_seqs,
                "temperature": args.temperature,
                "generation_max_tokens": prompt.get("generation_max_tokens", 128),
                "prompt_tokens": prompt["actual_prompt_tokens_after_chat_template"],
                "peak_gpu_mem_gb": peak,
                "vllm_kv_capacity": args.vllm_kv_capacity,
                "startup_success": True,
                "log_path": args.log_path,
                "gpu_monitor_path": str(monitor_path),
                "commit_hash": commit,
                **result,
            }
            rows.append(row)
            if row["error_type"] != "none":
                exit_code = 1

    append_rows(Path(args.raw_csv), ACTUAL_CONTEXT_RAW_FIELDS, rows)
    existing = []
    raw_path = Path(args.raw_csv)
    if raw_path.exists():
        with raw_path.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
    write_summary(Path(args.summary_csv), existing)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
