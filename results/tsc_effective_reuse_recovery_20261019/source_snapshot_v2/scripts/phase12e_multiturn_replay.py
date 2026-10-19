#!/usr/bin/env python3
"""Run Phase 12E multi-turn cache-aware POSC replay.

This script has a deterministic ledger-model mode by default. It estimates
TTFT pressure from the number of prompt tokens that cannot be reused under the
ContractKV segment prefix ledger. It does not claim observed vLLM cached-token
hits; that remains the next real-serving validation step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_posc_layout_compiler import compile_layout
from scripts.phase12e_cache_aware_posc import (
    POLICIES,
    RAW_FIELDS,
    CASE_SUMMARY_FIELDS,
    SUMMARY_FIELDS,
    SegmentPrefixLedger,
    aggregate_phase12e_case_results,
    aggregate_phase12e_results,
    cache_aware_posc_compile,
    compile_static_policy,
    estimate_lcp_tokens,
    write_csv,
    write_jsonl,
)
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories


def _token_total(segments: list[dict[str, Any]]) -> int:
    return sum(int(segment.get("token_count") or 0) for segment in segments)


def _score_layout(case: dict[str, Any], compiled: dict[str, Any]) -> tuple[bool, float]:
    if compiled.get("violated_edges"):
        return False, 0.0
    return True, 1.0


def _deterministic_noise(policy: str, trajectory_id: str, turn_id: int) -> float:
    seed = sum(ord(ch) for ch in f"{policy}:{trajectory_id}:{turn_id}")
    return float(seed % 11)


def _simulate_timing(policy: str, new_prefill_tokens: int, total_tokens: int, rebase_cost_ms: float, hidden_fraction: float, trajectory_id: str, turn_id: int) -> dict[str, float]:
    base_ms = 34.0
    per_new_token_ms = 0.155
    per_total_token_decode_ms = 0.004
    policy_overhead = {
        "raw-order": 0.0,
        "boolean-guarded": 1.0,
        "posc": 3.0,
        "cache-aware-posc": 4.0,
        "cache-aware-posc-rebase": 5.0,
    }.get(policy, 2.0)
    visible_rebase_ms = max(0.0, rebase_cost_ms * (1.0 - hidden_fraction))
    ttft = base_ms + new_prefill_tokens * per_new_token_ms + policy_overhead + visible_rebase_ms + _deterministic_noise(policy, trajectory_id, turn_id)
    tpot = 5.0 + total_tokens * per_total_token_decode_ms / 10.0
    latency = ttft + 12.0 * tpot
    return {
        "ttft_ms": round(ttft, 6),
        "tpot_ms": round(tpot, 6),
        "total_latency_ms": round(latency, 6),
    }


def _static_compile_with_lcp(policy: str, case: dict[str, Any], ledger: SegmentPrefixLedger) -> dict[str, Any]:
    compiled = compile_static_policy(case["segments"], policy)
    lcp = estimate_lcp_tokens(compiled["topological_order"], case["segments"], ledger, session_id=case["trajectory_id"])
    actual_tokens = _token_total(case["segments"])
    compiled.update(
        {
            "selected_policy": policy,
            "actual_prompt_tokens": actual_tokens,
            "estimated_lcp_tokens": lcp["matched_tokens"],
            "estimated_new_prefill_tokens": max(0, actual_tokens - int(lcp["matched_tokens"])),
            "estimated_future_stable_tokens": compile_layout(case["segments"], policy="posc")["expected_prefix_gain_tokens"] if policy == "posc" else 0,
            "matched_ledger_id": lcp["matched_ledger_id"],
            "matched_segment_ids": lcp["matched_segment_ids"],
            "rebase_performed": False,
            "rebase_hidden_fraction": 0.0,
            "rebase_cost_ms": 0.0,
        }
    )
    return compiled


def run_model_replay(cases: list[dict[str, Any]], policies: list[str], slo_ttft_ms: float, quiet: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledgers = {policy: SegmentPrefixLedger() for policy in policies}
    raw_rows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    ordered_cases = sorted(cases, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"])))
    for case in ordered_cases:
        for policy in policies:
            ledger = ledgers[policy]
            if policy in {"cache-aware-posc", "cache-aware-posc-rebase"}:
                compiled = cache_aware_posc_compile(
                    case["segments"],
                    ledger,
                    session_id=case["trajectory_id"],
                    turn_id=int(case["turn_id"]),
                    tool_slack_ms=float(case.get("tool_slack_ms") or 0.0),
                )
            else:
                compiled = _static_compile_with_lcp(policy, case, ledger)
            quality_sanity, quality_score = _score_layout(case, compiled)
            timing = _simulate_timing(
                policy,
                int(compiled["estimated_new_prefill_tokens"]),
                int(compiled["actual_prompt_tokens"]),
                float(compiled.get("rebase_cost_ms") or 0.0),
                float(compiled.get("rebase_hidden_fraction") or 0.0),
                str(case["trajectory_id"]),
                int(case["turn_id"]),
            )
            row = {
                "trajectory_id": case["trajectory_id"],
                "turn_id": case["turn_id"],
                "case_type": case["case_type"],
                "policy": policy,
                "selected_policy": compiled.get("selected_policy", policy),
                "layout_decision": compiled.get("layout_decision", ""),
                "success": True,
                "quality_score": quality_score,
                "quality_sanity": quality_sanity,
                "ttft_ms": timing["ttft_ms"],
                "tpot_ms": timing["tpot_ms"],
                "total_latency_ms": timing["total_latency_ms"],
                "slo_ttft_ms": slo_ttft_ms,
                "actual_prompt_tokens": compiled["actual_prompt_tokens"],
                "estimated_lcp_tokens": compiled["estimated_lcp_tokens"],
                "estimated_new_prefill_tokens": compiled["estimated_new_prefill_tokens"],
                "estimated_future_stable_tokens": compiled.get("estimated_future_stable_tokens", 0),
                "violated_edges": json.dumps(compiled.get("violated_edges", [])),
                "topological_order": json.dumps(compiled.get("topological_order", [])),
                "matched_ledger_id": compiled.get("matched_ledger_id", ""),
                "matched_segment_ids": json.dumps(compiled.get("matched_segment_ids", [])),
                "rebase_performed": compiled.get("rebase_performed", False),
                "rebase_hidden_fraction": compiled.get("rebase_hidden_fraction", 0.0),
                "rebase_cost_ms": compiled.get("rebase_cost_ms", 0.0),
                "claim_boundary": "deterministic ledger-model replay; TTFT is modeled from estimated reusable-prefix tokens, not observed vLLM cache hits.",
            }
            raw_rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            decision = {
                "trajectory_id": case["trajectory_id"],
                "turn_id": case["turn_id"],
                "case_type": case["case_type"],
                "policy": policy,
                "selected_policy": compiled.get("selected_policy", policy),
                "topological_order": compiled.get("topological_order", []),
                "estimated_lcp_tokens": compiled["estimated_lcp_tokens"],
                "estimated_new_prefill_tokens": compiled["estimated_new_prefill_tokens"],
                "violated_edges": compiled.get("violated_edges", []),
                "candidates": compiled.get("candidates", []),
            }
            decisions.append(decision)
            ledger.update(case["trajectory_id"], int(case["turn_id"]), case["segments"], compiled["topological_order"], policy=policy)
            if not quiet:
                print(json.dumps(raw_rows[-1], ensure_ascii=False))
    return raw_rows, decisions


def _parse_slos(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--policies", default="raw-order,boolean-guarded,posc,cache-aware-posc,cache-aware-posc-rebase")
    parser.add_argument("--slo-ttft-ms", type=float, default=300.0)
    parser.add_argument("--slo-buckets-ms", default="100,200,300,500,700,1000")
    parser.add_argument("--trajectory-output", type=Path, default=Path("results/prefix_cache/phase12e_multiturn_trajectories_v0.jsonl"))
    parser.add_argument("--decision-output", type=Path, default=Path("results/prefix_cache/phase12e_cache_aware_layout_decisions_v0.jsonl"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12e_multiturn_replay_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12e_multiturn_replay_summary_v0.csv"))
    parser.add_argument("--case-summary-output", type=Path, default=Path("results/prefix_cache/phase12e_multiturn_case_summary_v0.csv"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    cases = build_multiturn_trajectories(args.trajectories_per_type, args.turns)
    write_jsonl(args.trajectory_output, cases)
    policies = [policy.strip() for policy in args.policies.split(",") if policy.strip()]
    unsupported = sorted(set(policies) - set(POLICIES))
    if unsupported:
        raise SystemExit(f"unsupported policies: {unsupported}")
    rows, decisions = run_model_replay(cases, policies, args.slo_ttft_ms, quiet=args.quiet)
    write_jsonl(args.raw_output, rows)
    write_jsonl(args.decision_output, decisions)
    summary = aggregate_phase12e_results(rows, _parse_slos(args.slo_buckets_ms))
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    case_summary = aggregate_phase12e_case_results(rows)
    write_csv(args.case_summary_output, case_summary, CASE_SUMMARY_FIELDS)
    print(f"trajectory_turns={len(cases)} raw_rows={len(rows)} summary_rows={len(summary)} case_summary_rows={len(case_summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
