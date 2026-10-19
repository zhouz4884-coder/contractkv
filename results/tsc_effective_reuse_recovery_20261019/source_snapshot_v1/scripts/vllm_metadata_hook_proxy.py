#!/usr/bin/env python3
"""Build vLLM-adjacent ContractKV request metadata logs for Phase 9A."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_policy_runtime import ContractKVRuntime


POLICIES = ["No-Contract", "ContractKV-Indep", "ContractKV-Joint"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_metadata_logs(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sample_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": trace["dataset"],
        "task": trace.get("task", ""),
        "sample_id": str(trace.get("sample_id", "")),
        "segments": trace.get("segments", []),
        "total_prompt_tokens": int(trace.get("prompt_tokens") or 0),
        "metadata": {"trace_id": trace["trace_id"]},
    }


def no_contract_decision(trace: dict[str, Any], quality_budget: float, slo_budget_ms: float) -> dict[str, Any]:
    return {
        "sample_id": str(trace.get("sample_id", "")),
        "dataset": trace["dataset"],
        "task": trace.get("task", ""),
        "policy": "No-Contract",
        "segments": [
            {
                "type": segment.get("type", "UNKNOWN"),
                "tokens": int(segment.get("token_count") or 0),
                "selected_action": {"reuse": "default_vllm", "repair": "none", "precision": "fp16", "placement": "vram"},
                "action_plan": "vllm_default",
                "estimated_risk": 0.0,
                "estimated_latency_ms": 0.0,
                "estimated_memory_delta_mb": 0.0,
            }
            for segment in trace.get("segments", [])
        ],
        "total_estimated_risk": 0.0,
        "total_estimated_latency_ms": 0.0,
        "estimated_memory_saving_mb": 0.0,
        "slo_budget_ms": slo_budget_ms,
        "quality_budget": quality_budget,
        "admitted": True,
    }


def build_metadata_record(
    trace: dict[str, Any],
    decision: dict[str, Any],
    policy: str,
    request_index: int,
    controller_timings: dict[str, float] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    segments = trace.get("segments", [])
    decision_segments = decision.get("segments", [])
    controller_timings = controller_timings or {}
    row = {
        "schema_version": "phase9_metadata_v0",
        "request_id": f"{policy}-{trace['trace_id']}",
        "trace_id": trace["trace_id"],
        "request_index": request_index,
        "policy": policy,
        "dataset": trace["dataset"],
        "task": trace.get("task", ""),
        "sample_id": str(trace.get("sample_id", "")),
        "prompt_tokens": int(trace.get("prompt_tokens") or 0),
        "segment_list": [
            {
                "segment_id": f"s{i}",
                "type": segment.get("type", "UNKNOWN"),
                "token_count": int(segment.get("token_count") or 0),
            }
            for i, segment in enumerate(segments)
        ],
        "segment_token_counts": [int(segment.get("token_count") or 0) for segment in segments],
        "risk_budget": float(decision.get("quality_budget", 0.0)),
        "slo_budget_ms": float(decision.get("slo_budget_ms", trace.get("slo_ttft_ms", 0))),
        "tool_slack_ms": float(trace.get("tool_slack_ms", 0.0)),
        "estimated_risk": float(decision.get("total_estimated_risk", 0.0)),
        "admitted": bool(decision.get("admitted", False)),
        "decision_plan": decision_segments,
        "controller_timings_ms": controller_timings,
        "openai_response_format": "unchanged",
        "vllm_adjacency_level": "request_metadata_sidecar",
        "real_kv_cache_movement": False,
    }
    row["metadata_build_ms"] = (time.perf_counter() - started) * 1000
    row["controller_overhead_ms"] = row["metadata_build_ms"] + sum(float(v) for v in controller_timings.values())
    return row


def build_metadata_logs(
    traces: list[dict[str, Any]],
    policies: list[str],
    quality_budget: float,
    slo_budget_ms: float,
) -> list[dict[str, Any]]:
    runtimes = {
        policy: ContractKVRuntime(policy=policy, quality_budget=quality_budget, slo_budget_ms=slo_budget_ms)
        for policy in policies
        if policy != "No-Contract"
    }
    rows = []
    for policy in policies:
        for index, trace in enumerate(traces):
            if policy == "No-Contract":
                decision = no_contract_decision(trace, quality_budget, slo_budget_ms)
                timings = {}
            else:
                decision, timings = runtimes[policy].decide_sample(sample_from_trace(trace))
            rows.append(build_metadata_record(trace, decision, policy, index, timings))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/vllm_metadata_hook_logs_v0.jsonl"))
    parser.add_argument("--policies", default="No-Contract,ContractKV-Indep,ContractKV-Joint")
    parser.add_argument("--quality-budget", type=float, default=0.02)
    parser.add_argument("--slo-budget-ms", type=float, default=200.0)
    args = parser.parse_args()
    policies = [item for item in args.policies.split(",") if item]
    rows = build_metadata_logs(load_jsonl(args.trace), policies, args.quality_budget, args.slo_budget_ms)
    write_metadata_logs(args.output, rows)
    print(f"metadata_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
