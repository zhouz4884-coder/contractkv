#!/usr/bin/env python3
"""Run Phase 14M warm/cold cross-session physical prefix deduplication."""

from __future__ import annotations

import argparse
import concurrent.futures
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

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream


POLICIES = ("raw-order", "static-posc", "contractkv-caposc", "caposc-singleflight")

RAW_FIELDS = [
    "experiment", "cell_id", "policy", "shared_target_tokens", "sessions",
    "session_index", "request_id", "success", "quality_sanity", "ttft_ms",
    "tpot_ms", "latency_ms", "prompt_tokens", "prefix_hit_tokens",
    "reused_physical_blocks", "newly_allocated_blocks", "physical_block_ids",
    "physical_block_refcounts",
    "block_size", "total_gpu_blocks", "used_gpu_blocks", "free_gpu_blocks",
    "scheduler_wait_ms", "primer",
    "content_multiset_sha256",
    "error_type", "error_message",
]

SUMMARY_FIELDS = [
    "experiment", "cell_id", "policy", "shared_target_tokens", "sessions",
    "completed_requests", "completion_rate", "quality_sanity_rate", "mean_ttft_ms",
    "p95_ttft_ms", "mean_prefix_hit_tokens", "logical_reused_prefix_blocks",
    "unique_reused_physical_blocks", "dedup_factor", "shared_block_fraction",
    "unique_physical_blocks_effective", "effective_dedup_factor",
    "peak_concurrent_shared_blocks", "peak_concurrent_logical_refs",
    "peak_concurrent_unique_blocks", "peak_concurrent_dedup_factor",
    "peak_concurrent_refcount_match_rate",
    "block_size", "total_gpu_blocks", "mean_newly_allocated_blocks",
    "used_block_high_water", "minimum_free_blocks", "mean_scheduler_wait_ms",
    "primer_latency_ms", "preemption_count", "claim_boundary",
]


