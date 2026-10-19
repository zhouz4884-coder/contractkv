#!/usr/bin/env python3
"""Live burst workload for the Phase 16R quiescence admission gate."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import PSTPSpec, VerifyDecision, write_registry
from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase16e_live_transactional_slc import messages, send_stream


RAW_FIELDS = [
    "idle_grace_ms", "seed", "condition", "request_class", "request_index",
    "success", "ttft_ms", "tpot_ms", "total_latency_ms", "request_id", "error",
]
SUMMARY_FIELDS = [
    "idle_grace_ms", "condition", "active_requests", "active_success_rate",
    "shadow_requests", "shadow_success_rate", "active_mean_ttft_ms",
    "active_p95_ttft_ms", "active_p95_latency_ms", "p95_penalty_ms",
    "collision_count", "max_backoff_ms", "idle_hysteresis_events",
    "foreground_block_events", "kv_pressure_events", "shadow_rounds",
    "mixed_foreground_shadow_rounds", "max_shadow_request_tokens",
    "initial_and_running_cap_pass", "gate_pass", "claim_boundary",
]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def wait_for_shadow_round(path: Path, timeout_sec: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while asyncio.get_running_loop().time() < deadline:
        if any(event.get("event") == "shadow_round" for event in load_events(path)):
            return True
        await asyncio.sleep(.001)
    return False


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    import aiohttp

    rows: list[dict[str, Any]] = []
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=64)) as session:
        for seed in args.seeds:
            conditions = ("baseline", "shadow_burst") if seed % 2 == 0 else ("shadow_burst", "baseline")
            for condition in conditions:
                specs: dict[str, PSTPSpec] = {}
                shadow_jobs: list[tuple[str, str]] = []
                if condition == "shadow_burst":
                    for index in range(args.shadow_requests):
                        request_id = f"phase16r-shadow-{args.idle_grace_ms}-{seed}-{index}"
                        marker = f"SHADOW16R_{args.idle_grace_ms}_{seed}_{index}"
                        shadow_jobs.append((request_id, marker))
                        specs[request_id] = PSTPSpec(
                            txn_id=f"txn-{request_id}", stable_prefix_end_token=0,
                            verify_decision=VerifyDecision.CANCELLED,
                            failure_reason="quiescence workload is ephemeral",
                            shadow_work=True,
                        )
                write_registry(args.registry, specs)
                for warmup_index in range(args.warmup_requests):
                    warmup_id = f"phase16r-warmup-{condition}-{args.idle_grace_ms}-{seed}-{warmup_index}"
                    await send_stream(
                        session, args.base_url, args.model, warmup_id,
                        messages(f"WARMUP16R_{seed}_{condition}_{warmup_index}"),
                        args.max_tokens, 0, "warmup",
                    )
                await asyncio.sleep(.002)
                tasks: list[asyncio.Task[dict[str, Any]]] = []
                for request_id, marker in shadow_jobs:
                    tasks.append(asyncio.create_task(send_stream(
                        session, args.base_url, args.model, request_id,
                        messages(marker, args.shadow_words, request_id),
                        args.max_tokens, 100, "shadow",
                    )))
                if shadow_jobs:
                    if args.idle_grace_ms == 0 and args.synchronize_collision:
                        await wait_for_shadow_round(args.event_log)
                    else:
                        await asyncio.sleep(args.shadow_head_start_ms / 1000.0)
                for index in range(args.active_requests):
                    request_id = f"phase16r-active-{condition}-{args.idle_grace_ms}-{seed}-{index}"
                    marker = f"ACTIVE16R_{args.idle_grace_ms}_{seed}_{index}"
                    tasks.append(asyncio.create_task(send_stream(
                        session, args.base_url, args.model, request_id,
                        messages(marker), args.max_tokens, 0, "active",
                    )))
                    if args.active_gap_ms:
                        await asyncio.sleep(args.active_gap_ms / 1000.0)
                results = await asyncio.gather(*tasks)
                for index, result in enumerate(results):
                    rows.append({
                        "idle_grace_ms": args.idle_grace_ms, "seed": seed,
                        "condition": condition, "request_class": result["request_class"],
                        "request_index": index, "success": result["success"],
                        "ttft_ms": result["ttft_ms"], "tpot_ms": result["tpot_ms"],
                        "total_latency_ms": result["total_latency_ms"],
                        "request_id": result["request_id"], "error": result["error"],
                    })
                await asyncio.sleep(args.cooldown_sec)
    return rows


def summarize(args: argparse.Namespace, rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = [row for row in rows if row["condition"] == "baseline" and row["request_class"] == "active" and row["success"]]
    baseline_p95 = percentile([float(row["ttft_ms"]) for row in baseline], .95)
    collisions = [event for event in events if event.get("event") == "shadow_collision"]
    admissions = [event for event in events if event.get("event") == "shadow_admission"]
    rounds = [event for event in events if event.get("event") == "shadow_round"]
    output = []
    for condition in ("baseline", "shadow_burst"):
        active = [row for row in rows if row["condition"] == condition and row["request_class"] == "active"]
        shadow = [row for row in rows if row["condition"] == condition and row["request_class"] == "shadow"]
        good_active = [row for row in active if row["success"]]
        good_shadow = [row for row in shadow if row["success"]]
        ttft = [float(row["ttft_ms"]) for row in good_active]
        latency = [float(row["total_latency_ms"]) for row in good_active]
        p95 = percentile(ttft, .95)
        max_chunk = max((int(event.get("max_shadow_request_tokens", 0)) for event in rounds), default=0)
        mixed = sum(int(event.get("foreground_tokens", 0)) > 0 for event in rounds)
        gate = condition == "baseline" or (
            len(good_shadow) == len(shadow)
            and mixed == 0
            and max_chunk <= args.shadow_chunk_tokens
        )
        output.append({
            "idle_grace_ms": args.idle_grace_ms, "condition": condition,
            "active_requests": len(active),
            "active_success_rate": len(good_active) / max(len(active), 1),
            "shadow_requests": len(shadow),
            "shadow_success_rate": len(good_shadow) / max(len(shadow), 1) if shadow else 1.0,
            "active_mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
            "active_p95_ttft_ms": p95,
            "active_p95_latency_ms": percentile(latency, .95),
            "p95_penalty_ms": p95 - baseline_p95 if condition != "baseline" else 0.0,
            "collision_count": len(collisions) if condition != "baseline" else 0,
            "max_backoff_ms": max((float(event.get("backoff_ms", 0)) for event in collisions), default=0.0) if condition != "baseline" else 0.0,
            "idle_hysteresis_events": sum(event.get("reason") == "idle_hysteresis" for event in admissions) if condition != "baseline" else 0,
            "foreground_block_events": sum(event.get("reason") in {"foreground_waiting", "foreground_running"} for event in admissions) if condition != "baseline" else 0,
            "kv_pressure_events": sum(event.get("reason") == "kv_pressure" for event in admissions) if condition != "baseline" else 0,
            "shadow_rounds": len(rounds) if condition != "baseline" else 0,
            "mixed_foreground_shadow_rounds": mixed if condition != "baseline" else 0,
            "max_shadow_request_tokens": max_chunk if condition != "baseline" else 0,
            "initial_and_running_cap_pass": max_chunk <= args.shadow_chunk_tokens,
            "gate_pass": gate,
            "claim_boundary": "Live vLLM V1 burst-aware admission and micro-chunk scheduling; independent of verification and PSTP decisions.",
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
    parser.add_argument("--base-url", default="http://127.0.0.1:8016/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--idle-grace-ms", type=float, required=True)
    parser.add_argument("--shadow-chunk-tokens", type=int, default=32)
    parser.add_argument("--seeds", type=int, nargs="+", default=[16801, 16802, 16803])
    parser.add_argument("--active-requests", type=int, default=20)
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument("--shadow-requests", type=int, default=2)
    parser.add_argument("--active-gap-ms", type=float, default=10.0)
    parser.add_argument("--shadow-head-start-ms", type=float, default=5.0)
    parser.add_argument("--synchronize-collision", action="store_true", default=True)
    parser.add_argument("--shadow-words", type=int, default=480)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--cooldown-sec", type=float, default=.5)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    rows = asyncio.run(run(args))
    events = load_events(args.event_log)
    summary = summarize(args, rows, events)
    write_csv(args.raw_output, rows, RAW_FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(json.dumps(summary, indent=2))
    measured = [row for row in rows if row["request_class"] in {"active", "shadow"}]
    return 0 if all(row["success"] for row in measured) else 1


if __name__ == "__main__":
    raise SystemExit(main())
