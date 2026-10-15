#!/usr/bin/env python3
"""Phase 12F real vLLM replay for Cache-Aware POSC.

This script sends the Phase 12E multi-turn trajectories to a real
OpenAI-compatible vLLM endpoint and records real TTFT/TPOT/latency alongside
ContractKV's estimated LCP/new-prefill tokens.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase12e_cache_aware_posc import (
    SegmentPrefixLedger,
    cache_aware_posc_compile,
    compile_static_policy,
    estimate_lcp_tokens,
)
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories


POLICIES = ["raw-order", "boolean-guarded", "posc", "cache-aware-posc", "cache-aware-posc-rebase"]

REAL_RAW_FIELDS = [
    "trajectory_id",
    "turn_id",
    "case_type",
    "policy",
    "selected_policy",
    "layout_decision",
    "success",
    "quality_sanity",
    "quality_score",
    "real_ttft_ms",
    "real_tpot_ms",
    "real_latency_ms",
    "slo_ttft_ms",
    "actual_prompt_tokens",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "estimated_future_stable_tokens",
    "output_tokens",
    "cached_tokens",
    "cached_tokens_observable",
    "violated_edges",
    "topological_order",
    "matched_ledger_id",
    "matched_segment_ids",
    "oracle_source_policy",
    "request_id",
    "expected_answer",
    "output_text",
    "error_type",
    "error_message",
    "claim_boundary",
]

REAL_SUMMARY_FIELDS = [
    "policy",
    "slo_ttft_ms",
    "num_requests",
    "completed_requests",
    "completion_rate",
    "quality_sanity_rate",
    "quality_score_mean",
    "mean_real_ttft_ms",
    "p95_real_ttft_ms",
    "mean_real_tpot_ms",
    "p95_real_tpot_ms",
    "mean_real_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "mean_estimated_lcp_tokens",
    "mean_estimated_new_prefill_tokens",
    "cached_tokens_observable_rate",
    "claim_boundary",
]

CORRELATION_FIELDS = [
    "policy",
    "x_metric",
    "y_metric",
    "n",
    "pearson_r",
    "spearman_r",
    "claim_boundary",
]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _token_total(segments: list[dict[str, Any]]) -> int:
    return sum(int(segment.get("token_count") or 0) for segment in segments)


def _ordered_text(order: list[str], segments: list[dict[str, Any]]) -> str:
    by_id = {str(segment["segment_id"]): segment for segment in segments}
    return "\n\n".join(f"[{by_id[sid].get('segment_type')}:{sid}]\n{by_id[sid].get('text', '')}" for sid in order if sid in by_id)


def _messages_for_case(case: dict[str, Any], compiled_text: str) -> list[dict[str, str]]:
    system = (
        "You are a deterministic ContractKV layout evaluator. "
        "Return only the requested marker. If repository dependency order is broken, return ORDER_ERROR. /no_think"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": compiled_text}]


def score_real_output(output_text: str, expected_answer: str, unsafe_answer: str, violated_edges: list[list[str]]) -> tuple[bool, float]:
    if violated_edges:
        return False, 0.0
    if unsafe_answer and unsafe_answer in output_text:
        return False, 0.0
    if expected_answer and expected_answer in output_text:
        return True, 1.0
    return False, 0.0


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
            "estimated_future_stable_tokens": 0,
            "matched_ledger_id": lcp["matched_ledger_id"],
            "matched_segment_ids": lcp["matched_segment_ids"],
        }
    )
    return compiled


def compile_for_real_replay(policy: str, case: dict[str, Any], ledger: SegmentPrefixLedger) -> dict[str, Any]:
    if policy in {"cache-aware-posc", "cache-aware-posc-rebase"}:
        return cache_aware_posc_compile(
            case["segments"],
            ledger,
            session_id=case["trajectory_id"],
            turn_id=int(case["turn_id"]),
            tool_slack_ms=float(case.get("tool_slack_ms") or 0.0),
        )
    return _static_compile_with_lcp(policy, case, ledger)


def run_real_replay(
    cases: list[dict[str, Any]],
    base_url: str,
    model: str,
    policies: list[str],
    max_tokens: int,
    timeout: float,
    slo_ttft_ms: float,
    quiet: bool = False,
) -> list[dict[str, Any]]:
    ledgers = {policy: SegmentPrefixLedger() for policy in policies}
    rows: list[dict[str, Any]] = []
    ordered_cases = sorted(cases, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"])))
    for case in ordered_cases:
        for policy in policies:
            ledger = ledgers[policy]
            compiled = compile_for_real_replay(policy, case, ledger)
            text = _ordered_text(compiled["topological_order"], case["segments"])
            result = send_chat_stream(
                base_url,
                model,
                _messages_for_case(case, text),
                max_tokens,
                timeout,
                f"phase12f-{case['trajectory_id']}-{case['turn_id']}-{policy}",
            )
            quality_sanity, quality_score = score_real_output(
                result.get("output_text", ""),
                case.get("expected_answer", ""),
                case.get("unsafe_answer", "ORDER_ERROR"),
                compiled.get("violated_edges", []),
            )
            row = {
                "trajectory_id": case["trajectory_id"],
                "turn_id": case["turn_id"],
                "case_type": case["case_type"],
                "policy": policy,
                "selected_policy": compiled.get("selected_policy", policy),
                "layout_decision": compiled.get("layout_decision", ""),
                "success": result.get("success", False),
                "quality_sanity": quality_sanity,
                "quality_score": quality_score,
                "real_ttft_ms": result.get("ttft_ms", 0.0),
                "real_tpot_ms": result.get("tpot_ms", 0.0),
                "real_latency_ms": result.get("total_latency_ms", 0.0),
                "slo_ttft_ms": slo_ttft_ms,
                "actual_prompt_tokens": compiled.get("actual_prompt_tokens", _token_total(case["segments"])),
                "estimated_lcp_tokens": compiled.get("estimated_lcp_tokens", 0),
                "estimated_new_prefill_tokens": compiled.get("estimated_new_prefill_tokens", _token_total(case["segments"])),
                "estimated_future_stable_tokens": compiled.get("estimated_future_stable_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "cached_tokens": result.get("cached_tokens", ""),
                "cached_tokens_observable": result.get("cached_tokens_observable", False),
                "violated_edges": json.dumps(compiled.get("violated_edges", [])),
                "topological_order": json.dumps(compiled.get("topological_order", [])),
                "matched_ledger_id": compiled.get("matched_ledger_id", ""),
                "matched_segment_ids": json.dumps(compiled.get("matched_segment_ids", [])),
                "oracle_source_policy": "",
                "request_id": result.get("request_id", ""),
                "expected_answer": case.get("expected_answer", ""),
                "output_text": result.get("output_text", ""),
                "error_type": result.get("error_type", ""),
                "error_message": result.get("error_message", ""),
                "claim_boundary": "real vLLM OpenAI stream replay; cached-token hit rate only claimed if usage exposes it.",
            }
            rows.append({field: row.get(field, "") for field in REAL_RAW_FIELDS})
            ledger.update(case["trajectory_id"], int(case["turn_id"]), case["segments"], compiled["topological_order"], policy=policy)
            if not quiet:
                print(json.dumps(rows[-1], ensure_ascii=False))
    return rows


def _group_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (str(row["trajectory_id"]), int(row["turn_id"]), str(row["case_type"]))


def build_oracle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("policy")) == "oracle-best-layout":
            continue
        grouped.setdefault(_group_key(row), []).append(row)
    oracle = []
    for _, group in sorted(grouped.items()):
        safe = [row for row in group if _bool(row.get("success")) and _bool(row.get("quality_sanity"))]
        if not safe:
            safe = [row for row in group if _bool(row.get("success"))]
        if not safe:
            continue
        best = min(safe, key=lambda item: _float(item.get("real_ttft_ms")))
        row = dict(best)
        row["policy"] = "oracle-best-layout"
        row["selected_policy"] = "oracle-best-layout"
        row["oracle_source_policy"] = best.get("policy", "")
        row["claim_boundary"] = "non-deployable analysis upper bound; selects the fastest observed safe layout after replay."
        oracle.append({field: row.get(field, "") for field in REAL_RAW_FIELDS})
    return oracle


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = rank
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def compute_correlation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    metrics = ["estimated_lcp_tokens", "estimated_new_prefill_tokens"]
    policies = sorted({str(row["policy"]) for row in rows if str(row.get("policy")) != "oracle-best-layout"})
    for policy in policies + ["all-non-oracle"]:
        group = rows if policy == "all-non-oracle" else [row for row in rows if str(row.get("policy")) == policy]
        group = [row for row in group if str(row.get("policy")) != "oracle-best-layout" and _bool(row.get("success"))]
        for metric in metrics:
            xs = [_float(row.get(metric)) for row in group]
            ys = [_float(row.get("real_ttft_ms")) for row in group]
            pearson = _pearson(xs, ys)
            spearman = _pearson(_rank(xs), _rank(ys)) if len(xs) >= 2 else 0.0
            out.append(
                {
                    "policy": policy,
                    "x_metric": metric,
                    "y_metric": "real_ttft_ms",
                    "n": len(group),
                    "pearson_r": round(pearson, 6),
                    "spearman_r": round(spearman, 6),
                    "claim_boundary": "correlation between ContractKV ledger estimate and real vLLM timing; not direct cached-token observation.",
                }
            )
    return out


def summarize_real_replay_rows(rows: list[dict[str, Any]], slo_buckets_ms: list[float]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["policy"]), []).append(row)
    out = []
    for policy, group in sorted(grouped.items()):
        successes = [row for row in group if _bool(row.get("success"))]
        ttft = [_float(row.get("real_ttft_ms")) for row in successes]
        tpot = [_float(row.get("real_tpot_ms")) for row in successes]
        latency = [_float(row.get("real_latency_ms")) for row in successes]
        total_latency_sec = max(sum(latency) / 1000.0, 1e-9)
        for slo in slo_buckets_ms:
            compliant = [row for row in successes if _float(row.get("real_ttft_ms")) <= float(slo)]
            record = {
                "policy": policy,
                "slo_ttft_ms": int(slo) if float(slo).is_integer() else slo,
                "num_requests": len(group),
                "completed_requests": len(successes),
                "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
                "quality_sanity_rate": round(sum(_bool(row.get("quality_sanity")) for row in group) / len(group), 6) if group else 0.0,
                "quality_score_mean": round(statistics.mean(_float(row.get("quality_score")) for row in group), 6) if group else 0.0,
                "mean_real_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
                "p95_real_ttft_ms": round(percentile(ttft, 0.95), 6),
                "mean_real_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
                "p95_real_tpot_ms": round(percentile(tpot, 0.95), 6),
                "mean_real_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
                "slo_compliant_requests": len(compliant),
                "slo_compliant_req_per_sec": round(len(compliant) / total_latency_sec, 6),
                "mean_estimated_lcp_tokens": round(statistics.mean(_float(row.get("estimated_lcp_tokens")) for row in group), 6) if group else 0.0,
                "mean_estimated_new_prefill_tokens": round(statistics.mean(_float(row.get("estimated_new_prefill_tokens")) for row in group), 6) if group else 0.0,
                "cached_tokens_observable_rate": round(sum(_bool(row.get("cached_tokens_observable")) for row in group) / len(group), 6) if group else 0.0,
                "claim_boundary": "real vLLM replay summary; oracle-best-layout is a non-deployable upper bound when present.",
            }
            out.append({field: record.get(field, "") for field in REAL_SUMMARY_FIELDS})
    return out


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_slos(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--trajectories", type=Path)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--policies", default="raw-order,boolean-guarded,posc,cache-aware-posc,cache-aware-posc-rebase")
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--slo-ttft-ms", type=float, default=300.0)
    parser.add_argument("--slo-buckets-ms", default="100,200,300,500,700,1000")
    parser.add_argument("--include-oracle", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12f_real_vllm_caposc_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12f_real_vllm_caposc_summary_v0.csv"))
    parser.add_argument("--correlation-output", type=Path, default=Path("results/prefix_cache/phase12f_lcp_ttft_correlation_v0.csv"))
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        rows = load_jsonl(args.raw_output)
    else:
        if not args.base_url:
            raise SystemExit("--base-url is required unless --summarize-only is set")
        cases = load_jsonl(args.trajectories) if args.trajectories else build_multiturn_trajectories(args.trajectories_per_type, args.turns)
        policies = [policy.strip() for policy in args.policies.split(",") if policy.strip()]
        unsupported = sorted(set(policies) - set(POLICIES))
        if unsupported:
            raise SystemExit(f"unsupported policies: {unsupported}")
        rows = run_real_replay(cases, args.base_url, args.model, policies, args.max_tokens, args.timeout, args.slo_ttft_ms, quiet=args.quiet)
        if args.include_oracle:
            rows.extend(build_oracle_rows(rows))
        write_jsonl(args.raw_output, rows)
    summary = summarize_real_replay_rows(rows, _parse_slos(args.slo_buckets_ms))
    write_csv(args.summary_output, summary, REAL_SUMMARY_FIELDS)
    corr = compute_correlation_rows(rows)
    write_csv(args.correlation_output, corr, CORRELATION_FIELDS)
    print(f"raw_rows={len(rows)} summary_rows={len(summary)} correlation_rows={len(corr)}")
    return 0 if rows and all(str(row.get("error_type")) in {"", "none"} for row in rows if str(row.get("policy")) != "oracle-best-layout") else 1


if __name__ == "__main__":
    raise SystemExit(main())
