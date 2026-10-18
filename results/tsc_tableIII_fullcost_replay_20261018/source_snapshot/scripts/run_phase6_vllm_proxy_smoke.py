#!/usr/bin/env python3
"""Run one ContractKV proxy forwarding smoke against a live vLLM endpoint."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_policy_runtime import ContractKVRuntime
from scripts.contractkv_server_proxy import ContractKVProxy


FIELDS = [
    "timestamp",
    "served_model",
    "vllm_base_url",
    "status",
    "body_has_choices",
    "output_format_preserved",
    "proxy_overhead_ms",
    "policy",
    "error_type",
    "error_message",
]


def append_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--served-model", required=True)
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/runtime/phase6a_vllm_proxy_smoke.csv"))
    parser.add_argument("--request-log", type=Path, default=Path("results/runtime/contractkv_proxy_requests.jsonl"))
    parser.add_argument("--decision-log", type=Path, default=Path("results/runtime/contractkv_decision_logs.jsonl"))
    parser.add_argument("--policy", default="ContractKV-Joint")
    args = parser.parse_args()

    runtime = ContractKVRuntime(policy=args.policy)
    proxy = ContractKVProxy(args.vllm_base_url, runtime, args.request_log, args.decision_log)
    request = {
        "model": args.served_model,
        "messages": [{"role": "user", "content": "请用一句话解释 KV cache。"}],
        "max_tokens": 64,
        "temperature": 0,
    }
    try:
        status, body, meta = proxy.handle_chat_completion(request)
        decoded = json.loads(body.decode("utf-8")) if body else {}
        has_choices = isinstance(decoded.get("choices"), list)
        row = {
            "timestamp": time.time(),
            "served_model": args.served_model,
            "vllm_base_url": args.vllm_base_url,
            "status": status,
            "body_has_choices": has_choices,
            "output_format_preserved": status == 200 and has_choices,
            "proxy_overhead_ms": round(float(meta.get("proxy_overhead_ms", 0.0)), 6),
            "policy": args.policy,
            "error_type": "none" if status == 200 and has_choices else "bad_output",
            "error_message": "" if status == 200 and has_choices else body.decode("utf-8", errors="replace")[:200],
        }
    except Exception as exc:
        row = {
            "timestamp": time.time(),
            "served_model": args.served_model,
            "vllm_base_url": args.vllm_base_url,
            "status": "",
            "body_has_choices": False,
            "output_format_preserved": False,
            "proxy_overhead_ms": "",
            "policy": args.policy,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    append_csv(args.output, row)
    print(row)
    return 0 if row["error_type"] == "none" else 1


if __name__ == "__main__":
    raise SystemExit(main())
