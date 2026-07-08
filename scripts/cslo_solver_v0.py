#!/usr/bin/env python3
"""CSLO trace-level ContractKV solver v0."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RISK_ACTION_MAP = {
    "reuse_exact": "fp16_baseline",
    "reuse_shifted_proxy": "shifted_position_proxy",
    "repair_boundary_proxy": "boundary_repair_proxy",
    "recompute_full": "fp16_baseline",
    "precision_fp16": "fp16_baseline",
    "precision_int8_proxy": "shifted_position_proxy",
    "precision_int4_proxy": "boundary_corruption",
    "placement_vram": "fp16_baseline",
    "placement_host": "fp16_baseline",
    "prefetch_host_to_gpu": "fp16_baseline",
    "offload_gpu_to_host": "fp16_baseline",
    "evict_segment": "segment_eviction",
}

RISK_ACTION_MULTIPLIER = {
    "fp16_baseline": 0.0,
    "reuse_exact": 0.0,
    "reuse_shifted_proxy": 0.05,
    "repair_boundary_proxy": 0.02,
    "recompute_full": 0.0,
    "precision_fp16": 0.0,
    "precision_int8_proxy": 0.02,
    "precision_int4_proxy": 0.08,
    "placement_vram": 0.0,
    "placement_host": 0.0,
    "prefetch_host_to_gpu": 0.0,
    "offload_gpu_to_host": 0.0,
    "evict_segment": 1.0,
}


@dataclass(frozen=True)
class SegmentPlan:
    name: str
    actions: tuple[str, ...]
    selected_action: dict[str, str]
    estimated_risk: float
    estimated_latency_ms: float
    estimated_memory_delta_mb: float


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def make_risk_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], float]:
    lookup = {}
    for row in rows:
        key = (row["dataset"], row["task"], row["segment_type"], row["action"])
        lookup[key] = float(row["mean_quality_drop"])
    return lookup


def make_cost_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    lookup = {}
    for row in rows:
        lookup[(row["action"], row["segment_type"])] = {
            "estimated_latency_ms": float(row["estimated_latency_ms"]),
            "estimated_memory_delta_mb": float(row["estimated_memory_delta_mb"]),
            "estimated_interference_penalty_ms": float(row["estimated_interference_penalty_ms"]),
        }
    return lookup


def estimate_action_risk(
    risk_lookup: dict[tuple[str, str, str, str], float],
    dataset: str,
    task: str,
    segment_type: str,
    action: str,
) -> float:
    risk_action = RISK_ACTION_MAP.get(action, action)
    candidates = [
        (dataset, task, segment_type, risk_action),
        (dataset, task, segment_type, "fp16_baseline"),
    ]
    for key in candidates:
        if key in risk_lookup:
            return risk_lookup[key] * RISK_ACTION_MULTIPLIER.get(action, 1.0)
    matching = [value for (d, _, st, a), value in risk_lookup.items() if d == dataset and st == segment_type and a == risk_action]
    if matching:
        return (sum(matching) / len(matching)) * RISK_ACTION_MULTIPLIER.get(action, 1.0)
    matching = [value for (_, _, st, a), value in risk_lookup.items() if st == segment_type and a == risk_action]
    return (sum(matching) / len(matching)) * RISK_ACTION_MULTIPLIER.get(action, 1.0) if matching else 0.0


def _cost(cost_lookup: dict[tuple[str, str], dict[str, float]], action: str, segment_type: str, tokens: int) -> tuple[float, float]:
    row = cost_lookup.get((action, segment_type)) or cost_lookup.get((action, "RAG_CHUNK"))
    if not row:
        return 0.0, 0.0
    scale = max(tokens, 1) / 1000.0
    latency = row["estimated_latency_ms"] * scale
    memory = row["estimated_memory_delta_mb"] * scale
    return latency, memory


def build_segment_plan(
    name: str,
    action_names: tuple[str, ...],
    selected_action: dict[str, str],
    dataset: str,
    task: str,
    segment_type: str,
    tokens: int,
    risk_lookup: dict[tuple[str, str, str, str], float],
    cost_lookup: dict[tuple[str, str], dict[str, float]],
) -> SegmentPlan:
    risk = sum(estimate_action_risk(risk_lookup, dataset, task, segment_type, a) for a in action_names)
    latency = 0.0
    memory = 0.0
    for action in action_names:
        action_latency, action_memory = _cost(cost_lookup, action, segment_type, tokens)
        latency += action_latency
        memory += action_memory
    return SegmentPlan(
        name=name,
        actions=action_names,
        selected_action=selected_action,
        estimated_risk=round(risk, 6),
        estimated_latency_ms=round(latency, 4),
        estimated_memory_delta_mb=round(memory, 4),
    )


def candidate_plans(
    dataset: str,
    task: str,
    segment_type: str,
    tokens: int,
    risk_lookup: dict[tuple[str, str, str, str], float],
    cost_lookup: dict[tuple[str, str], dict[str, float]],
) -> list[SegmentPlan]:
    return [
        build_segment_plan(
            "aggressive_int4_host",
            ("reuse_exact", "precision_int4_proxy", "placement_host", "prefetch_host_to_gpu"),
            {"reuse": "exact", "repair": "none", "precision": "int4_proxy", "placement": "host_prefetch"},
            dataset,
            task,
            segment_type,
            tokens,
            risk_lookup,
            cost_lookup,
        ),
        build_segment_plan(
            "balanced_int8_repair_host",
            ("repair_boundary_proxy", "precision_int8_proxy", "placement_host", "prefetch_host_to_gpu"),
            {"reuse": "shifted_proxy", "repair": "boundary_proxy", "precision": "int8_proxy", "placement": "host_prefetch"},
            dataset,
            task,
            segment_type,
            tokens,
            risk_lookup,
            cost_lookup,
        ),
        build_segment_plan(
            "safe_fp16_vram",
            ("reuse_exact", "precision_fp16", "placement_vram"),
            {"reuse": "exact", "repair": "none", "precision": "fp16", "placement": "vram"},
            dataset,
            task,
            segment_type,
            tokens,
            risk_lookup,
            cost_lookup,
        ),
        build_segment_plan(
            "recompute_fp16_vram",
            ("recompute_full", "precision_fp16", "placement_vram"),
            {"reuse": "none", "repair": "none", "precision": "fp16", "placement": "vram"},
            dataset,
            task,
            segment_type,
            tokens,
            risk_lookup,
            cost_lookup,
        ),
    ]


def choose_joint_segment_plan(segment_type: str, tokens: int, risk_hint: float, quality_budget: float) -> SegmentPlan:
    selected_action = {"reuse": "exact", "repair": "none", "precision": "int4_proxy", "placement": "host_prefetch"}
    if risk_hint > quality_budget:
        selected_action = {"reuse": "exact", "repair": "none", "precision": "fp16", "placement": "vram"}
    return SegmentPlan("test_plan", tuple(), selected_action, risk_hint, 0.0, 0.0)


def evaluate_joint_trace(
    sample: dict[str, Any],
    risk_lookup: dict[tuple[str, str, str, str], float],
    cost_lookup: dict[tuple[str, str], dict[str, float]],
    quality_budget: float,
    slo_budget_ms: float,
    policy_name: str = "ContractKV-Joint",
) -> dict[str, Any]:
    dataset = sample["dataset"]
    task = sample["task"]
    segment_options = []
    selected_indices = []
    for segment in sample.get("segments", []):
        segment_type = segment["type"]
        tokens = int(segment.get("token_count") or 0)
        plans = candidate_plans(dataset, task, segment_type, tokens, risk_lookup, cost_lookup)
        segment_options.append((segment, plans))
        selected_indices.append(0)

    def totals() -> tuple[float, float, float]:
        risk = 0.0
        latency = 0.0
        memory = 0.0
        for (_, plans), index in zip(segment_options, selected_indices):
            plan = plans[index]
            risk += plan.estimated_risk
            latency += plan.estimated_latency_ms
            memory += plan.estimated_memory_delta_mb
        return risk, latency, memory

    for _ in range(sum(len(plans) - 1 for _, plans in segment_options)):
        total_risk, total_latency, _ = totals()
        if total_risk <= quality_budget and total_latency <= slo_budget_ms:
            break
        best_index = None
        best_score = None
        for i, (_, plans) in enumerate(segment_options):
            current_index = selected_indices[i]
            if current_index >= len(plans) - 1:
                continue
            current = plans[current_index]
            next_plan = plans[current_index + 1]
            risk_gain = max(0.0, current.estimated_risk - next_plan.estimated_risk)
            latency_gain = max(0.0, current.estimated_latency_ms - next_plan.estimated_latency_ms)
            if total_risk > quality_budget and risk_gain <= 0:
                continue
            if total_latency > slo_budget_ms and latency_gain <= 0 and total_risk <= quality_budget:
                continue
            memory_cost = max(0.001, next_plan.estimated_memory_delta_mb - current.estimated_memory_delta_mb)
            score = ((risk_gain * 1000.0) + latency_gain) / memory_cost
            if best_score is None or score > best_score:
                best_score = score
                best_index = i
        if best_index is None:
            break
        selected_indices[best_index] += 1

    segments = []
    total_risk = 0.0
    total_latency = 0.0
    total_memory = 0.0
    for (segment, plans), selected_index in zip(segment_options, selected_indices):
        plan = plans[selected_index]
        segments.append(
            {
                "type": segment["type"],
                "tokens": int(segment.get("token_count") or 0),
                "selected_action": plan.selected_action,
                "action_plan": plan.name,
                "estimated_risk": plan.estimated_risk,
                "estimated_latency_ms": plan.estimated_latency_ms,
                "estimated_memory_delta_mb": plan.estimated_memory_delta_mb,
            }
        )
        total_risk += plan.estimated_risk
        total_latency += plan.estimated_latency_ms
        total_memory += plan.estimated_memory_delta_mb

    return {
        "sample_id": str(sample.get("sample_id", "")),
        "dataset": dataset,
        "task": task,
        "policy": policy_name,
        "segments": segments,
        "total_estimated_risk": round(total_risk, 6),
        "total_estimated_latency_ms": round(total_latency, 4),
        "estimated_memory_saving_mb": round(max(0.0, -total_memory), 4),
        "slo_budget_ms": slo_budget_ms,
        "quality_budget": quality_budget,
        "admitted": total_risk <= quality_budget and total_latency <= slo_budget_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/risk_ledger/quality_risk_summary_v0.csv"))
    parser.add_argument("--cost-table", type=Path, default=Path("results/cost/segment_action_cost_table_v0.csv"))
    parser.add_argument("--decisions", type=Path, default=Path("results/controller/cslo_decisions_v0.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("results/controller/cslo_summary_v0.csv"))
    parser.add_argument("--quality-budget", type=float, default=0.02)
    parser.add_argument("--slo-budget-ms", type=float, default=200.0)
    args = parser.parse_args()

    samples = read_jsonl(args.samples)
    risk_lookup = make_risk_lookup(read_csv(args.risk_summary))
    cost_lookup = make_cost_lookup(read_csv(args.cost_table))
    decisions = [
        evaluate_joint_trace(sample, risk_lookup, cost_lookup, args.quality_budget, args.slo_budget_ms)
        for sample in samples
    ]
    write_jsonl(args.decisions, decisions)
    rows = [
        {
            "dataset": d["dataset"],
            "sample_id": d["sample_id"],
            "policy": d["policy"],
            "total_estimated_risk": d["total_estimated_risk"],
            "total_estimated_latency_ms": d["total_estimated_latency_ms"],
            "estimated_memory_saving_mb": d["estimated_memory_saving_mb"],
            "admitted": d["admitted"],
        }
        for d in decisions
    ]
    write_csv(args.summary, rows)
    print(f"decisions={len(decisions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
