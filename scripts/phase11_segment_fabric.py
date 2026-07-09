#!/usr/bin/env python3
"""Phase 11 Segment Lifecycle Fabric offline evaluation.

This is a control-plane evaluation, not a mixed-precision attention kernel.
It estimates when segment canonicalization, tool-slack preparation, and
action-conditioned backend selection would help before adding a real backend.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


CANONICAL_SLOT_ORDER = {
    "SYS_PROMPT": 0,
    "TOOL_SCHEMA": 1,
    "CODE_PREFIX": 2,
    "REPO_CONTEXT": 2,
    "RAG_CHUNK": 3,
    "SYNTHETIC_CONTEXT": 3,
    "CHAT_HISTORY": 4,
    "ASSISTANT_HISTORY": 4,
    "SCRATCHPAD": 5,
    "TOOL_OBSERVATION": 6,
    "USER_QUERY": 7,
}

STABLE_SLOT_TYPES = {
    "SYS_PROMPT",
    "TOOL_SCHEMA",
    "CODE_PREFIX",
    "REPO_CONTEXT",
    "RAG_CHUNK",
    "SYNTHETIC_CONTEXT",
}

LOW_RISK_COMPRESSIBLE_TYPES = {
    "CHAT_HISTORY",
    "ASSISTANT_HISTORY",
    "SCRATCHPAD",
    "TOOL_OBSERVATION",
}

HIGH_RISK_TYPES = {
    "SYS_PROMPT",
    "TOOL_SCHEMA",
    "CODE_PREFIX",
    "REPO_CONTEXT",
    "RAG_CHUNK",
    "SYNTHETIC_CONTEXT",
    "USER_QUERY",
}

FOREST_FIELDS = [
    "dataset",
    "task",
    "sample_id",
    "total_tokens_with_tool_observation",
    "stable_tokens",
    "tool_observation_tokens",
    "raw_prefix_hit_tokens",
    "canonical_slot_hit_tokens",
    "raw_prefill_tokens",
    "canonical_prefill_tokens",
    "prefill_tokens_saved",
    "raw_prefix_cache_hit_rate",
    "canonical_segment_cache_hit_rate",
    "position_policy",
    "quality_claim",
    "notes",
]

SSPP_FIELDS = [
    "prepare_action",
    "tool_slack_ms",
    "prediction_hit_rate",
    "prepare_work_ms",
    "hidden_work_ms",
    "critical_path_ms",
    "wasted_work_ms",
    "hidden_fraction",
    "critical_path_reduction_ms",
    "notes",
]

BACKEND_FIELDS = [
    "policy",
    "dataset",
    "task",
    "sample_id",
    "total_prompt_tokens",
    "slack_ms",
    "estimated_fp16_kv_mb",
    "estimated_memory_saving_mb",
    "estimated_residual_stall_ms",
    "estimated_quality_risk",
    "quality_budget",
    "quality_budget_violation",
    "segment_actions",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "experiment",
    "num_rows",
    "primary_metric",
    "primary_value",
    "secondary_metric",
    "secondary_value",
    "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def _token_count(segment: dict[str, Any]) -> int:
    try:
        return int(float(segment.get("token_count", 0)))
    except (TypeError, ValueError):
        return 0


def _segment_hash(segment: dict[str, Any]) -> str:
    text = str(segment.get("text", ""))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _stable_segments(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return [segment for segment in sample.get("segments", []) if segment.get("type") in STABLE_SLOT_TYPES]


def _query_tokens(sample: dict[str, Any]) -> int:
    return sum(_token_count(segment) for segment in sample.get("segments", []) if segment.get("type") == "USER_QUERY")


def _same_segment(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("type") == b.get("type") and _segment_hash(a) == _segment_hash(b)


def _linear_prefix_hit_tokens(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> int:
    tokens = 0
    for left, right in zip(previous, current):
        if not _same_segment(left, right):
            break
        tokens += _token_count(left)
    return tokens


def canonical_slot_key(segment: dict[str, Any]) -> tuple[int, str, str]:
    segment_type = str(segment.get("type", ""))
    return (CANONICAL_SLOT_ORDER.get(segment_type, 99), segment_type, _segment_hash(segment))


def build_canonical_slot_case(sample: dict[str, Any], tool_observation_tokens: int = 64) -> dict[str, Any]:
    """Compare prefix-locked raw order against canonical slots after a dynamic insert."""
    previous = list(sample.get("segments", []))
    sys_segments = [segment for segment in previous if segment.get("type") == "SYS_PROMPT"]
    non_sys = [segment for segment in previous if segment.get("type") != "SYS_PROMPT"]
    tool_observation = {
        "type": "TOOL_OBSERVATION",
        "text": f"dynamic tool observation for {sample.get('sample_id', '')}",
        "token_count": tool_observation_tokens,
    }
    raw_current = [*sys_segments, tool_observation, *non_sys]
    total_tokens = sum(_token_count(segment) for segment in raw_current)
    stable_tokens = sum(_token_count(segment) for segment in _stable_segments(sample))
    raw_hit = _linear_prefix_hit_tokens(previous, raw_current)
    canonical_hit = stable_tokens
    raw_prefill = max(0, total_tokens - raw_hit)
    canonical_prefill = max(0, total_tokens - canonical_hit)
    return {
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "total_tokens_with_tool_observation": total_tokens,
        "stable_tokens": stable_tokens,
        "tool_observation_tokens": tool_observation_tokens,
        "raw_prefix_hit_tokens": raw_hit,
        "canonical_slot_hit_tokens": canonical_hit,
        "raw_prefill_tokens": raw_prefill,
        "canonical_prefill_tokens": canonical_prefill,
        "prefill_tokens_saved": max(0, canonical_hit - raw_hit),
        "raw_prefix_cache_hit_rate": round(raw_hit / total_tokens, 6) if total_tokens else 0.0,
        "canonical_segment_cache_hit_rate": round(canonical_hit / total_tokens, 6) if total_tokens else 0.0,
        "position_policy": "same_slot_only",
        "quality_claim": "layout_equivalence_required_not_model_scored",
        "notes": "Canonical slots reuse stable same-position segments; arbitrary non-linear KV grafting is not claimed.",
    }


def build_forest_rows(samples: list[dict[str, Any]], limit: int = 140, tool_observation_tokens: int = 64) -> list[dict[str, Any]]:
    return [build_canonical_slot_case(sample, tool_observation_tokens) for sample in samples[:limit]]


def residual_after_slack(work_ms: float, slack_ms: float) -> float:
    return max(0.0, work_ms - slack_ms)


def build_sspp_rows(
    prepare_actions: dict[str, float],
    slack_buckets_ms: list[int],
    prediction_hit_rates: list[float],
) -> list[dict[str, Any]]:
    rows = []
    for action, work_ms in sorted(prepare_actions.items()):
        for slack in slack_buckets_ms:
            residual = residual_after_slack(work_ms, slack)
            hidden = work_ms - residual
            for hit_rate in prediction_hit_rates:
                wasted = work_ms * max(0.0, 1.0 - hit_rate)
                rows.append(
                    {
                        "prepare_action": action,
                        "tool_slack_ms": slack,
                        "prediction_hit_rate": hit_rate,
                        "prepare_work_ms": round(work_ms, 6),
                        "hidden_work_ms": round(hidden, 6),
                        "critical_path_ms": round(residual, 6),
                        "wasted_work_ms": round(wasted, 6),
                        "hidden_fraction": round(hidden / work_ms, 6) if work_ms else 0.0,
                        "critical_path_reduction_ms": round(hidden, 6),
                        "notes": "SSPP moves segment preparation from next-turn TTFT path into tool slack; prediction misses are counted as wasted work.",
                    }
                )
    return rows


def load_prepare_actions(copy_proxy: Path) -> dict[str, float]:
    actions = {
        "pretokenize_1k_tokens": 4.0,
        "prehash_segments": 1.0,
        "prequant_int4_1k_tokens_stub": 12.0,
    }
    if copy_proxy.exists():
        for row in read_csv(copy_proxy):
            if row.get("mode") == "copy_on_critical_path":
                size = int(float(row["kv_size_mb"]))
                actions[f"prefetch_{size}mb"] = float(row["copy_ms"])
    return actions


def estimate_fp16_kv_mb(tokens: int) -> float:
    return tokens * 16.0 / 1000.0


def _quant_risk(segment_type: str) -> float:
    if segment_type in HIGH_RISK_TYPES:
        return 0.08
    if segment_type in LOW_RISK_COMPRESSIBLE_TYPES:
        return 0.01
    return 0.03


def _offload_residual_ms(memory_mb: float, slack_ms: float, bandwidth_gbps: float = 12.0) -> float:
    copy_ms = (memory_mb / 1024.0) / bandwidth_gbps * 1000.0
    return max(0.0, copy_ms - slack_ms)


def load_task_eviction_risk(path: Path) -> dict[tuple[str, str], float]:
    if not path.exists():
        return {}
    risks: dict[tuple[str, str], float] = {}
    for row in read_csv(path):
        if row.get("condition") != "segment_eviction":
            continue
        try:
            risks[(row["dataset"], row["task"])] = float(row["mean_quality_drop"])
        except (KeyError, TypeError, ValueError):
            continue
    return risks


def _task_risk(sample: dict[str, Any], task_eviction_risk: dict[tuple[str, str], float]) -> float | None:
    key = (str(sample.get("dataset", "")), str(sample.get("task", "")))
    return task_eviction_risk.get(key)


def _can_quantize_context(
    sample: dict[str, Any],
    segment_type: str,
    quality_budget: float,
    task_eviction_risk: dict[tuple[str, str], float],
) -> tuple[bool, float]:
    if segment_type in LOW_RISK_COMPRESSIBLE_TYPES:
        risk = _quant_risk(segment_type)
        return risk <= quality_budget, risk
    if segment_type in {"SYS_PROMPT", "TOOL_SCHEMA", "USER_QUERY"}:
        return False, 0.0
    measured = _task_risk(sample, task_eviction_risk)
    if measured is None:
        return False, 0.0
    # Segment eviction is harsher than INT4 quantization, so use it as a
    # conservative gate: only tasks already safe under eviction are unlocked.
    if measured <= quality_budget:
        return True, measured
    return False, 0.0


def _can_offload_context(segment_type: str) -> bool:
    return segment_type not in {"SYS_PROMPT", "TOOL_SCHEMA", "USER_QUERY"}


def _policy_row(
    sample: dict[str, Any],
    policy: str,
    quality_budget: float,
    slack_ms: float,
    task_eviction_risk: dict[tuple[str, str], float],
) -> dict[str, Any]:
    total_tokens = int(sample.get("total_prompt_tokens") or sum(_token_count(s) for s in sample.get("segments", [])))
    fp16_mb = estimate_fp16_kv_mb(total_tokens)
    memory_saving = 0.0
    weighted_risk = 0.0
    residual_stall = 0.0
    actions = []
    for segment in sample.get("segments", []):
        segment_type = str(segment.get("type", ""))
        tokens = _token_count(segment)
        share = tokens / total_tokens if total_tokens else 0.0
        segment_mb = estimate_fp16_kv_mb(tokens)
        action = "keep_fp16"
        risk = 0.0
        if policy == "uniform-int4":
            action = "quantize_int4"
            risk = _quant_risk(segment_type)
            memory_saving += segment_mb * 0.75
        elif policy == "contractkv-int4":
            can_quantize, risk = _can_quantize_context(sample, segment_type, quality_budget, task_eviction_risk)
            if can_quantize:
                action = "quantize_int4"
                memory_saving += segment_mb * 0.75
        elif policy == "uniform-offload":
            action = "offload_host"
            memory_saving += segment_mb
            residual_stall += _offload_residual_ms(segment_mb, slack_ms=0)
        elif policy == "contractkv-offload":
            if _can_offload_context(segment_type):
                action = "offload_host"
                memory_saving += segment_mb
                residual_stall += _offload_residual_ms(segment_mb, slack_ms=slack_ms)
        weighted_risk += risk * share
        actions.append(f"{segment_type}:{action}")
    return {
        "policy": policy,
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "total_prompt_tokens": total_tokens,
        "slack_ms": slack_ms,
        "estimated_fp16_kv_mb": round(fp16_mb, 6),
        "estimated_memory_saving_mb": round(memory_saving, 6),
        "estimated_residual_stall_ms": round(residual_stall, 6),
        "estimated_quality_risk": round(weighted_risk, 6),
        "quality_budget": quality_budget,
        "quality_budget_violation": weighted_risk > quality_budget,
        "segment_actions": ";".join(actions),
        "claim_boundary": "backend_stub_control_plane_only_not_real_quantized_attention",
    }


def build_backend_policy_rows(
    samples: list[dict[str, Any]],
    quality_budget: float = 0.03,
    slack_ms: float = 100.0,
    policies: list[str] | None = None,
    task_eviction_risk: dict[tuple[str, str], float] | None = None,
) -> list[dict[str, Any]]:
    policies = policies or ["vllm-fp16", "uniform-int4", "contractkv-int4", "uniform-offload", "contractkv-offload"]
    task_eviction_risk = task_eviction_risk or {}
    rows = []
    for sample in samples:
        for policy in policies:
            rows.append(_policy_row(sample, policy, quality_budget, slack_ms, task_eviction_risk))
    return rows


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 6) if values else 0.0


def build_summary_rows(forest_rows: list[dict[str, Any]], sspp_rows: list[dict[str, Any]], backend_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    forest_saved = [float(row["prefill_tokens_saved"]) for row in forest_rows]
    sspp_hidden = [float(row["hidden_fraction"]) for row in sspp_rows if float(row["prediction_hit_rate"]) == 1.0]
    contract_backend = [row for row in backend_rows if row["policy"].startswith("contractkv")]
    safe_contract = [row for row in contract_backend if not bool(row["quality_budget_violation"])]
    return [
        {
            "experiment": "phase11a_segment_forest_canonical_slots",
            "num_rows": len(forest_rows),
            "primary_metric": "mean_prefill_tokens_saved",
            "primary_value": _mean(forest_saved),
            "secondary_metric": "mean_canonical_hit_rate",
            "secondary_value": _mean([float(row["canonical_segment_cache_hit_rate"]) for row in forest_rows]),
            "claim_boundary": "same-slot canonical reuse estimate; arbitrary KV grafting not claimed",
        },
        {
            "experiment": "phase11b_sspp_tool_slack",
            "num_rows": len(sspp_rows),
            "primary_metric": "mean_hidden_fraction_hit_rate_1",
            "primary_value": _mean(sspp_hidden),
            "secondary_metric": "num_prepare_actions",
            "secondary_value": len({row["prepare_action"] for row in sspp_rows}),
            "claim_boundary": "tool-slack preparation model using measured/proxy action costs",
        },
        {
            "experiment": "phase11c_action_conditioned_backend_stub",
            "num_rows": len(backend_rows),
            "primary_metric": "safe_contractkv_rows",
            "primary_value": len(safe_contract),
            "secondary_metric": "mean_contractkv_memory_saving_mb",
            "secondary_value": _mean([float(row["estimated_memory_saving_mb"]) for row in contract_backend]),
            "claim_boundary": "control-plane backend stub; not real KIVI or LMCache integration",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--copy-proxy", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/segment_fabric"))
    parser.add_argument("--limit", type=int, default=140)
    parser.add_argument("--tool-observation-tokens", type=int, default=64)
    parser.add_argument("--slack-buckets-ms", default="0,50,100,200,500")
    parser.add_argument("--prediction-hit-rates", default="1.0,0.75,0.5")
    parser.add_argument("--quality-budget", type=float, default=0.03)
    parser.add_argument("--backend-slack-ms", type=float, default=100.0)
    args = parser.parse_args()

    samples = load_jsonl(args.samples)[: args.limit]
    slack_buckets = [int(item) for item in args.slack_buckets_ms.split(",") if item]
    hit_rates = [float(item) for item in args.prediction_hit_rates.split(",") if item]

    forest_rows = build_forest_rows(samples, args.limit, args.tool_observation_tokens)
    sspp_rows = build_sspp_rows(load_prepare_actions(args.copy_proxy), slack_buckets, hit_rates)
    backend_rows = build_backend_policy_rows(samples, args.quality_budget, args.backend_slack_ms, task_eviction_risk=load_task_eviction_risk(args.risk_summary))
    summary_rows = build_summary_rows(forest_rows, sspp_rows, backend_rows)

    write_csv(args.output_dir / "segment_forest_canonical_slots_v0.csv", forest_rows, FOREST_FIELDS)
    write_csv(args.output_dir / "sspp_tool_slack_pipeline_v0.csv", sspp_rows, SSPP_FIELDS)
    write_csv(args.output_dir / "action_conditioned_backend_stub_v0.csv", backend_rows, BACKEND_FIELDS)
    write_csv(args.output_dir / "phase11_segment_lifecycle_fabric_summary_v0.csv", summary_rows, SUMMARY_FIELDS)
    print(f"forest_rows={len(forest_rows)} sspp_rows={len(sspp_rows)} backend_rows={len(backend_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
