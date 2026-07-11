#!/usr/bin/env python3
"""Phase 14D open-loop offered-load replay for real vLLM capacity knees."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream, send_chat_stream_async
from scripts.phase14m_physical_dedup import fit_shared_text, messages_for
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_metrics


RAW_FIELDS = [
    "cell_id", "policy", "arrival_rate_rps", "seed", "request_index",
    "arrival_offset_ms", "actual_request_start_ms", "send_lag_ms", "request_id", "success", "quality_sanity", "ttft_ms",
    "tpot_ms", "latency_ms", "output_tokens", "prefix_hit_tokens",
    "observed_new_prefill_tokens", "scheduler_wait_ms", "used_gpu_blocks",
    "free_gpu_blocks", "error_type", "error_message",
]

SUMMARY_FIELDS = [
    "cell_id", "policy", "arrival_rate_rps", "seed", "measurement_seconds",
    "offered_requests", "completed_requests", "completion_rate", "quality_sanity_rate",
    "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "mean_latency_ms",
    "slo_ttft_ms", "slo_compliant_requests", "slo_compliant_req_per_sec",
    "mean_scheduler_wait_ms", "second_half_wait_slope_sec_per_sec", "p95_send_lag_ms", "p99_send_lag_ms",
    "end_backlog", "mean_prefix_hit_tokens", "mean_observed_new_prefill_tokens",
    "used_block_high_water", "minimum_free_blocks", "primer_latency_ms",
    "cold_start_amortized_latency_ms", "min_completed_required",
    "min_second_half_samples_required", "capacity_stable", "claim_boundary",
]


def load_events_since(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read().decode("utf-8", errors="replace")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def slope(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator if denominator else 0.0


async def one_request(
    args: argparse.Namespace,
    policy: str,
    shared: str,
    request_index: int,
    start: float,
    deadline: float,
    session: Any,
) -> dict[str, Any]:
    await asyncio.sleep(max(0.0, deadline - time.perf_counter()))
    actual_start = time.perf_counter()
    result = await send_chat_stream_async(
        session, args.base_url, args.model,
        messages_for(policy, shared, request_index, f"M{request_index}X", args.cell_id),
        args.max_tokens, f"{args.cell_id}-{request_index}",
    )
    result.update({
        "request_index": request_index,
        "arrival_offset_ms": (deadline - start) * 1000.0,
        "actual_request_start_ms": (actual_start - start) * 1000.0,
        "send_lag_ms": max(0.0, (actual_start - deadline) * 1000.0),
        "quality_sanity": f"M{request_index}X" in str(result.get("output_text", "")),
    })
    return result


async def run_open_loop(args: argparse.Namespace, shared: str) -> list[dict[str, Any]]:
    import aiohttp
    rng = random.Random(args.seed)
    start = time.perf_counter()
    stop = start + args.measurement_seconds
    deadline = start
    tasks = []
    request_index = 0
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            deadline += rng.expovariate(args.arrival_rate_rps)
            if deadline > stop:
                break
            tasks.append(asyncio.create_task(one_request(args, args.policy, shared, request_index, start, deadline, session)))
            request_index += 1
        # The drain window starts only after the offered-load measurement window
        # closes.  Starting it while late arrivals are still sleeping would turn
        # valid on-time arrivals into artificial capacity failures.
        await asyncio.sleep(max(0.0, stop - time.perf_counter()))
        done, pending = await asyncio.wait(tasks, timeout=args.drain_seconds)
    for task in pending:
        task.cancel()
    rows = []
    for task in done:
        try:
            rows.append(task.result())
        except Exception as exc:
            rows.append({"success": False, "error_type": type(exc).__name__, "error_message": str(exc)})
    for task in pending:
        rows.append({"success": False, "error_type": "drain_timeout", "error_message": "request remained outstanding after drain", "request_index": -1, "arrival_offset_ms": 0, "actual_request_start_ms": "", "send_lag_ms": "", "quality_sanity": False})
    args.offered_requests = request_index
    return rows


def join_metrics(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = {str(row.get("request_id", "")): row for row in summarize_metrics(events)}
    output = []
    for row in rows:
        metric = metrics.get(str(row.get("request_id", "")), {})
        output.append({
            "cell_id": "", "policy": "", "arrival_rate_rps": "", "seed": "",
            "request_index": row.get("request_index", ""), "arrival_offset_ms": row.get("arrival_offset_ms", ""),
            "actual_request_start_ms": row.get("actual_request_start_ms", ""), "send_lag_ms": row.get("send_lag_ms", ""),
            "request_id": row.get("request_id", ""), "success": row.get("success", False),
            "quality_sanity": row.get("quality_sanity", False), "ttft_ms": row.get("ttft_ms", 0.0),
            "tpot_ms": row.get("tpot_ms", 0.0), "latency_ms": row.get("total_latency_ms", 0.0),
            "output_tokens": row.get("output_tokens", 0), "prefix_hit_tokens": metric.get("prefix_hit_tokens", ""),
            "observed_new_prefill_tokens": metric.get("new_prefill_tokens", ""),
            "scheduler_wait_ms": metric.get("scheduler_wait_ms", ""),
            "used_gpu_blocks": "", "free_gpu_blocks": "",
            "error_type": row.get("error_type", ""), "error_message": row.get("error_message", ""),
        })
    by_request: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event") == "prefix_cache_request_observation":
            by_request.setdefault(str(event.get("request_id", "")), []).append(event)
    for row in output:
        group = by_request.get(str(row["request_id"]), [])
        row["used_gpu_blocks"] = max((int(event.get("used_gpu_blocks") or 0) for event in group), default=0)
        row["free_gpu_blocks"] = min((int(event.get("free_gpu_blocks") or 0) for event in group), default=0)
    return output


def summarize(rows: list[dict[str, Any]], args: argparse.Namespace, primer_latency_ms: float = 0.0) -> dict[str, Any]:
    successes = [row for row in rows if row.get("success")]
    ttft = [float(row.get("ttft_ms") or 0.0) for row in successes]
    waits = [float(row.get("scheduler_wait_ms") or 0.0) for row in successes if row.get("scheduler_wait_ms") not in ("", None)]
    second_half = [row for row in successes if float(row.get("arrival_offset_ms") or 0.0) >= args.measurement_seconds * 500.0]
    xs = [float(row.get("arrival_offset_ms") or 0.0) / 1000.0 for row in second_half]
    ys = [float(row.get("scheduler_wait_ms") or 0.0) / 1000.0 for row in second_half]
    queue_slope = slope(xs, ys)
    send_lags = [float(row.get("send_lag_ms") or 0.0) for row in successes]
    compliant = [row for row in successes if row.get("quality_sanity") and float(row.get("ttft_ms") or 0.0) <= args.slo_ttft_ms]
    end_backlog = args.offered_requests - len(successes)
    stable = (
        len(successes) >= getattr(args, "min_completed", 0)
        and len(second_half) >= getattr(args, "min_second_half_samples", 0)
        and len(successes) / max(1, args.offered_requests) >= .99
        and percentile(ttft, .95) <= args.slo_ttft_ms
        and queue_slope <= .02
        and percentile(send_lags, .95) <= getattr(args, "max_p95_send_lag_ms", 5.0)
        and percentile(send_lags, .99) <= getattr(args, "max_p99_send_lag_ms", 20.0)
        and end_backlog == 0
    )
    return {
        "cell_id": args.cell_id, "policy": args.policy, "arrival_rate_rps": args.arrival_rate_rps,
        "seed": args.seed, "measurement_seconds": args.measurement_seconds,
        "offered_requests": args.offered_requests, "completed_requests": len(successes),
        "completion_rate": len(successes) / max(1, args.offered_requests),
        "quality_sanity_rate": sum(bool(row.get("quality_sanity")) for row in successes) / len(successes) if successes else 0.0,
        "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, .95),
        "mean_tpot_ms": statistics.mean(float(row.get("tpot_ms") or 0.0) for row in successes) if successes else 0.0,
        "mean_latency_ms": statistics.mean(float(row.get("latency_ms") or 0.0) for row in successes) if successes else 0.0,
        "slo_ttft_ms": args.slo_ttft_ms, "slo_compliant_requests": len(compliant),
        "slo_compliant_req_per_sec": len(compliant) / args.measurement_seconds,
        "mean_scheduler_wait_ms": statistics.mean(waits) if waits else 0.0,
        "second_half_wait_slope_sec_per_sec": queue_slope, "end_backlog": end_backlog,
        "p95_send_lag_ms": percentile(send_lags, .95), "p99_send_lag_ms": percentile(send_lags, .99),
        "mean_prefix_hit_tokens": statistics.mean(float(row.get("prefix_hit_tokens") or 0.0) for row in successes) if successes else 0.0,
        "mean_observed_new_prefill_tokens": statistics.mean(float(row.get("observed_new_prefill_tokens") or 0.0) for row in successes) if successes else 0.0,
        "used_block_high_water": max((int(row.get("used_gpu_blocks") or 0) for row in successes), default=0),
        "minimum_free_blocks": min((int(row.get("free_gpu_blocks") or 0) for row in successes), default=0),
        "primer_latency_ms": primer_latency_ms,
        "cold_start_amortized_latency_ms": (
            statistics.mean(float(row.get("latency_ms") or 0.0) for row in successes) + primer_latency_ms / len(successes)
            if successes else 0.0
        ),
        "min_completed_required": getattr(args, "min_completed", 0),
        "min_second_half_samples_required": getattr(args, "min_second_half_samples", 0),
        "capacity_stable": stable,
        "claim_boundary": "Real vLLM open-loop offered-load measurement. Capacity requires the documented completion, SLO, queue-stability, and drain conditions.",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("raw-order", "static-posc", "contractkv-caposc"), required=True)
    parser.add_argument("--arrival-rate-rps", type=float, required=True)
    parser.add_argument("--measurement-seconds", type=float, default=60.0)
    parser.add_argument("--drain-seconds", type=float, default=30.0)
    parser.add_argument("--shared-target-tokens", type=int, default=4096)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--slo-ttft-ms", type=float, default=2000.0)
    parser.add_argument("--seed", type=int, default=14014)
    parser.add_argument("--min-completed", type=int, default=0)
    parser.add_argument("--min-second-half-samples", type=int, default=0)
    parser.add_argument("--max-p95-send-lag-ms", type=float, default=5.0)
    parser.add_argument("--max-p99-send-lag-ms", type=float, default=20.0)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    shared = fit_shared_text(tokenizer, args.shared_target_tokens)
    offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    primer_latency_ms = 0.0
    if args.policy != "raw-order":
        primer = send_chat_stream(args.base_url, args.model, messages_for(args.policy, shared, -1, "MPRIMERX", args.cell_id), args.max_tokens, args.timeout, f"{args.cell_id}-primer")
        if not primer.get("success"):
            raise SystemExit(f"prefix primer failed: {primer.get('error_message')}")
        primer_latency_ms = float(primer.get("total_latency_ms") or 0.0)
    rows = asyncio.run(run_open_loop(args, shared))
    time.sleep(.5)
    joined = join_metrics(rows, load_events_since(args.metrics_events, offset))
    for row in joined:
        row.update({"cell_id": args.cell_id, "policy": args.policy, "arrival_rate_rps": args.arrival_rate_rps, "seed": args.seed})
    summary = summarize(joined, args, primer_latency_ms)
    write_csv(args.raw_output, joined, RAW_FIELDS)
    write_csv(args.summary_output, [summary], SUMMARY_FIELDS)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["offered_requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
