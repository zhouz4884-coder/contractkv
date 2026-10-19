#!/usr/bin/env python3
"""Inject timeout, cancellation, and disconnect faults into compact verify."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase18_compact_egress_live import post, prepare_payload


async def run(args: argparse.Namespace) -> dict[str, Any]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    base = prepare_payload(args, "fault-base")
    endpoint = args.api_root + "/v1/contractkv/verify"
    events: list[dict[str, Any]] = []
    async with aiohttp.ClientSession(timeout=timeout) as session:
        timed = dict(base, request_id="c3-fault-timeout", txn_id="txn-timeout",
                     timeout_s=0.001)
        timeout_result = await post(session, endpoint, timed)
        events.append({"case": "timeout", "status": timeout_result["status"],
                       "client_cancelled": False})

        before = dict(base, request_id="c3-fault-cancel-before",
                      txn_id="txn-cancel-before")
        task = asyncio.create_task(post(session, endpoint, before))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            events.append({"case": "cancel_before", "status": 0,
                           "client_cancelled": True})

        during = dict(base, request_id="c3-fault-cancel-during",
                      txn_id="txn-cancel-during")
        task = asyncio.create_task(post(session, endpoint, during))
        await asyncio.sleep(.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            events.append({"case": "cancel_during", "status": 0,
                           "client_cancelled": True})

        disconnect = dict(base, request_id="c3-fault-disconnect",
                          txn_id="txn-disconnect")
        body = json.dumps(disconnect).encode()
        reader, writer = await asyncio.open_connection(args.host, args.port)
        writer.write(
            f"POST /v1/contractkv/verify HTTP/1.1\r\n"
            f"Host: {args.host}:{args.port}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        del reader
        events.append({"case": "frontend_disconnect", "status": 0,
                       "client_cancelled": True})

        await asyncio.sleep(2)
        async with session.get(args.api_root + "/v1/contractkv/stats") as response:
            stats = json.loads(await response.read())
        normal = await post(session, args.base_url + "/completions", {
            "model": args.model,
            "prompt": "Reply OK.",
            "max_tokens": 2,
            "temperature": 0,
            "request_id": "c3-after-fault-normal",
        })
    return {
        "events": events,
        "router_stats_after_faults": stats,
        "normal_completion_status_after_faults": normal["status"],
        "gate_pass": (
            int(stats.get("pending_futures", -1)) == 0
            and normal["status"] == 200
            and timeout_result["status"] >= 400
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8023/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--policy-hash", default="phase18-c3-policy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8023)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_lifecycle_faults_v0.json"))
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    args.api_root = args.base_url[:-3] if args.base_url.endswith("/v1") else args.base_url
    result = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
