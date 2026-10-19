#!/usr/bin/env python3
"""Request-adjacent prefetch/offload orchestrator proxy for Phase 9C."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.compute_tool_slack_sensitivity import load_copy_sizes


FIELDS = [
    "request_id",
    "trace_id",
    "policy",
    "dataset",
    "sample_id",
    "prompt_tokens",
    "tool_slack_ms",
    "predicted_transfer_size_mb",
    "copy_strategy",
    "copy_ms",
    "residual_stall_ms",
    "phase8_boundary_matched",
    "real_kv_cache_movement",
    "note",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def estimate_transfer_size_mb(trace: dict[str, Any]) -> int:
    max_segment_tokens = max((int(segment.get("token_count") or 0) for segment in trace.get("segments", [])), default=0)
    if max_segment_tokens >= 4000:
        return 1024
    if max_segment_tokens >= 1000:
        return 512
    if max_segment_tokens >= 500:
        return 256
    return 128


def choose_copy_strategy(tool_slack_ms: float, transfer_size_mb: int) -> str:
    if tool_slack_ms <= 0:
        return "copy_now"
    if transfer_size_mb >= 1024 and tool_slack_ms < 50:
        return "skip"
    if tool_slack_ms >= 50 and transfer_size_mb <= 512:
        return "defer_to_slack"
    if tool_slack_ms >= 100:
        return "defer_to_slack"
    return "copy_now"


def residual_stall_ms(copy_ms: float, tool_slack_ms: float, strategy: str) -> float:
    if strategy == "skip":
        return 0.0
    if strategy == "defer_to_slack":
        return max(0.0, copy_ms - tool_slack_ms)
    return copy_ms


def request_id(policy: str, trace: dict[str, Any]) -> str:
    return f"{policy}-{trace['trace_id']}"


def _phase8_boundary(size_mb: int, slack_ms: float, stall: float) -> bool:
    if size_mb <= 512 and slack_ms >= 50:
        return stall == 0.0
    if size_mb >= 1024 and slack_ms >= 100:
        return stall == 0.0
    return True


def run_orchestrator_replay(
    traces: list[dict[str, Any]],
    copy_ms_by_size: dict[int, float],
    policies: list[str] | None = None,
) -> list[dict[str, Any]]:
    policies = policies or ["ContractKV-Joint"]
    rows = []
    for policy in policies:
        for trace in traces:
            size = estimate_transfer_size_mb(trace)
            copy_ms = float(copy_ms_by_size.get(size, 0.0))
            if policy == "No-Contract":
                strategy = "skip"
            elif policy == "ContractKV-Indep":
                strategy = "copy_now"
            else:
                strategy = choose_copy_strategy(float(trace.get("tool_slack_ms", 0.0)), size)
            stall = residual_stall_ms(copy_ms, float(trace.get("tool_slack_ms", 0.0)), strategy)
            rows.append(
                {
                    "request_id": request_id(policy, trace),
                    "trace_id": trace["trace_id"],
                    "policy": policy,
                    "dataset": trace["dataset"],
                    "sample_id": str(trace.get("sample_id", "")),
                    "prompt_tokens": int(trace.get("prompt_tokens") or 0),
                    "tool_slack_ms": float(trace.get("tool_slack_ms", 0.0)),
                    "predicted_transfer_size_mb": size,
                    "copy_strategy": strategy,
                    "copy_ms": round(copy_ms, 6),
                    "residual_stall_ms": round(stall, 6),
                    "phase8_boundary_matched": _phase8_boundary(size, float(trace.get("tool_slack_ms", 0.0)), stall),
                    "real_kv_cache_movement": False,
                    "note": "request_adjacent_tensor_proxy_not_real_vllm_kv_cache",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--copy-proxy", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/vllm_prefetch_orchestrator_proxy_v0.csv"))
    parser.add_argument("--policies", default="No-Contract,ContractKV-Indep,ContractKV-Joint")
    args = parser.parse_args()
    policies = [item for item in args.policies.split(",") if item]
    rows = run_orchestrator_replay(load_jsonl(args.trace), load_copy_sizes(args.copy_proxy), policies)
    write_csv(args.output, rows)
    print(f"orchestrator_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
