#!/usr/bin/env python3
"""Live vLLM probe for micro-chunk interference and ephemeral cache commit."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_prefix_events


INTERFERENCE_FIELDS = [
    "model", "seed", "condition", "request_class", "request_index", "success",
    "ttft_ms", "tpot_ms", "total_latency_ms", "output_text", "request_id", "error",
]
INTERFERENCE_SUMMARY_FIELDS = [
    "model", "condition", "active_requests", "active_success_rate",
    "shadow_requests", "shadow_success_rate",
    "active_mean_ttft_ms", "active_p95_ttft_ms", "active_p99_ttft_ms",
    "active_mean_latency_ms", "active_p95_latency_ms", "p95_penalty_ms",
    "p95_penalty_fraction", "gate_pass", "claim_boundary",
]
TRANSACTION_FIELDS = [
    "model", "action", "shadow_request_id", "probe_request_id", "shadow_success",
    "probe_success", "shadow_marker_ok", "probe_marker_ok", "shadow_ttft_ms",
    "probe_ttft_ms", "shadow_prompt_tokens", "shadow_new_prefill_tokens",
    "probe_prompt_tokens", "probe_new_prefill_tokens", "probe_cached_tokens",
    "cache_reuse_fraction", "expected_cache_visibility", "gate_pass", "claim_boundary",
]


def stable_context(words: int, nonce: str) -> str:
    vocabulary = (
        "contractkv transactional prefix ledger stable context segment cache "
        "scheduler validation semantic contract resident block"
    ).split()
    short_nonce = hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:8]
    body = [f"{short_nonce}_{vocabulary[index % len(vocabulary)]}_{index}" for index in range(words)]
    return " ".join(body)


def messages(marker: str, words: int = 0, nonce: str = "") -> list[dict[str, str]]:
    context = f"[STABLE_CONTEXT]\n{stable_context(words, nonce)}\n" if words else ""
    return [
        {"role": "system", "content": "/no_think Reply with only the requested marker."},
        {"role": "user", "content": f"{context}Return exactly this marker: {marker}"},
    ]


async def send_stream(
    session: Any,
    base_url: str,
    model: str,
    request_id: str,
    prompt: list[dict[str, str]],
    max_tokens: int,
    priority: int,
    request_class: str = "",
) -> dict[str, Any]:
    payload = {
        "model": model, "messages": prompt, "max_tokens": max_tokens,
        "temperature": 0, "top_p": 1, "stream": True,
        "stream_options": {"include_usage": True},
        "request_id": request_id, "priority": priority,
    }
    started = time.perf_counter()
    first = None
    token_times: list[float] = []
    output: list[str] = []
    usage: dict[str, Any] = {}
    response_id = request_id
    try:
        async with session.post(base_url.rstrip("/") + "/chat/completions", json=payload) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {(await response.text())[:300]}")
            async for raw in response.content:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                response_id = chunk.get("id", response_id)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                content = choices[0].get("delta", {}).get("content") if choices else None
                if content:
                    now = time.perf_counter()
                    first = first or now
                    token_times.append(now)
                    output.append(content)
        ended = time.perf_counter()
        return {
            "success": bool(output), "request_id": response_id,
            "request_class": request_class,
            "output_text": "".join(output),
            "ttft_ms": (first - started) * 1000.0 if first else 0.0,
            "tpot_ms": ((token_times[-1] - token_times[0]) * 1000.0 / max(len(token_times) - 1, 1)) if len(token_times) > 1 else 0.0,
            "total_latency_ms": (ended - started) * 1000.0,
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "error": "",
        }
    except Exception as exc:
        return {
            "success": False, "request_id": response_id, "output_text": "",
            "request_class": request_class,
            "ttft_ms": 0.0, "tpot_ms": 0.0,
            "total_latency_ms": (time.perf_counter() - started) * 1000.0,
            "prompt_tokens": 0, "error": str(exc)[:300],
        }


async def run_interference(args: argparse.Namespace, session: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        for condition in ["baseline", "idle_only_shadow"]:
            tasks: list[asyncio.Task[dict[str, Any]]] = []
            for warmup_index in range(args.warmup_requests):
                warmup_marker = f"WARMUP_{args.model}_{condition}_{seed}_{warmup_index}"
                await send_stream(
                    session, args.base_url, args.model,
                    f"contractkv-warmup-{condition}-{seed}-{warmup_index}",
                    messages(warmup_marker), args.max_tokens, 0, "active",
                )
            if condition == "idle_only_shadow":
                for index in range(args.shadow_requests):
                    marker = f"SHADOW_{args.model}_{seed}_{index}"
                    tasks.append(asyncio.create_task(send_stream(
                        session, args.base_url, args.model,
                        f"contractkv-shadow-abort-interference-{seed}-{index}",
                        messages(marker, args.shadow_words, f"shadow-{seed}-{index}"),
                        args.max_tokens, 100, "shadow",
                    )))
                await asyncio.sleep(args.shadow_head_start_ms / 1000.0)
            for index in range(args.active_requests):
                marker = f"ACTIVE_{args.model}_{condition}_{seed}_{index}"
                task = asyncio.create_task(send_stream(
                    session, args.base_url, args.model,
                    f"contractkv-active-{condition}-{seed}-{index}",
                    messages(marker), args.max_tokens, 0,
                    "active",
                ))
                task._contractkv_meta = (index, marker)  # type: ignore[attr-defined]
                tasks.append(task)
                if args.active_gap_ms:
                    await asyncio.sleep(args.active_gap_ms / 1000.0)
            for index, task in enumerate(asyncio.as_completed(tasks)):
                result = await task
                request_class = str(result["request_class"])
                rows.append({
                    "model": args.model, "seed": seed, "condition": condition,
                    "request_class": request_class, "request_index": index,
                    **{key: result.get(key, "") for key in ["success", "ttft_ms", "tpot_ms", "total_latency_ms", "output_text", "request_id", "error"]},
                })
            await asyncio.sleep(args.cooldown_sec)
    return rows


def summarize_interference(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    shadow_grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["request_class"] == "active":
            grouped.setdefault(str(row["condition"]), []).append(row)
        else:
            shadow_grouped.setdefault(str(row["condition"]), []).append(row)
    baseline_p95 = percentile([float(row["ttft_ms"]) for row in grouped.get("baseline", []) if row["success"]], 0.95)
    for condition, items in sorted(grouped.items()):
        good = [row for row in items if row["success"]]
        ttft = [float(row["ttft_ms"]) for row in good]
        latency = [float(row["total_latency_ms"]) for row in good]
        shadows = shadow_grouped.get(condition, [])
        good_shadows = [row for row in shadows if row["success"]]
        p95 = percentile(ttft, 0.95)
        penalty = p95 - baseline_p95 if condition != "baseline" else 0.0
        fraction = penalty / baseline_p95 if baseline_p95 else 0.0
        out.append({
            "model": items[0]["model"] if items else "", "condition": condition,
            "active_requests": len(items), "active_success_rate": len(good) / max(len(items), 1),
            "shadow_requests": len(shadows),
            "shadow_success_rate": len(good_shadows) / max(len(shadows), 1) if shadows else 1.0,
            "active_mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
            "active_p95_ttft_ms": p95,
            "active_p99_ttft_ms": percentile(ttft, 0.99),
            "active_mean_latency_ms": statistics.mean(latency) if latency else 0.0,
            "active_p95_latency_ms": percentile(latency, 0.95),
            "p95_penalty_ms": penalty, "p95_penalty_fraction": fraction,
            "gate_pass": condition == "baseline" or (len(good_shadows) == len(shadows) and penalty <= max(10.0, 0.05 * baseline_p95)),
            "claim_boundary": "Fresh live vLLM V1 endpoint with source-level IDLE_ONLY micro-chunk hook.",
        })
    return out


def prefix_metrics(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {str(row.get("request_id")): row for row in summarize_prefix_events(events)}


async def run_transactions(args: argparse.Namespace, session: Any) -> list[dict[str, Any]]:
    pending = []
    for action in ["abort", "commit"]:
        nonce = f"phase16e-{args.model}-{action}-{time.time_ns()}"
        marker = f"TXN_{action.upper()}_OK"
        prompt = messages(marker, args.transaction_words, nonce)
        shadow = await send_stream(
            session, args.base_url, args.model,
            f"contractkv-shadow-{action}-validation-{nonce}", prompt,
            args.max_tokens, 100,
            "shadow",
        )
        await asyncio.sleep(0.5)
        probe = await send_stream(
            session, args.base_url, args.model,
            f"contractkv-foreground-probe-{action}-{nonce}", prompt,
            args.max_tokens, 0,
            "active",
        )
        pending.append((action, marker, shadow, probe))
        await asyncio.sleep(0.5)
    await asyncio.sleep(1.0)
    metrics = prefix_metrics(args.prefix_metrics_log)
    rows = []
    for action, marker, shadow, probe in pending:
        shadow_metric = metrics.get(str(shadow["request_id"]), {})
        probe_metric = metrics.get(str(probe["request_id"]), {})
        prompt_tokens = int(probe_metric.get("prompt_tokens", probe.get("prompt_tokens", 0)) or 0)
        new_prefill = int(probe_metric.get("new_prefill_tokens", prompt_tokens) or 0)
        reuse = 1.0 - new_prefill / max(prompt_tokens, 1)
        expected = action == "commit"
        gate = reuse >= 0.80 if expected else reuse <= 0.20
        rows.append({
            "model": args.model, "action": action,
            "shadow_request_id": shadow["request_id"], "probe_request_id": probe["request_id"],
            "shadow_success": shadow["success"], "probe_success": probe["success"],
            "shadow_marker_ok": marker in shadow["output_text"], "probe_marker_ok": marker in probe["output_text"],
            "shadow_ttft_ms": shadow["ttft_ms"], "probe_ttft_ms": probe["ttft_ms"],
            "shadow_prompt_tokens": shadow_metric.get("prompt_tokens", shadow.get("prompt_tokens", 0)),
            "shadow_new_prefill_tokens": shadow_metric.get("new_prefill_tokens", ""),
            "probe_prompt_tokens": prompt_tokens, "probe_new_prefill_tokens": new_prefill,
            "probe_cached_tokens": int(probe_metric.get("cached_tokens", max(0, prompt_tokens - new_prefill)) or 0),
            "cache_reuse_fraction": reuse, "expected_cache_visibility": expected,
            "gate_pass": bool(shadow["success"] and probe["success"] and marker in shadow["output_text"] and marker in probe["output_text"] and gate),
            "claim_boundary": "Real vLLM block-hash registration isolation; commit/abort at whole shadow-request stable prefix, not concurrent multi-transaction atomicity.",
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


async def main_async(args: argparse.Namespace) -> None:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=64)) as session:
        interference = await run_interference(args, session)
        transactions = await run_transactions(args, session)
    write_csv(args.interference_raw, interference, INTERFERENCE_FIELDS)
    write_csv(args.interference_summary, summarize_interference(interference), INTERFERENCE_SUMMARY_FIELDS)
    write_csv(args.transaction_output, transactions, TRANSACTION_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8016/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--seeds", type=int, nargs="+", default=[16601, 16602, 16603])
    parser.add_argument("--active-requests", type=int, default=30)
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument("--shadow-requests", type=int, default=2)
    parser.add_argument("--active-gap-ms", type=float, default=50.0)
    parser.add_argument("--shadow-head-start-ms", type=float, default=20.0)
    parser.add_argument("--shadow-words", type=int, default=400)
    parser.add_argument("--transaction-words", type=int, default=300)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--cooldown-sec", type=float, default=1.0)
    parser.add_argument("--prefix-metrics-log", type=Path, required=True)
    parser.add_argument("--interference-raw", type=Path, default=Path("results/hard_systems/phase16e_live_interference_raw_v0.csv"))
    parser.add_argument("--interference-summary", type=Path, default=Path("results/hard_systems/phase16e_live_interference_summary_v0.csv"))
    parser.add_argument("--transaction-output", type=Path, default=Path("results/hard_systems/phase16e_live_ephemeral_transaction_v0.csv"))
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
