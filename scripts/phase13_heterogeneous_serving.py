#!/usr/bin/env python3
"""Phase 13 heterogeneous agent-serving ledger replay.

This is an end-to-end control-plane integration replay. It combines the
previously validated CAPOSC layout compiler, SSPP slack hiding model, and RAR
block-pressure accounting into one auditable table. It does not claim new live
vLLM measurements; Phase 13B should run the same policy set against a real
server endpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories
from scripts.phase12f_real_vllm_caposc_replay import compile_for_real_replay


PHASE13_POLICIES = [
    "vllm-raw-order",
    "contractkv-caposc",
    "contractkv-caposc-sspp",
    "contractkv-caposc-sspp-rar",
]

PHASE13_RAW_FIELDS = [
    "trajectory_id",
    "turn_id",
    "case_type",
    "arrival_mode",
    "concurrency",
    "policy",
    "slo_ttft_ms",
    "completion_success",
    "capacity_failure",
    "quality_bad",
    "quality_score",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "compiler_overhead_ms",
    "actual_prompt_tokens",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "caposc_selected_policy",
    "sspp_hidden_fraction",
    "sspp_hidden_ms",
    "sspp_residual_stall_ms",
    "rar_events",
    "blocks_freed",
    "recompute_tokens_saved",
    "caposc_layout_decision",
    "claim_boundary",
]

PHASE13_SUMMARY_FIELDS = [
    "policy",
    "concurrency",
    "slo_ttft_ms",
    "num_requests",
    "completed_requests",
    "completion_rate",
    "capacity_failures",
    "quality_bad_rate",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "mean_total_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "compiler_overhead_ms_mean",
    "caposc_selected_policy_mix",
    "sspp_hidden_fraction_mean",
    "sspp_residual_stall_ms_mean",
    "rar_events",
    "total_blocks_freed",
    "mean_block_headroom_gain",
    "total_recompute_tokens_saved",
    "claim_boundary",
]

CASE_SUMMARY_FIELDS = [
    "case_type",
    "policy",
    "concurrency",
    "num_requests",
    "quality_bad_rate",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "slo_compliant_req_per_sec",
    "sspp_hidden_fraction_mean",
    "rar_events",
    "claim_boundary",
]


def _seg(segment_id: str, segment_type: str, text: str, deps: list[str], volatility: float, cache_stability: float) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "segment_type": segment_type,
        "text": text,
        "token_count": max(1, len(text.split())),
        "dependencies": deps,
        "volatility": volatility,
        "cache_stability": cache_stability,
        "reuse_probability": cache_stability,
        "boundary_risk": 0.0,
        "stability_scope": "cross_turn" if cache_stability >= 0.5 else "single_turn",
    }


def _pad(label: str, words: int) -> str:
    base = f"{label} contract cache stable segment tool slack lifecycle block ".split()
    return " ".join((base * ((words // len(base)) + 2))[:words])


def _edges(segments: list[dict[str, Any]]) -> list[list[str]]:
    return [[dep, str(segment["segment_id"])] for segment in segments for dep in segment.get("dependencies", [])]


def _tool_call_turn(i: int, turn: int) -> dict[str, Any]:
    marker = f"PHASE13_TOOL_{i}_{turn}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Use tool schema and observations; answer with marker only. /no_think", [], 0.0, 1.0),
        _seg("tool_schema", "TOOL_SCHEMA", f"Stable API schema for planner tool {i}. {_pad('schema', 180)}", ["sys"], 0.0, 1.0),
        _seg("stable_context", "RAG_CHUNK", f"Stable tool manual includes marker {marker}. {_pad('manual', 160)}", ["sys"], 0.0, 1.0),
        _seg("tool_obs_current", "TOOL_OBS", f"Volatile tool observation at turn {turn}: status ok.", ["tool_schema"], 1.0, 0.0),
        _seg("query", "USER_QUERY", f"Return marker {marker}.", ["stable_context", "tool_obs_current"], 0.1, 0.0),
    ]
    return {
        "trajectory_id": f"tool_{i}",
        "turn_id": turn,
        "case_type": "tool_call_agent",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "tool_slack_ms": [10, 50, 100, 200, 500, 100][turn % 6],
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def _long_history_turn(i: int, turn: int) -> dict[str, Any]:
    marker = f"PHASE13_HISTORY_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Answer from stable long history and final user query only. /no_think", [], 0.0, 1.0),
        _seg("history_anchor", "CHAT_HISTORY", f"Stable early conversation contains marker {marker}. {_pad('history', 220)}", ["sys"], 0.0, 1.0),
    ]
    for t in range(turn + 1):
        segments.append(_seg(f"history_{t}", "CHAT_HISTORY", f"Chronological stable memory turn {t}. {_pad('memory', 70)}", ["history_anchor"] if t == 0 else [f"history_{t - 1}"], 0.2, 0.8))
    segments.append(_seg("tool_obs_current", "TOOL_OBS", f"Latest volatile observation for long history {turn}.", ["sys"], 1.0, 0.0))
    segments.append(_seg("query", "USER_QUERY", f"Return marker {marker}.", [f"history_{turn}", "tool_obs_current"], 0.1, 0.0))
    return {
        "trajectory_id": f"history_{i}",
        "turn_id": turn,
        "case_type": "long_history_agent",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "tool_slack_ms": [0, 10, 50, 100, 200, 500][turn % 6],
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def build_phase13_workload(trajectories_per_type: int = 2, turns: int = 6) -> list[dict[str, Any]]:
    """Build mixed code, RAG, mixed, tool-call, and long-history traces."""

    base = build_multiturn_trajectories(trajectories_per_type=trajectories_per_type, turns=turns)
    extra: list[dict[str, Any]] = []
    for i in range(trajectories_per_type):
        for turn in range(turns):
            extra.append(_tool_call_turn(i, turn))
            extra.append(_long_history_turn(i, turn))
    rows = base + extra
    return sorted(rows, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"]), str(item["case_type"])))


def _token_total(case: dict[str, Any]) -> int:
    return sum(int(segment.get("token_count") or 0) for segment in case.get("segments", []))


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compile_case(policy: str, case: dict[str, Any], ledger: SegmentPrefixLedger) -> dict[str, Any]:
    compile_policy = "raw-order" if policy == "vllm-raw-order" else "cache-aware-posc"
    started = time.perf_counter()
    compiled = compile_for_real_replay(compile_policy, case, ledger)
    compiler_ms = (time.perf_counter() - started) * 1000.0
    compiled["compiler_overhead_ms"] = compiler_ms if policy != "vllm-raw-order" else 0.0
    return compiled


def _estimate_sspp(compiled: dict[str, Any], case: dict[str, Any], enabled: bool) -> dict[str, float]:
    if not enabled:
        return {"hidden_fraction": 0.0, "hidden_ms": 0.0, "residual_stall_ms": 0.0}
    prep_ms = min(100.0, max(8.0, float(compiled.get("estimated_future_stable_tokens", 0)) * 0.18))
    slack_ms = float(case.get("tool_slack_ms") or 0.0)
    hidden_ms = min(prep_ms, slack_ms)
    residual = max(0.0, prep_ms - hidden_ms)
    hidden_fraction = hidden_ms / prep_ms if prep_ms > 0 else 0.0
    return {
        "hidden_fraction": round(hidden_fraction, 6),
        "hidden_ms": round(hidden_ms, 6),
        "residual_stall_ms": round(residual, 6),
    }


def _estimate_rar(compiled: dict[str, Any], case: dict[str, Any], concurrency: int, enabled: bool) -> dict[str, int]:
    if not enabled or concurrency < 4:
        return {"rar_events": 0, "blocks_freed": 0, "recompute_tokens_saved": 0}
    tokens = int(compiled.get("actual_prompt_tokens") or _token_total(case))
    stable_prefix = int(compiled.get("estimated_lcp_tokens") or 0)
    suffix_tokens = max(0, tokens - stable_prefix)
    if suffix_tokens < 32:
        return {"rar_events": 0, "blocks_freed": 0, "recompute_tokens_saved": 0}
    block_size = 16
    blocks_freed = max(1, math.ceil(suffix_tokens / block_size))
    saved = max(0, stable_prefix - 32)
    return {"rar_events": 1, "blocks_freed": blocks_freed, "recompute_tokens_saved": saved}


def _estimate_timing(compiled: dict[str, Any], sspp: dict[str, float], rar: dict[str, int], concurrency: int) -> dict[str, float]:
    new_prefill = float(compiled.get("estimated_new_prefill_tokens") or 0)
    queue_pressure = max(0, concurrency - 1) * 7.5
    prefill_ms = new_prefill * 0.145
    ttft = 36.0 + prefill_ms + queue_pressure - sspp["hidden_ms"] + (sspp["residual_stall_ms"] * 0.2)
    ttft = max(8.0, ttft)
    if rar["rar_events"]:
        ttft += max(0.0, (new_prefill - rar["recompute_tokens_saved"]) * 0.01)
    tpot = 5.2 + max(0, concurrency - 1) * 0.75
    total_latency = ttft + (24 * tpot)
    return {
        "ttft_ms": round(ttft, 6),
        "tpot_ms": round(tpot, 6),
        "total_latency_ms": round(total_latency, 6),
    }


def _capacity_failure(concurrency: int, policy: str, rar: dict[str, int], case: dict[str, Any]) -> bool:
    pressure_tokens = _token_total(case) * concurrency
    if pressure_tokens < 4200:
        return False
    if policy == "contractkv-caposc-sspp-rar" and rar["blocks_freed"] > 0:
        return False
    return concurrency >= 8


def run_phase13_ledger_replay(
    workload: list[dict[str, Any]],
    concurrencies: list[int] | None = None,
    slo_buckets_ms: list[float] | None = None,
) -> list[dict[str, Any]]:
    concurrencies = concurrencies or [1, 2, 4, 6, 8]
    slo_buckets_ms = slo_buckets_ms or [100, 200, 500, 700, 1000]
    rows: list[dict[str, Any]] = []
    ordered = sorted(workload, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"])))
    for concurrency in concurrencies:
        arrival_mode = "sequential_session_replay" if concurrency == 1 else "concurrent_multi_session_replay"
        ledgers = {policy: SegmentPrefixLedger() for policy in PHASE13_POLICIES}
        for policy in PHASE13_POLICIES:
            ledger = ledgers[policy]
            for case in ordered:
                compiled = _compile_case(policy, case, ledger)
                sspp = _estimate_sspp(compiled, case, enabled=policy in {"contractkv-caposc-sspp", "contractkv-caposc-sspp-rar"})
                rar = _estimate_rar(compiled, case, concurrency, enabled=policy == "contractkv-caposc-sspp-rar")
                timing = _estimate_timing(compiled, sspp, rar, concurrency)
                failed = _capacity_failure(concurrency, policy, rar, case)
                quality_bad = bool(compiled.get("violated_edges"))
                for slo in slo_buckets_ms:
                    row = {
                        "trajectory_id": case["trajectory_id"],
                        "turn_id": case["turn_id"],
                        "case_type": case["case_type"],
                        "arrival_mode": arrival_mode,
                        "concurrency": concurrency,
                        "policy": policy,
                        "slo_ttft_ms": float(slo),
                        "completion_success": not failed,
                        "capacity_failure": failed,
                        "quality_bad": quality_bad,
                        "quality_score": 0.0 if quality_bad else 1.0,
                        "ttft_ms": timing["ttft_ms"],
                        "tpot_ms": timing["tpot_ms"],
                        "total_latency_ms": timing["total_latency_ms"],
                        "compiler_overhead_ms": round(float(compiled.get("compiler_overhead_ms") or 0.0), 6),
                        "actual_prompt_tokens": int(compiled.get("actual_prompt_tokens") or _token_total(case)),
                        "estimated_lcp_tokens": int(compiled.get("estimated_lcp_tokens") or 0),
                        "estimated_new_prefill_tokens": int(compiled.get("estimated_new_prefill_tokens") or 0),
                        "caposc_selected_policy": compiled.get("selected_policy", ""),
                        "sspp_hidden_fraction": sspp["hidden_fraction"],
                        "sspp_hidden_ms": sspp["hidden_ms"],
                        "sspp_residual_stall_ms": sspp["residual_stall_ms"],
                        "rar_events": rar["rar_events"],
                        "blocks_freed": rar["blocks_freed"],
                        "recompute_tokens_saved": rar["recompute_tokens_saved"],
                        "caposc_layout_decision": compiled.get("layout_decision", ""),
                        "claim_boundary": "Phase 13A ledger replay integrating CAPOSC, SSPP, and RAR; not a fresh live vLLM measurement.",
                    }
                    rows.append({field: row.get(field, "") for field in PHASE13_RAW_FIELDS})
                ledger.update(case["trajectory_id"], int(case["turn_id"]), case["segments"], compiled["topological_order"], policy=policy)
    return rows


def summarize_phase13_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, float], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["policy"]), int(row["concurrency"]), float(row["slo_ttft_ms"])), []).append(row)
    out: list[dict[str, Any]] = []
    for (policy, concurrency, slo), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("completion_success"))]
        ttft = [_float(row.get("ttft_ms")) for row in successes]
        tpot = [_float(row.get("tpot_ms")) for row in successes]
        latency = [_float(row.get("total_latency_ms")) for row in successes]
        total_latency_sec = max(sum(latency) / 1000.0, 1e-9)
        compliant = [row for row in successes if _float(row.get("ttft_ms")) <= slo and not _bool(row.get("quality_bad"))]
        selected: dict[str, int] = {}
        for row in group:
            key = str(row.get("caposc_selected_policy") or "raw-order")
            selected[key] = selected.get(key, 0) + 1
        record = {
            "policy": policy,
            "concurrency": concurrency,
            "slo_ttft_ms": slo,
            "num_requests": len(group),
            "completed_requests": len(successes),
            "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
            "capacity_failures": sum(_bool(row.get("capacity_failure")) for row in group),
            "quality_bad_rate": round(sum(_bool(row.get("quality_bad")) for row in group) / len(group), 6) if group else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
            "p95_tpot_ms": round(percentile(tpot, 0.95), 6),
            "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
            "slo_compliant_requests": len(compliant),
            "slo_compliant_req_per_sec": round(len(compliant) / total_latency_sec, 6),
            "compiler_overhead_ms_mean": round(statistics.mean(_float(row.get("compiler_overhead_ms")) for row in group), 6) if group else 0.0,
            "caposc_selected_policy_mix": json.dumps(selected, sort_keys=True),
            "sspp_hidden_fraction_mean": round(statistics.mean(_float(row.get("sspp_hidden_fraction")) for row in group), 6) if group else 0.0,
            "sspp_residual_stall_ms_mean": round(statistics.mean(_float(row.get("sspp_residual_stall_ms")) for row in group), 6) if group else 0.0,
            "rar_events": sum(int(row.get("rar_events") or 0) for row in group),
            "total_blocks_freed": sum(int(row.get("blocks_freed") or 0) for row in group),
            "mean_block_headroom_gain": round(statistics.mean(int(row.get("blocks_freed") or 0) for row in group), 6) if group else 0.0,
            "total_recompute_tokens_saved": sum(int(row.get("recompute_tokens_saved") or 0) for row in group),
            "claim_boundary": "Phase 13A ledger replay summary; live vLLM validation remains Phase 13B.",
        }
        out.append({field: record.get(field, "") for field in PHASE13_SUMMARY_FIELDS})
    return out


def summarize_phase13_cases(rows: list[dict[str, Any]], slo_ttft_ms: float) -> list[dict[str, Any]]:
    filtered = [row for row in rows if float(row["slo_ttft_ms"]) == float(slo_ttft_ms)]
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in filtered:
        groups.setdefault((str(row["case_type"]), str(row["policy"]), int(row["concurrency"])), []).append(row)
    out: list[dict[str, Any]] = []
    for (case_type, policy, concurrency), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("completion_success"))]
        ttft = [_float(row.get("ttft_ms")) for row in successes]
        latency_sec = max(sum(_float(row.get("total_latency_ms")) for row in successes) / 1000.0, 1e-9)
        compliant = [row for row in successes if _float(row.get("ttft_ms")) <= float(slo_ttft_ms) and not _bool(row.get("quality_bad"))]
        record = {
            "case_type": case_type,
            "policy": policy,
            "concurrency": concurrency,
            "num_requests": len(group),
            "quality_bad_rate": round(sum(_bool(row.get("quality_bad")) for row in group) / len(group), 6) if group else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "slo_compliant_req_per_sec": round(len(compliant) / latency_sec, 6),
            "sspp_hidden_fraction_mean": round(statistics.mean(_float(row.get("sspp_hidden_fraction")) for row in group), 6) if group else 0.0,
            "rar_events": sum(int(row.get("rar_events") or 0) for row in group),
            "claim_boundary": "case-type breakdown for Phase 13A ledger replay.",
        }
        out.append({field: record.get(field, "") for field in CASE_SUMMARY_FIELDS})
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--concurrencies", default="1,2,4,6,8")
    parser.add_argument("--slo-buckets-ms", default="100,200,500,700,1000")
    parser.add_argument("--case-summary-slo-ms", type=float, default=500.0)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13_heterogeneous_serving_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13_heterogeneous_serving_summary_v0.csv"))
    parser.add_argument("--case-summary-output", type=Path, default=Path("results/end_to_end/phase13_heterogeneous_serving_case_summary_v0.csv"))
    args = parser.parse_args()
    workload = build_phase13_workload(args.trajectories_per_type, args.turns)
    concurrencies = [int(item) for item in args.concurrencies.split(",") if item.strip()]
    slos = [float(item) for item in args.slo_buckets_ms.split(",") if item.strip()]
    rows = run_phase13_ledger_replay(workload, concurrencies=concurrencies, slo_buckets_ms=slos)
    summary = summarize_phase13_rows(rows)
    case_summary = summarize_phase13_cases(rows, args.case_summary_slo_ms)
    write_csv(args.raw_output, rows, PHASE13_RAW_FIELDS)
    write_csv(args.summary_output, summary, PHASE13_SUMMARY_FIELDS)
    write_csv(args.case_summary_output, case_summary, CASE_SUMMARY_FIELDS)
    print(f"phase13_workload_turns={len(workload)} raw_rows={len(rows)} summary_rows={len(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
