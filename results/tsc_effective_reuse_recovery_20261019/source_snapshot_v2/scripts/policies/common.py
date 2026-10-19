from __future__ import annotations

from typing import Any

from scripts.cslo_solver_v0 import build_segment_plan, evaluate_joint_trace


def _trace_from_fixed_actions(
    sample: dict[str, Any],
    risk_lookup: dict[tuple[str, str, str, str], float],
    cost_lookup: dict[tuple[str, str], dict[str, float]],
    quality_budget: float,
    slo_budget_ms: float,
    policy: str,
    action_names: tuple[str, ...],
    selected_action: dict[str, str],
) -> dict[str, Any]:
    segments = []
    total_risk = 0.0
    total_latency = 0.0
    total_memory = 0.0
    for segment in sample.get("segments", []):
        plan = build_segment_plan(
            policy,
            action_names,
            selected_action,
            sample["dataset"],
            sample["task"],
            segment["type"],
            int(segment.get("token_count") or 0),
            risk_lookup,
            cost_lookup,
        )
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
        "dataset": sample["dataset"],
        "task": sample["task"],
        "policy": policy,
        "segments": segments,
        "total_estimated_risk": round(total_risk, 6),
        "total_estimated_latency_ms": round(total_latency, 4),
        "estimated_memory_saving_mb": round(max(0.0, -total_memory), 4),
        "slo_budget_ms": slo_budget_ms,
        "quality_budget": quality_budget,
        "admitted": total_risk <= quality_budget and total_latency <= slo_budget_ms,
    }


def full_recompute(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "Full-Recompute",
        ("recompute_full", "precision_fp16", "placement_vram"),
        {"reuse": "none", "repair": "none", "precision": "fp16", "placement": "vram"},
    )


def prefix_reuse_only(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "Prefix-Reuse-Only",
        ("reuse_exact", "precision_fp16", "placement_vram"),
        {"reuse": "exact", "repair": "none", "precision": "fp16", "placement": "vram"},
    )


def quant_only(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "Quantization-Only",
        ("reuse_exact", "precision_int4_proxy", "placement_vram"),
        {"reuse": "exact", "repair": "none", "precision": "int4_proxy", "placement": "vram"},
    )


def offload_only(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "Offload-Only",
        ("reuse_exact", "precision_fp16", "placement_host", "prefetch_host_to_gpu"),
        {"reuse": "exact", "repair": "none", "precision": "fp16", "placement": "host_prefetch"},
    )


def repair_only(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "Repair-Only",
        ("reuse_shifted_proxy", "repair_boundary_proxy", "precision_fp16", "placement_vram"),
        {"reuse": "shifted_proxy", "repair": "boundary_proxy", "precision": "fp16", "placement": "vram"},
    )


def contractkv_indep(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return _trace_from_fixed_actions(
        sample,
        risk_lookup,
        cost_lookup,
        quality_budget,
        slo_budget_ms,
        "ContractKV-Indep",
        ("reuse_exact", "precision_int4_proxy", "placement_host", "prefetch_host_to_gpu"),
        {"reuse": "exact", "repair": "none", "precision": "int4_proxy", "placement": "host_prefetch"},
    )


def contractkv_joint(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms):
    return evaluate_joint_trace(sample, risk_lookup, cost_lookup, quality_budget, slo_budget_ms)
