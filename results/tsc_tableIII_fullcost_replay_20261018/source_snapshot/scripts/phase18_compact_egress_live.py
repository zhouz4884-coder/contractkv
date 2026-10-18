#!/usr/bin/env python3
"""Exercise the source-level ContractKV compact verification channel."""

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

from scripts.contractkv_pstp import lcp_length
from scripts.phase17_live_common import build_layout, generate_raw, tokenize


def digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


async def post(session: Any, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    async with session.post(url, json=payload) as response:
        body = await response.read()
        elapsed = (time.perf_counter() - started) * 1000
        if body:
            try:
                value = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                value = {"detail": body[:500].decode(errors="replace")}
        else:
            value = {}
        return {
            "status": response.status,
            "bytes": len(body),
            "elapsed_ms": elapsed,
            "body": value,
        }


async def normal_regression(args: argparse.Namespace, session: Any) -> list[dict[str, Any]]:
    rows = []
    for endpoint, count in (("chat/completions", args.normal_requests),
                            ("completions", args.normal_requests)):
        for index in range(count):
            stream = index % 2 == 1
            if endpoint.startswith("chat"):
                payload = {
                    "model": args.model,
                    "messages": [{"role": "user", "content": "Reply OK."}],
                    "max_tokens": 2,
                    "temperature": 0,
                    "stream": stream,
                    "logprobs": index % 4 >= 2,
                    "top_logprobs": 2 if index % 4 >= 2 else None,
                    "request_id": f"c3-normal-chat-{index}",
                }
            else:
                payload = {
                    "model": args.model,
                    "prompt": "Reply OK.",
                    "max_tokens": 2,
                    "temperature": 0,
                    "stream": stream,
                    "logprobs": 2 if index % 4 >= 2 else None,
                    "prompt_logprobs": (2 if not stream and index % 8 >= 4
                                        else None),
                    "request_id": f"c3-normal-completion-{index}",
                }
            payload = {key: value for key, value in payload.items()
                       if value is not None}
            started = time.perf_counter()
            try:
                async with session.post(args.base_url + "/" + endpoint,
                                        json=payload) as response:
                    body = await response.read()
                    success = response.status == 200 and bool(body)
                    status = response.status
                    error = "" if success else body[:300].decode(errors="replace")
            except Exception as exc:
                success, status, error = False, 0, repr(exc)
            rows.append({
                "endpoint": endpoint,
                "stream": stream,
                "logprobs": bool(payload.get("logprobs")),
                "prompt_logprobs": bool(payload.get("prompt_logprobs")),
                "success": success,
                "status": status,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "error": error,
            })
    return rows


def prepare_payload(args: argparse.Namespace, case_id: str) -> dict[str, Any]:
    layout = build_layout(case_id, prefix_nonce="phase18-c3-shared")
    raw = generate_raw(args.base_url, args.model,
                       f"c3-raw-{case_id}", layout["raw_messages"], args.timeout)
    stable_ids = tokenize(args.base_url, args.model,
                          layout["stable_messages"], False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model,
                             layout["candidate_messages"], True, args.timeout)
    prompt_ids = candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]]
    return {
        "request_id": f"c3-verify-{case_id}",
        "prompt_token_ids": prompt_ids,
        "txn_id": f"txn-{case_id}",
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


async def compact_smoke(args: argparse.Namespace, session: Any,
                        base: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    cases.append(("pass", dict(base, request_id="c3-smoke-pass", txn_id="txn-pass")))
    fail = dict(base, request_id="c3-smoke-fail", txn_id="txn-fail")
    fail["reference_raw_margins"] = [value + 100.0
                                     for value in base["reference_raw_margins"]]
    cases.append(("fail", fail))
    incomplete = dict(base, request_id="c3-smoke-incomplete", txn_id="txn-incomplete")
    incomplete["reference_raw_margins"] = []
    cases.append(("incomplete", incomplete))
    mismatch = dict(base, request_id="c3-smoke-mismatch", txn_id="txn-mismatch",
                    policy_hash="wrong-policy-hash")
    cases.append(("manifest_mismatch", mismatch))
    rows = []
    for name, payload in cases:
        result = await post(session, args.api_root + "/v1/contractkv/verify", payload)
        body = result["body"]
        rows.append({
            "case": name,
            "status": result["status"],
            "response_bytes": result["bytes"],
            "latency_ms": result["elapsed_ms"],
            "decision": body.get("verify_decision", "HTTP_ERROR"),
            "txn_state": body.get("txn_state", ""),
            "committed_tokens": body.get("committed_tokens", 0),
            "certificate_issued": body.get("certificate_issued", False),
            "failure_reason": body.get("failure_reason", body.get("detail", "")),
            "raw_margin_q05": body.get("raw_margin_q05"),
            "candidate_margin_q05": body.get("candidate_margin_q05"),
            "degradation_q95": body.get("degradation_q95"),
            "contains_prompt_logprobs": "prompt_logprobs" in json.dumps(body),
        })
    return rows


async def lifecycle(args: argparse.Namespace, session: Any,
                    base: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index in range(args.sequential_verify):
        payload = dict(base, request_id=f"c3-seq-{index}", txn_id=f"txn-seq-{index}")
        result = await post(session, args.api_root + "/v1/contractkv/verify", payload)
        rows.append({"mode": "sequential", "index": index,
                     "status": result["status"], "bytes": result["bytes"],
                     "latency_ms": result["elapsed_ms"],
                     "decision": result["body"].get("verify_decision", "")})

    async def one(index: int) -> dict[str, Any]:
        payload = dict(base, request_id=f"c3-concurrent-{index}",
                       txn_id=f"txn-concurrent-{index}")
        result = await post(session, args.api_root + "/v1/contractkv/verify", payload)
        return {"mode": "concurrent", "index": index,
                "status": result["status"], "bytes": result["bytes"],
                "latency_ms": result["elapsed_ms"],
                "decision": result["body"].get("verify_decision", "")}

    rows.extend(await asyncio.gather(*(one(index)
                                      for index in range(args.concurrent_verify))))
    duplicate = dict(base, request_id="c3-duplicate", txn_id="txn-duplicate")
    duplicate_results = await asyncio.gather(
        post(session, args.api_root + "/v1/contractkv/verify", duplicate),
        post(session, args.api_root + "/v1/contractkv/verify", duplicate),
        return_exceptions=True,
    )
    for index, result in enumerate(duplicate_results):
        if isinstance(result, Exception):
            rows.append({"mode": "duplicate", "index": index, "status": 0,
                         "bytes": 0, "latency_ms": 0, "decision": repr(result)})
        else:
            rows.append({"mode": "duplicate", "index": index,
                         "status": result["status"], "bytes": result["bytes"],
                         "latency_ms": result["elapsed_ms"],
                         "decision": result["body"].get("verify_decision", "")})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(timeout=timeout,
                                     connector=aiohttp.TCPConnector(limit=64)) as session:
        normal = await normal_regression(args, session)
        base = prepare_payload(args, "base")
        full_wire = await post(session, args.base_url + "/completions", {
            "model": args.model,
            "prompt": base["prompt_token_ids"],
            "max_tokens": 1,
            "temperature": 0,
            "prompt_logprobs": 2,
            "return_token_ids": True,
            "request_id": "c3-full-wire-reference",
        })
        smoke = await compact_smoke(args, session, base)
        lifecycle_rows = await lifecycle(args, session, base)
        async with session.get(args.api_root + "/v1/contractkv/stats") as response:
            router_stats = json.loads(await response.read())
    write_csv(args.normal_output, normal)
    write_csv(args.smoke_output, smoke)
    write_csv(args.lifecycle_output, lifecycle_rows)
    compact_bytes = [int(row["response_bytes"]) for row in smoke]
    return {
        "normal_requests": len(normal),
        "normal_success_rate": sum(bool(row["success"]) for row in normal) / max(len(normal), 1),
        "smoke": smoke,
        "sequential_success": sum(row["status"] == 200 for row in lifecycle_rows
                                  if row["mode"] == "sequential"),
        "concurrent_success": sum(row["status"] == 200 for row in lifecycle_rows
                                  if row["mode"] == "concurrent"),
        "compact_response_mean_bytes": statistics.mean(compact_bytes),
        "compact_response_max_bytes": max(compact_bytes),
        "full_prompt_logprob_http_bytes": full_wire["bytes"],
        "full_prompt_logprob_http_status": full_wire["status"],
        "http_payload_reduction_ratio": (
            full_wire["bytes"] / max(statistics.mean(compact_bytes), 1)),
        "router_stats": router_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8023/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--policy-hash", default="phase18-c3-policy")
    parser.add_argument("--normal-requests", type=int, default=100)
    parser.add_argument("--sequential-verify", type=int, default=100)
    parser.add_argument("--concurrent-verify", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--normal-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_normal_regression_v0.csv"))
    parser.add_argument("--smoke-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_compact_smoke_v0.csv"))
    parser.add_argument("--lifecycle-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_lifecycle_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_gate_summary_v0.json"))
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    args.api_root = args.base_url[:-3] if args.base_url.endswith("/v1") else args.base_url
    summary = asyncio.run(run(args))
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["normal_success_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
