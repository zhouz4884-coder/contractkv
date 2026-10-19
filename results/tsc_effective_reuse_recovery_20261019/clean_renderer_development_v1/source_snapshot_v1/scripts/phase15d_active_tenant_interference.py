#!/usr/bin/env python3
"""Measure active-tenant TTFT interference from shadow/canary requests.

This is a deliberately small live-endpoint probe. It keeps the active tenant
request shape fixed and compares it against the same active stream while
longer shadow canary requests are in flight.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import time
from pathlib import Path
from typing import Any

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream_async


RAW_FIELDS = [
    "seed",
    "condition",
    "request_class",
    "request_index",
    "success",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "output_tokens",
    "finish_reason",
    "error_type",
    "error_message",
]

SUMMARY_FIELDS = [
    "seed",
    "condition",
    "active_requests",
    "shadow_requests",
    "active_success_rate",
    "active_mean_ttft_ms",
    "active_p95_ttft_ms",
    "active_mean_latency_ms",
    "active_p95_latency_ms",
]


def stable_words(count: int, seed: int) -> str:
    base = (
        "contractkv segment prefix cache ledger safety canary verification "
        "task bearing prompt residency scheduler "
    ).split()
    words = (base * ((count // len(base)) + 2))[:count]
    words.insert(len(words) // 2, f"ACTIVE_INTERFERENCE_SEED_{seed}")
    return " ".join(words)


def active_messages(index: int, seed: int) -> list[dict[str, str]]:
    marker = f"ACTIVE_OK_{seed}_{index}"
    return [
        {"role": "system", "content": "/no_think Reply with only the requested marker."},
        {"role": "user", "content": f"Return exactly this marker: {marker}"},
    ]


def shadow_messages(index: int, seed: int, shadow_words: int) -> list[dict[str, str]]:
    marker = f"SHADOW_OK_{seed}_{index}"
    context = stable_words(shadow_words, seed + index)
    return [
        {"role": "system", "content": "/no_think Reply with only the requested marker."},
        {
            "role": "user",
            "content": (
                "[SHADOW_CANARY_CONTEXT]\n"
                f"{context}\n"
                f"Return exactly this marker: {marker}"
            ),
        },
    ]


async def bounded_request(
    sem: asyncio.Semaphore,
    session: Any,
    args: argparse.Namespace,
    messages: list[dict[str, str]],
    request_class: str,
    condition: str,
    index: int,
    seed: int,
) -> dict[str, Any]:
    async with sem:
        result = await send_chat_stream_async(
            session=session,
            base_url=args.base_url,
            model=args.model,
            messages=messages,
            max_tokens=args.max_tokens,
            request_tag=f"phase15d-{condition}-{request_class}-{seed}-{index}",
            seed=seed,
        )
    result.update(
        {
            "seed": seed,
            "condition": condition,
            "request_class": request_class,
            "request_index": index,
        }
    )
    return {field: result.get(field, "") for field in RAW_FIELDS}


async def run_condition(args: argparse.Namespace, seed: int, condition: str) -> list[dict[str, Any]]:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=args.timeout)
    connector = aiohttp.TCPConnector(limit=args.active_concurrency + args.shadow_concurrency + 4)
    rows: list[dict[str, Any]] = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        active_sem = asyncio.Semaphore(args.active_concurrency)
        shadow_sem = asyncio.Semaphore(max(args.shadow_concurrency, 1))
        tasks: list[asyncio.Task[dict[str, Any]]] = []
        if condition == "shadow_interference":
            for index in range(args.shadow_requests):
                tasks.append(
                    asyncio.create_task(
                        bounded_request(
                            shadow_sem,
                            session,
                            args,
                            shadow_messages(index, seed, args.shadow_words),
                            "shadow",
                            condition,
                            index,
                            seed,
                        )
                    )
                )
                if args.shadow_launch_gap_ms:
                    await asyncio.sleep(args.shadow_launch_gap_ms / 1000.0)
        for index in range(args.active_requests):
            tasks.append(
                asyncio.create_task(
                    bounded_request(
                        active_sem,
                        session,
                        args,
                        active_messages(index, seed),
                        "active",
                        condition,
                        index,
                        seed,
                    )
                )
            )
            if args.active_launch_gap_ms:
                await asyncio.sleep(args.active_launch_gap_ms / 1000.0)
        for task in asyncio.as_completed(tasks):
            rows.append(await task)
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["seed"]), str(row["condition"])), []).append(row)
    summaries = []
    for (seed, condition), items in sorted(grouped.items()):
        active = [row for row in items if row["request_class"] == "active"]
        active_success = [row for row in active if str(row["success"]).lower() == "true" or row["success"] is True]
        ttfts = [float(row["ttft_ms"]) for row in active_success]
        lats = [float(row["total_latency_ms"]) for row in active_success]
        shadows = [row for row in items if row["request_class"] == "shadow"]
        summaries.append(
            {
                "seed": seed,
                "condition": condition,
                "active_requests": len(active),
                "shadow_requests": len(shadows),
                "active_success_rate": round(len(active_success) / max(len(active), 1), 6),
                "active_mean_ttft_ms": round(statistics.mean(ttfts), 6) if ttfts else 0.0,
                "active_p95_ttft_ms": round(percentile(ttfts, 0.95), 6) if ttfts else 0.0,
                "active_mean_latency_ms": round(statistics.mean(lats), 6) if lats else 0.0,
                "active_p95_latency_ms": round(percentile(lats, 0.95), 6) if lats else 0.0,
            }
        )
    return summaries


def add_penalty_summary(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_seed: dict[str, dict[str, dict[str, Any]]] = {}
    for row in summary_rows:
        by_seed.setdefault(str(row["seed"]), {})[str(row["condition"])] = row
    out = list(summary_rows)
    for seed, conditions in sorted(by_seed.items()):
        base = conditions.get("baseline")
        shadow = conditions.get("shadow_interference")
        if not base or not shadow:
            continue
        out.append(
            {
                "seed": seed,
                "condition": "shadow_penalty_vs_baseline",
                "active_requests": shadow["active_requests"],
                "shadow_requests": shadow["shadow_requests"],
                "active_success_rate": shadow["active_success_rate"],
                "active_mean_ttft_ms": round(float(shadow["active_mean_ttft_ms"]) - float(base["active_mean_ttft_ms"]), 6),
                "active_p95_ttft_ms": round(float(shadow["active_p95_ttft_ms"]) - float(base["active_p95_ttft_ms"]), 6),
                "active_mean_latency_ms": round(float(shadow["active_mean_latency_ms"]) - float(base["active_mean_latency_ms"]), 6),
                "active_p95_latency_ms": round(float(shadow["active_p95_latency_ms"]) - float(base["active_p95_latency_ms"]), 6),
            }
        )
    return out


async def main_async(args: argparse.Namespace) -> None:
    all_rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        for condition in ["baseline", "shadow_interference"]:
            rows = await run_condition(args, seed, condition)
            all_rows.extend(rows)
            if args.cooldown_sec:
                await asyncio.sleep(args.cooldown_sec)
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    with args.raw_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    summary_rows = add_penalty_summary(summarize(all_rows))
    with args.summary_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--seeds", type=int, nargs="+", default=[15601, 15602, 15603])
    parser.add_argument("--active-requests", type=int, default=40)
    parser.add_argument("--shadow-requests", type=int, default=12)
    parser.add_argument("--active-concurrency", type=int, default=2)
    parser.add_argument("--shadow-concurrency", type=int, default=2)
    parser.add_argument("--active-launch-gap-ms", type=float, default=0.0)
    parser.add_argument("--shadow-launch-gap-ms", type=float, default=25.0)
    parser.add_argument("--shadow-words", type=int, default=2600)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--cooldown-sec", type=float, default=2.0)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase15d_active_tenant_interference_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase15d_active_tenant_interference_summary_v0.csv"))
    return parser.parse_args()


def main() -> None:
    started = time.perf_counter()
    args = parse_args()
    asyncio.run(main_async(args))
    print(f"wrote {args.raw_output} and {args.summary_output} in {time.perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
