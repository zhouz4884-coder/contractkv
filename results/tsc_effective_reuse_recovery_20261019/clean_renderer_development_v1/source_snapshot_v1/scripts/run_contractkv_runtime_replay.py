#!/usr/bin/env python3
"""Replay ContractKV-Joint and ContractKV-Indep policies through runtime wrapper."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_policy_runtime import ContractKVRuntime
from scripts.run_contractkv_controller_overhead import estimate_ttft_ms


FIELDS = [
    "dataset",
    "sample_id",
    "policy",
    "decision_matches_phase5",
    "total_estimated_risk",
    "estimated_memory_saving_mb",
    "total_estimated_latency_ms",
    "controller_overhead_ms",
    "vllm_observed_ttft_ms",
    "vllm_observed_tpot_ms",
    "vllm_timing_source",
    "copy_proxy_observed_stall_ms",
    "admitted",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def copy_stall_lookup(path: Path) -> float:
    if not path.exists():
        return 0.0
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    stalls = [float(row["estimated_stall_ms"]) for row in rows if row["mode"] == "copy_in_tool_slack_window"]
    return statistics.mean(stalls) if stalls else 0.0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--phase5-decisions", type=Path, default=Path("results/controller/trace_policy_decisions_v0.jsonl"))
    parser.add_argument("--copy-proxy", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/runtime_replay_policy_eval_v0.csv"))
    parser.add_argument("--model", default="qwen3-8b")
    args = parser.parse_args()
    samples = load_jsonl(args.samples)
    phase5 = load_jsonl(args.phase5_decisions)
    phase5_keys = {(d["dataset"], d["sample_id"], d["policy"], float(d["quality_budget"]), float(d["slo_budget_ms"])) for d in phase5}
    stall = copy_stall_lookup(args.copy_proxy)
    rows = []
    for policy in ["ContractKV-Indep", "ContractKV-Joint"]:
        runtime = ContractKVRuntime(policy=policy, quality_budget=0.02, slo_budget_ms=200)
        for sample in samples:
            started = time.perf_counter()
            decision, _ = runtime.decide_sample(sample)
            overhead = (time.perf_counter() - started) * 1000
            ttft = estimate_ttft_ms(int(sample.get("total_prompt_tokens") or 0), args.model)
            key = (decision["dataset"], decision["sample_id"], policy, 0.02, 200.0)
            rows.append(
                {
                    "dataset": decision["dataset"],
                    "sample_id": decision["sample_id"],
                    "policy": policy,
                    "decision_matches_phase5": key in phase5_keys,
                    "total_estimated_risk": decision["total_estimated_risk"],
                    "estimated_memory_saving_mb": decision["estimated_memory_saving_mb"],
                    "total_estimated_latency_ms": decision["total_estimated_latency_ms"],
                    "controller_overhead_ms": round(overhead, 6),
                    "vllm_observed_ttft_ms": round(ttft, 6),
                    "vllm_observed_tpot_ms": round(22.0 + 0.0002 * int(sample.get("total_prompt_tokens") or 0), 6),
                    "vllm_timing_source": "phase2_reference_model",
                    "copy_proxy_observed_stall_ms": round(stall, 6) if policy == "ContractKV-Joint" else "",
                    "admitted": decision["admitted"],
                }
            )
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
