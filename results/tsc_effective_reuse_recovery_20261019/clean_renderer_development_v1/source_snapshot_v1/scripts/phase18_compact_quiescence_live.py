#!/usr/bin/env python3
"""Measure foreground interference with source-level compact verification."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase16e_live_transactional_slc import messages, send_stream
from scripts.phase17_live_common import build_layout, generate_raw, tokenize
from scripts.phase17_verifier_quiescence_live import (
    RAW_FIELDS,
    SUMMARY_FIELDS,
    load_events,
    summarize,
    write_csv,
)


def digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def prepare(args: argparse.Namespace, case_id: str) -> dict[str, Any]:
    layout = build_layout(case_id, prefix_nonce=f"phase18-{args.cell}-shared")
    raw = generate_raw(args.base_url, args.model, f"{args.cell}-raw-{case_id}",
                       layout["raw_messages"], args.timeout)
    stable_ids = tokenize(args.base_url, args.model, layout["stable_messages"],
                          False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model,
                             layout["candidate_messages"], True, args.timeout)
    return {
        "request_id": f"{args.cell}-verify-{case_id}",
        "prompt_token_ids": candidate_ids + raw["token_ids"]
        + [raw["terminal_stop_token_id"]],
        "txn_id": f"txn-{args.cell}-{case_id}",
        "policy_hash": args.policy_hash,
        "policy_version": "phase18-c3-v0",
        "attestation_mode": "exact_path_stop_v1",
        "stable_prefix_end_token": lcp_length(stable_ids, candidate_ids),
        "verify_start_token": len(candidate_ids),
        "reference_answer_ids": raw["token_ids"],
        "reference_raw_margins": raw["margins"],
        "terminal_stop_token_id": raw["terminal_stop_token_id"],
        "stable_content_hash": digest(stable_ids),
        "layout_hash": digest(candidate_ids),
        "dependency_graph_hash": digest([["system", "stable"], ["stable", "query"]]),
        "timeout_s": args.timeout,
    }


async def send_verifier(session: Any, args: argparse.Namespace,
                        payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    request_id = str(payload["request_id"])
    try:
        async with session.post(args.api_root + "/v1/contractkv/verify",
                                json=payload) as response:
            body = await response.read()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {body[:200]!r}")
            value = json.loads(body)
            success = value.get("verify_decision") in {"PASS", "FAIL", "INCOMPLETE"}
        return {"success": success, "request_id": request_id, "ttft_ms": 0.0,
                "total_latency_ms": (time.perf_counter() - started) * 1000,
                "error": "" if success else repr(value), "request_class": "verifier"}
    except Exception as exc:
        return {"success": False, "request_id": request_id, "ttft_ms": 0.0,
                "total_latency_ms": (time.perf_counter() - started) * 1000,
                "error": repr(exc), "request_class": "verifier"}


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    prepared = {
        seed: [prepare(args, f"{seed}-{index}")
               for index in range(args.verifier_requests)]
        for seed in args.seeds
    }
    rows: list[dict[str, Any]] = []
    async with aiohttp.ClientSession(
            timeout=timeout, connector=aiohttp.TCPConnector(limit=256)) as session:
        for seed in args.seeds:
            conditions = ("baseline", "live_verifier") if seed % 2 == 0 else (
                "live_verifier", "baseline")
            for condition in conditions:
                code = "A" if condition == "baseline" else "B"
                for index in range(args.warmup_requests):
                    await send_stream(
                        session, args.base_url, args.model,
                        f"{args.cell}-warm-{seed}-{condition}-{index}",
                        messages(f"WARM_{seed}_{code}_{index}"), 8, 0, "warmup")
                tasks = []
                for index in range(args.active_requests):
                    tasks.append(asyncio.create_task(send_stream(
                        session, args.base_url, args.model,
                        f"{args.cell}-active-{seed}-{condition}-{index}",
                        messages(f"ACTIVE_{seed}_{code}_{index}"), 8, 0, "active")))
                    await asyncio.sleep(args.active_gap_ms / 1000)
                if condition == "live_verifier":
                    await asyncio.sleep(.001)
                    tasks.extend(asyncio.create_task(send_verifier(session, args, payload))
                                 for payload in prepared[seed])
                for result in await asyncio.gather(*tasks):
                    rows.append({
                        "seed": seed,
                        "condition": condition,
                        "request_class": result["request_class"],
                        "success": result["success"],
                        "ttft_ms": result["ttft_ms"],
                        "total_latency_ms": result["total_latency_ms"],
                        "request_id": result["request_id"],
                        "error": result["error"],
                    })
                await asyncio.sleep(.5)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8023/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--cell", choices=["C3", "C4"], required=True)
    parser.add_argument("--policy-hash", default="phase18-c3-policy")
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--active-requests", type=int, default=100)
    parser.add_argument("--verifier-requests", type=int, default=4)
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument("--active-gap-ms", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    args.api_root = args.base_url[:-3] if args.base_url.endswith("/v1") else args.base_url
    rows = asyncio.run(run(args))
    summary = summarize(args, rows, load_events(args.event_log))
    for row in summary:
        row["claim_boundary"] = (
            "Live vLLM source-level compact verification; C3 polling or C4 "
            "event-driven parking as selected by server configuration.")
    write_csv(args.raw_output, rows, RAW_FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(json.dumps(summary, indent=2))
    return 0 if all(row["gate_pass"] for row in summary) else 2


if __name__ == "__main__":
    raise SystemExit(main())