def load_new_events(path: Path, start_size: int) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        handle.seek(start_size)
        data = handle.read().decode("utf-8", errors="replace")
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def fit_shared_text(tokenizer: Any, target_tokens: int) -> str:
    unit = "Stable enterprise repository context: function contract state transition invariant. "
    text = unit * max(1, target_tokens // 8 + 16)
    ids = tokenizer.encode(text, add_special_tokens=False)[:target_tokens]
    return tokenizer.decode(ids, skip_special_tokens=True)


def messages_for(policy: str, shared: str, index: int, marker: str, cell_id: str = "") -> list[dict[str, str]]:
    """Build token-identical A/B prompts except for the legal segment order.

    ``policy`` and ``cell_id`` remain API-side metadata only.  They must never
    appear in prompt text because that would make a prefix-cache A/B comparison
    differ in content as well as layout.
    """
    system = "Follow the user exactly."
    observation = f"[UNIQUE_TOOL_OBS] tenant={index}; marker={marker}."
    query = "Return exactly the marker from UNIQUE_TOOL_OBS. /no_think"
    if policy == "raw-order":
        content = f"{observation}\n\n[SHARED_CONTEXT]\n{shared}\n\n{query}"
    else:
        content = f"[SHARED_CONTEXT]\n{shared}\n\n{observation}\n\n{query}"
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def run_request(args: argparse.Namespace, policy: str, shared: str, index: int, primer: bool = False) -> dict[str, Any]:
    marker = f"M{index}X"
    result = send_chat_stream(
        args.base_url, args.model, messages_for(policy, shared, index, marker, args.cell_id),
        args.max_tokens, args.timeout, f"{args.cell_id}-{index}",
    )
    result["session_index"] = index
    result["quality_sanity"] = marker in str(result.get("output_text", ""))
    result["primer"] = primer
    # This signature is deliberately order-insensitive and policy-neutral.
    parts = sorted(["Follow the user exactly.", shared, f"[UNIQUE_TOOL_OBS] tenant={index}; marker={marker}.", "Return exactly the marker from UNIQUE_TOOL_OBS. /no_think"])
    result["content_multiset_sha256"] = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return result


def join_events(results: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event") == "prefix_cache_request_observation":
            observations.setdefault(str(event.get("request_id")), []).append(event)
    rows = []
    for result in results:
        group = observations.get(str(result.get("request_id")), [])
        initial = next((event for event in group if event.get("initial_prefill_observation")), {})
        rows.append({
            **result,
            "prompt_tokens": initial.get("prompt_tokens", ""),
            "prefix_hit_tokens": initial.get("prefix_hit_tokens", ""),
            "reused_physical_blocks": initial.get("reused_physical_blocks", ""),
            # Initial prompt allocation only. Later decode allocations belong
            # to request growth and must not be reported as fresh prompt copies.
            "newly_allocated_blocks": initial.get("newly_allocated_blocks", ""),
            "physical_block_ids": initial.get("physical_block_ids", []),
            "physical_block_refcounts": initial.get("physical_block_refcounts", []),
            "block_size": initial.get("block_size", ""),
            "total_gpu_blocks": initial.get("total_gpu_blocks", ""),
            "used_gpu_blocks": max((int(event.get("used_gpu_blocks") or 0) for event in group), default=0),
            "free_gpu_blocks": min((int(event.get("free_gpu_blocks") or 0) for event in group), default=0),
            "scheduler_wait_ms": initial.get("scheduler_wait_ms", ""),
        })
    return rows


def concurrent_snapshot_stats(events: list[dict[str, Any]]) -> dict[str, float]:
    """Return peak same-snapshot sharing facts emitted by the guarded probe."""
    snapshots = [event for event in events if event.get("event") == "prefix_cache_concurrent_snapshot"]
    best = {
        "peak_concurrent_shared_blocks": 0.0,
        "peak_concurrent_logical_refs": 0.0,
        "peak_concurrent_unique_blocks": 0.0,
        "peak_concurrent_dedup_factor": 0.0,
        "peak_concurrent_refcount_match_rate": 0.0,
    }
    for snapshot in snapshots:
        counts = [int(value) for value in snapshot.get("shared_block_request_counts", [])]
        refcounts = [int(value) for value in snapshot.get("shared_block_refcounts", [])]
        if not counts:
            continue
        logical = sum(counts)
        unique = len(counts)
        factor = logical / unique if unique else 0.0
        matched = sum(1 for count, refcount in zip(counts, refcounts) if refcount >= count)
        match_rate = matched / unique if unique else 0.0
        candidate = (factor, logical, unique)
        current = (best["peak_concurrent_dedup_factor"], best["peak_concurrent_logical_refs"], best["peak_concurrent_unique_blocks"])
        if candidate > current:
            best = {
                "peak_concurrent_shared_blocks": float(unique),
                "peak_concurrent_logical_refs": float(logical),
                "peak_concurrent_unique_blocks": float(unique),
                "peak_concurrent_dedup_factor": float(factor),
                "peak_concurrent_refcount_match_rate": float(match_rate),
            }
    return best


def summarize(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    primer_latency: float,
    concurrent_stats: dict[str, float] | None = None,
) -> dict[str, Any]:
    measured = [row for row in rows if not row.get("primer")]
    successful = [row for row in measured if row.get("success")]
    reused_ids = []
    logical = 0
    total_blocks = 0
    total_new_blocks = 0
    for row in successful:
        reused = int(row.get("reused_physical_blocks") or 0)
        ids = list(row.get("physical_block_ids") or [])
        reused_ids.extend(ids[:reused])
        logical += reused
        prompt_blocks = max(1, (int(row.get("prompt_tokens") or 0) + 15) // 16)
        total_blocks += prompt_blocks
        # Initial physical demand is the non-reused suffix. Later decode
        # iterations must not be counted as fresh prompt copies.
        total_new_blocks += max(0, prompt_blocks - reused)
    unique = len(set(reused_ids))
    effective_unique = unique + total_new_blocks
    ttfts = [float(row.get("ttft_ms") or 0) for row in successful]
    return {
        "experiment": args.experiment,
        "cell_id": args.cell_id,
        "policy": args.policy,
        "shared_target_tokens": args.shared_target_tokens,
        "sessions": args.sessions,
        "completed_requests": len(successful),
        "completion_rate": len(successful) / len(measured) if measured else 0.0,
        "quality_sanity_rate": sum(bool(row.get("quality_sanity")) for row in successful) / len(successful) if successful else 0.0,
        "mean_ttft_ms": statistics.mean(ttfts) if ttfts else 0.0,
        "p95_ttft_ms": percentile(ttfts, .95),
        "mean_prefix_hit_tokens": statistics.mean(float(row.get("prefix_hit_tokens") or 0) for row in successful) if successful else 0.0,
        "logical_reused_prefix_blocks": logical,
        "unique_reused_physical_blocks": unique,
        "dedup_factor": logical / unique if unique else 0.0,
        "shared_block_fraction": logical / total_blocks if total_blocks else 0.0,
        "unique_physical_blocks_effective": effective_unique,
        "effective_dedup_factor": total_blocks / effective_unique if effective_unique else 0.0,
        **(concurrent_stats or concurrent_snapshot_stats([])),
        "block_size": max((int(row.get("block_size") or 0) for row in successful), default=0),
        "total_gpu_blocks": max((int(row.get("total_gpu_blocks") or 0) for row in successful), default=0),
        "mean_newly_allocated_blocks": statistics.mean(
            float(row.get("newly_allocated_blocks") or 0) for row in successful
        ) if successful else 0.0,
        "used_block_high_water": max((int(row.get("used_gpu_blocks") or 0) for row in successful), default=0),
        "minimum_free_blocks": min((int(row.get("free_gpu_blocks") or 0) for row in successful), default=0),
        "mean_scheduler_wait_ms": statistics.mean(float(row.get("scheduler_wait_ms") or 0) for row in successful) if successful else 0.0,
        "primer_latency_ms": primer_latency,
        "preemption_count": "unavailable_without_preemption_probe",
        "claim_boundary": "Real vLLM V1 request block IDs and native prefix-cache observations; no nvidia-smi VRAM deduction claim.",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str], append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a" if append else "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists or not append:
            writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("warm", "cold"), required=True)
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--shared-target-tokens", type=int, required=True)
    parser.add_argument("--sessions", type=int, required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    shared = fit_shared_text(tokenizer, args.shared_target_tokens)
    start_size = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    primer_result = None
    if args.experiment == "warm" or args.policy == "caposc-singleflight":
        primer_result = run_request(args, "contractkv-caposc" if args.policy == "caposc-singleflight" else args.policy, shared, -1, True)
    fanout_policy = "contractkv-caposc" if args.policy == "caposc-singleflight" else args.policy
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.sessions) as pool:
        results = list(pool.map(lambda index: run_request(args, fanout_policy, shared, index), range(args.sessions)))
    time.sleep(.5)
    all_results = ([primer_result] if primer_result else []) + results
    new_events = load_new_events(args.metrics_events, start_size)
    rows = join_events(all_results, new_events)
    for row in rows:
        row.update({
            "experiment": args.experiment, "cell_id": args.cell_id,
            "policy": args.policy, "shared_target_tokens": args.shared_target_tokens,
            "sessions": args.sessions,
        })
    summary = summarize(
        rows, args,
        float(primer_result.get("total_latency_ms") or 0) if primer_result else 0.0,
        concurrent_snapshot_stats(new_events),
    )
    write_csv(args.raw_output, rows, RAW_FIELDS, args.append)
    write_csv(args.summary_output, [summary], SUMMARY_FIELDS, args.append)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["completion_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
