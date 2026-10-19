#!/usr/bin/env python3
"""Run Phase 5 trace-level policy evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.cslo_solver_v0 import make_cost_lookup, make_risk_lookup, read_csv, read_jsonl, write_jsonl
from scripts.policies.common import (
    contractkv_indep,
    contractkv_joint,
    full_recompute,
    offload_only,
    prefix_reuse_only,
    quant_only,
    repair_only,
)


POLICIES: dict[str, Callable[..., dict[str, Any]]] = {
    "Full-Recompute": full_recompute,
    "Prefix-Reuse-Only": prefix_reuse_only,
    "Quantization-Only": quant_only,
    "Offload-Only": offload_only,
    "Repair-Only": repair_only,
    "ContractKV-Indep": contractkv_indep,
    "ContractKV-Joint": contractkv_joint,
}

EVAL_FIELDS = [
    "dataset",
    "quality_budget",
    "slo_budget_ms",
    "policy",
    "num_traces",
    "admission_rate",
    "mean_estimated_latency_ms",
    "p95_estimated_latency_ms",
    "mean_estimated_quality_risk",
    "p95_estimated_quality_risk",
    "quality_budget_violation_rate",
    "slo_violation_rate",
    "estimated_memory_saving_mb",
    "joint_win_rate_over_indep",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * pct
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    frac = index - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def aggregate_policy_metrics(rows: list[dict[str, Any]], quality_budget: float, slo_budget_ms: float) -> dict[str, Any]:
    latencies = [float(row["total_estimated_latency_ms"]) for row in rows]
    risks = [float(row["total_estimated_risk"]) for row in rows]
    memory = [float(row["estimated_memory_saving_mb"]) for row in rows]
    return {
        "num_traces": len(rows),
        "admission_rate": round(sum(1 for row in rows if bool(row["admitted"])) / max(len(rows), 1), 6),
        "mean_estimated_latency_ms": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "p95_estimated_latency_ms": round(percentile(latencies, 0.95), 6),
        "mean_estimated_quality_risk": round(statistics.mean(risks), 6) if risks else 0.0,
        "p95_estimated_quality_risk": round(percentile(risks, 0.95), 6),
        "quality_budget_violation_rate": round(sum(1 for risk in risks if risk > quality_budget) / max(len(risks), 1), 6),
        "slo_violation_rate": round(sum(1 for latency in latencies if latency > slo_budget_ms) / max(len(latencies), 1), 6),
        "estimated_memory_saving_mb": round(statistics.mean(memory), 6) if memory else 0.0,
    }


def joint_win_rate(joint_rows: list[dict[str, Any]], indep_rows: list[dict[str, Any]]) -> float:
    indep_by_sample = {(row["dataset"], row["task"], row["sample_id"]): row for row in indep_rows}
    wins = 0
    total = 0
    for row in joint_rows:
        key = (row["dataset"], row["task"], row["sample_id"])
        indep = indep_by_sample.get(key)
        if not indep:
            continue
        total += 1
        row_admitted = bool(row["admitted"])
        indep_admitted = bool(indep["admitted"])
        if row_admitted and not indep_admitted:
            wins += 1
        elif row_admitted == indep_admitted and (
            float(row["total_estimated_risk"]) < float(indep["total_estimated_risk"])
            or float(row["total_estimated_latency_ms"]) < float(indep["total_estimated_latency_ms"])
        ):
            wins += 1
    return round(wins / total, 6) if total else 0.0


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/risk_ledger/quality_risk_summary_v0.csv"))
    parser.add_argument("--cost-table", type=Path, default=Path("results/cost/segment_action_cost_table_v0.csv"))
    parser.add_argument("--eval-csv", type=Path, default=Path("results/controller/trace_policy_eval_v0.csv"))
    parser.add_argument("--decisions-jsonl", type=Path, default=Path("results/controller/trace_policy_decisions_v0.jsonl"))
    parser.add_argument("--datasets", default="RULER,LongBench,RepoBench")
    parser.add_argument("--quality-budgets", default="0.01,0.02,0.05")
    parser.add_argument("--slo-budgets-ms", default="100,200,500")
    args = parser.parse_args()

    samples = read_jsonl(args.samples)
    risk_lookup = make_risk_lookup(read_csv(args.risk_summary))
    cost_lookup = make_cost_lookup(read_csv(args.cost_table))
    datasets = [item for item in args.datasets.split(",") if item]
    quality_budgets = [float(item) for item in args.quality_budgets.split(",") if item]
    slo_budgets = [float(item) for item in args.slo_budgets_ms.split(",") if item]
    all_decisions = []
    eval_rows = []

    for dataset in datasets:
        dataset_samples = [sample for sample in samples if sample["dataset"] == dataset]
        for quality_budget in quality_budgets:
            for slo_budget in slo_budgets:
                decisions_by_policy = {}
                for policy_name, policy_fn in POLICIES.items():
                    decisions = [
                        policy_fn(sample, risk_lookup, cost_lookup, quality_budget, slo_budget)
                        for sample in dataset_samples
                    ]
                    for decision in decisions:
                        decision["quality_budget"] = quality_budget
                        decision["slo_budget_ms"] = slo_budget
                    decisions_by_policy[policy_name] = decisions
                    all_decisions.extend(decisions)
                joint_rate = joint_win_rate(decisions_by_policy["ContractKV-Joint"], decisions_by_policy["ContractKV-Indep"])
                for policy_name, decisions in decisions_by_policy.items():
                    metrics = aggregate_policy_metrics(decisions, quality_budget, slo_budget)
                    eval_rows.append(
                        {
                            "dataset": dataset,
                            "quality_budget": quality_budget,
                            "slo_budget_ms": slo_budget,
                            "policy": policy_name,
                            **metrics,
                            "joint_win_rate_over_indep": joint_rate if policy_name == "ContractKV-Joint" else "",
                        }
                    )

    write_jsonl(args.decisions_jsonl, all_decisions)
    write_csv(args.eval_csv, EVAL_FIELDS, eval_rows)
    print(f"eval_rows={len(eval_rows)}")
    print(f"decision_rows={len(all_decisions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
