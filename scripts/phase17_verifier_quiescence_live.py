#!/usr/bin/env python3
"""Foreground interference under real Phase 17 teacher-forced verification."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_transaction import PSTPRuntime, write_runtime_registry
from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase16e_live_transactional_slc import messages, send_stream
from scripts.phase17_live_common import build_layout, build_runtime, generate_raw, tokenize


RAW_FIELDS = ["seed", "condition", "request_class", "success", "ttft_ms", "total_latency_ms", "request_id", "error"]
SUMMARY_FIELDS = [
    "condition", "active_requests", "active_success_rate", "verifier_requests",
    "verifier_success_rate", "active_mean_ttft_ms", "active_p95_ttft_ms",
    "p95_penalty_ms", "shadow_completion_rate", "mixed_rounds",
    "max_shadow_request_tokens", "idle_hysteresis_events", "collision_events",
    "gate_pass", "claim_boundary",
]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def send_verifier(session: Any, args: argparse.Namespace, request_id: str, prompt_ids: list[int]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with session.post(args.base_url.rstrip("/") + "/completions", json={
            "model": args.model, "prompt": prompt_ids, "max_tokens": 1,
            "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
            "request_id": request_id, "priority": 100,
        }) as response:
            text = await response.text()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {text[:200]}")
        return {"success": True, "request_id": request_id, "ttft_ms": 0.0,
                "total_latency_ms": (time.perf_counter() - started) * 1000, "error": "", "request_class": "verifier"}
    except Exception as exc:
        return {"success": False, "request_id": request_id, "ttft_ms": 0.0,
                "total_latency_ms": (time.perf_counter() - started) * 1000, "error": str(exc), "request_class": "verifier"}


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    rows = []
    registry: dict[str, PSTPRuntime] = {}
    prepared: dict[int, list[tuple[str, list[int]]]] = {}
    for seed in args.seeds:
        prepared[seed] = []
        for index in range(args.verifier_requests):
            case_id = f"q-{seed}-{index}"
            layout = build_layout(case_id)
            raw = generate_raw(args.base_url, args.model, f"phase17-q-raw-{case_id}", layout["raw_messages"], args.timeout)
            stable_ids = tokenize(args.base_url, args.model, layout["stable_messages"], False, args.timeout)
            candidate_ids = tokenize(args.base_url, args.model, layout["candidate_messages"], True, args.timeout)
            request_id = f"phase17-q-candidate-{case_id}"
            registry[request_id] = build_runtime(
                txn_id=f"txn-{case_id}", stable_ids=stable_ids,
                candidate_prompt_ids=candidate_ids, raw=raw, stop_token_id=args.stop_token_id,
                thresholds={"tau_raw": 0.0, "tau_abs": 0.0, "tau_drop": 4.0},
                candidate_messages=layout["candidate_messages"],
            )
            prepared[seed].append((request_id, candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]]))
    write_runtime_registry(args.registry, registry)

    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=64)) as session:
        for seed in args.seeds:
            conditions = ("baseline", "live_verifier") if seed % 2 == 0 else ("live_verifier", "baseline")
            for condition in conditions:
                condition_code = "A" if condition == "baseline" else "B"
                for warmup in range(args.warmup_requests):
                    await send_stream(session, args.base_url, args.model,
                                      f"phase17-q-warmup-{seed}-{condition}-{warmup}",
                                      messages(f"QWARM_{seed}_{condition_code}_{warmup}"), 8, 0, "warmup")
                tasks = []
                for index in range(args.active_requests):
                    request_id = f"phase17-q-active-{seed}-{condition}-{index}"
                    tasks.append(asyncio.create_task(send_stream(
                        session, args.base_url, args.model, request_id,
                        messages(f"QACTIVE_{seed}_{condition_code}_{index}"), 8, 0, "active")))
                    await asyncio.sleep(args.active_gap_ms / 1000)
                if condition == "live_verifier":
                    # Shadow work becomes eligible only after the foreground
                    # burst is visible in waiting/running state.
                    await asyncio.sleep(.001)
                    for request_id, prompt_ids in prepared[seed]:
                        tasks.append(asyncio.create_task(send_verifier(session, args, request_id, prompt_ids)))
                for result in await asyncio.gather(*tasks):
                    rows.append({
                        "seed": seed, "condition": condition,
                        "request_class": result["request_class"], "success": result["success"],
                        "ttft_ms": result["ttft_ms"], "total_latency_ms": result["total_latency_ms"],
                        "request_id": result["request_id"], "error": result["error"],
                    })
                await asyncio.sleep(.5)
    return rows


def summarize(args: argparse.Namespace, rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = [row for row in rows if row["condition"] == "baseline" and row["request_class"] == "active" and row["success"]]
    baseline_p95 = percentile([float(row["ttft_ms"]) for row in baseline], .95)
    rounds = [event for event in events if event.get("event") == "shadow_round"]
    admissions = [event for event in events if event.get("event") == "shadow_admission"]
    collisions = [event for event in events if event.get("event") == "shadow_collision"]
    output = []
    for condition in ("baseline", "live_verifier"):
        active = [row for row in rows if row["condition"] == condition and row["request_class"] == "active"]
        verifiers = [row for row in rows if row["condition"] == condition and row["request_class"] == "verifier"]
        good = [row for row in active if row["success"]]
        good_verifiers = [row for row in verifiers if row["success"]]
        ttft = [float(row["ttft_ms"]) for row in good]
        p95 = percentile(ttft, .95)
        mixed = sum(int(event.get("foreground_tokens", 0)) > 0 for event in rounds) if condition == "live_verifier" else 0
        max_chunk = max((int(event.get("max_shadow_request_tokens", 0)) for event in rounds), default=0) if condition == "live_verifier" else 0
        penalty = p95 - baseline_p95 if condition == "live_verifier" else 0.0
        gate = condition == "baseline" or (
            len(good_verifiers) == len(verifiers) and mixed == 0
            and max_chunk <= 32 and penalty <= 10.0
        )
        output.append({
            "condition": condition, "active_requests": len(active),
            "active_success_rate": len(good) / max(len(active), 1),
            "verifier_requests": len(verifiers),
            "verifier_success_rate": len(good_verifiers) / max(len(verifiers), 1) if verifiers else 1.0,
            "active_mean_ttft_ms": statistics.mean(ttft) if ttft else 0,
            "active_p95_ttft_ms": p95, "p95_penalty_ms": penalty,
            "shadow_completion_rate": len(good_verifiers) / max(len(verifiers), 1) if verifiers else 1.0,
            "mixed_rounds": mixed, "max_shadow_request_tokens": max_chunk,
            "idle_hysteresis_events": sum(event.get("reason") == "idle_hysteresis" for event in admissions) if condition == "live_verifier" else 0,
            "collision_events": len(collisions) if condition == "live_verifier" else 0,
            "gate_pass": gate,
            "claim_boundary": "Live vLLM teacher-forced verification under foreground load; no acceleration claim.",
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8017/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[17101, 17102, 17103])
    parser.add_argument("--active-requests", type=int, default=20)
    parser.add_argument("--verifier-requests", type=int, default=2)
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument("--active-gap-ms", type=float, default=10)
    parser.add_argument("--stop-token-id", type=int, default=151645)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    rows = asyncio.run(run(args)); events = load_events(args.event_log)
    summary = summarize(args, rows, events)
    write_csv(args.raw_output, rows, RAW_FIELDS); write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(json.dumps(summary, indent=2))
    return 0 if all(row["gate_pass"] for row in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
