#!/usr/bin/env python3
"""Measure TTFT/TPOT through an OpenAI-compatible streaming API."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_FEASIBILITY_FIELDS = [
    "timestamp",
    "phase",
    "model",
    "model_path",
    "backend",
    "gpu_ids",
    "tensor_parallel_size",
    "dtype",
    "max_model_len",
    "max_num_seqs",
    "gpu_memory_utilization",
    "port",
    "startup_success",
    "startup_time_sec",
    "idle_gpu_mem_gb",
    "peak_gpu_mem_gb",
    "ttft_ms",
    "tpot_ms",
    "output_tokens",
    "error_type",
    "error_message",
    "log_path",
    "commit_hash",
]

ERROR_TYPES = {
    "none",
    "cuda_unavailable",
    "model_incomplete",
    "oom_startup",
    "oom_runtime",
    "vllm_import_error",
    "api_timeout",
    "bad_output",
    "port_conflict",
}


def compute_tpot_ms(first_token_time: float | None, end_time: float | None, output_tokens: int) -> float | None:
    if first_token_time is None or end_time is None or output_tokens <= 1:
        return None
    return round(((end_time - first_token_time) / (output_tokens - 1)) * 1000.0, 3)


def classify_error(message: str) -> str:
    text = message.lower()
    if not text:
        return "none"
    if "cuda" in text and ("unavailable" in text or "initialization" in text):
        return "cuda_unavailable"
    if "out of memory" in text or "oom" in text:
        return "oom_startup" if "startup" in text else "oom_runtime"
    if "vllm" in text and "import" in text:
        return "vllm_import_error"
    if "timed out" in text or "timeout" in text:
        return "api_timeout"
    if "port" in text and ("use" in text or "conflict" in text or "address already" in text):
        return "port_conflict"
    return "bad_output"


def current_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_FEASIBILITY_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in MODEL_FEASIBILITY_FIELDS})


def _iter_sse(response: Any):
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        yield json.loads(payload)


def run_prompt(base_url: str, model: str, prompt: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    request_body = dict(prompt)
    request_body["model"] = model
    request_body["stream"] = True
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    started = time.perf_counter()
    first_token_time: float | None = None
    output_chunks: list[str] = []

    with urllib.request.urlopen(request, timeout=timeout) as response:
        for chunk in _iter_sse(response):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content") or ""
            if content and first_token_time is None:
                first_token_time = time.perf_counter()
            if content:
                output_chunks.append(content)

    ended = time.perf_counter()
    output_text = "".join(output_chunks)
    output_tokens = len(output_chunks)
    ttft_ms = round((first_token_time - started) * 1000.0, 3) if first_token_time is not None else None
    return {
        "prompt_id": prompt.get("id", "unknown"),
        "success": bool(output_text),
        "ttft_ms": ttft_ms,
        "tpot_ms": compute_tpot_ms(first_token_time, ended, output_tokens),
        "output_tokens": output_tokens,
        "output_text": output_text,
        "error_type": "none" if output_text else "bad_output",
        "error_message": "",
    }


def load_prompts(path: Path) -> list[dict[str, Any]]:
    prompts = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                prompts.append(json.loads(line))
    return prompts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompts", default="configs/smoke_prompts.jsonl")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--feasibility-csv", default="results/baselines/model_feasibility.csv")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--gpu-ids", default="0")
    parser.add_argument("--tensor-parallel-size", default="1")
    parser.add_argument("--dtype", default="float16")
    parser.add_argument("--max-model-len", required=True)
    parser.add_argument("--max-num-seqs", required=True)
    parser.add_argument("--gpu-memory-utilization", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--startup-success", default="true")
    parser.add_argument("--startup-time-sec", default="")
    parser.add_argument("--idle-gpu-mem-gb", default="")
    parser.add_argument("--peak-gpu-mem-gb", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--commit-hash", default=None)
    args = parser.parse_args()

    prompts = load_prompts(Path(args.prompts))
    output_jsonl = Path(args.output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    commit_hash = args.commit_hash or current_commit()
    exit_code = 0

    with output_jsonl.open("a", encoding="utf-8") as result_handle:
        for prompt in prompts:
            timestamp = datetime.now(timezone.utc).isoformat()
            try:
                result = run_prompt(args.base_url, args.model, prompt, args.timeout)
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                result = {
                    "prompt_id": prompt.get("id", "unknown"),
                    "success": False,
                    "ttft_ms": "",
                    "tpot_ms": "",
                    "output_tokens": 0,
                    "output_text": "",
                    "error_type": classify_error(str(exc)),
                    "error_message": str(exc),
                }
                exit_code = 1

            result.update({"timestamp": timestamp, "model": args.model, "phase": args.phase})
            result_handle.write(json.dumps(result, ensure_ascii=False) + "\n")

            csv_row = {
                "timestamp": timestamp,
                "phase": args.phase,
                "model": args.model,
                "model_path": args.model_path,
                "backend": "vllm-openai-stream",
                "gpu_ids": args.gpu_ids,
                "tensor_parallel_size": args.tensor_parallel_size,
                "dtype": args.dtype,
                "max_model_len": args.max_model_len,
                "max_num_seqs": args.max_num_seqs,
                "gpu_memory_utilization": args.gpu_memory_utilization,
                "port": args.port,
                "startup_success": args.startup_success,
                "startup_time_sec": args.startup_time_sec,
                "idle_gpu_mem_gb": args.idle_gpu_mem_gb,
                "peak_gpu_mem_gb": args.peak_gpu_mem_gb,
                "ttft_ms": result["ttft_ms"],
                "tpot_ms": result["tpot_ms"],
                "output_tokens": result["output_tokens"],
                "error_type": result["error_type"],
                "error_message": result["error_message"],
                "log_path": args.log_path,
                "commit_hash": commit_hash,
            }
            _append_csv(Path(args.feasibility_csv), csv_row)

            if result["error_type"] != "none":
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

