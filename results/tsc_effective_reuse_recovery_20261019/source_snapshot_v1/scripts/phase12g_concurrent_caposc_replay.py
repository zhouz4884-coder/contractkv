#!/usr/bin/env python3
"""Phase 12G concurrent real vLLM replay for CAPOSC."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase12f_real_vllm_caposc_replay import (
    _messages_for_case,
    _ordered_text,
    build_oracle_rows,
    compile_for_real_replay,
    score_real_output,
)
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories


POLICIES = ["boolean-guarded", "posc", "cache-aware-posc", "cache-aware-posc-rebase"]

CONCURRENT_RAW_FIELDS = [
    "concurrency",
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
    "replay_wall_time_sec",
    "actual_prompt_tokens",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "estimated_future_stable_tokens",
    "output_tokens",
    "cached_tokens_observable",
    "violated_edges",
    "topological_order",
    "oracle_source_policy",
    "request_id",
    "error_type",
    "error_message",
    "claim_boundary",
]

CONCURRENT_SUMMARY_FIELDS = [
    "concurrency",
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
    "mean_real_latency_ms",
    "replay_wall_time_sec",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "mean_estimated_lcp_tokens",
    "mean_estimated_new_prefill_tokens",
    "cached_tokens_observable_rate",
    "claim_boundary",
]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def prepare_concurrent_jobs(cases: list[dict[str, Any]], policies: list[str], concurrency: int) -> list[dict[str, Any]]:
    ledgers = {policy: SegmentPrefixLedger() for policy in policies}
    jobs: list[dict[str, Any]] = []
    ordered_cases = sorted(cases, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"])))
    for policy in policies:
        ledger = ledgers[policy]
        for case in ordered_cases:
            compiled = compile_for_real_replay(policy, case, ledger)
            text = _ordered_text(compiled["topological_order"], case["segments"])
            job = {
                "concurrency": concurrency,
                "trajectory_id": case["trajectory_id"],
                "turn_id": case["turn_id"],
                "case_type": case["case_type"],
                "policy": policy,
                "selected_policy": compiled.get("selected_policy", policy),
                "layout_decision": compiled.get("layout_decision", ""),
                "messages": _messages_for_case(case, text),
                "expected_answer": case.get("expected_answer", ""),
                "unsafe_answer": case.get("unsafe_answer", "ORDER_ERROR"),
                "actual_prompt_tokens": compiled.get("actual_prompt_tokens", 0),
                "estimated_lcp_tokens": compiled.get("estimated_lcp_tokens", 0),
                "estimated_new_prefill_tokens": compiled.get("estimated_new_prefill_tokens", 0),
                "estimated_future_stable_tokens": compiled.get("estimated_future_stable_tokens", 0),
                "violated_edges_raw": compiled.get("violated_edges", []),
                "violated_edges": json.dumps(compiled.get("violated_edges", [])),
                "topological_order": json.dumps(compiled.get("topological_order", [])),
                "oracle_source_policy": "",
            }
            jobs.append(job)
            ledger.update(case["trajectory_id"], int(case["turn_id"]), case["segments"], compiled["topological_order"], policy=policy)
    return jobs


def _run_job(base_url: str, model: str, max_tokens: int, timeout: float, slo_ttft_ms: float, job: dict[str, Any]) -> dict[str, Any]:
    result = send_chat_stream(
        base_url,
        model,
        job["messages"],
        max_tokens,
        timeout,
        f"phase12g-c{job['concurrency']}-{job['trajectory_id']}-{job['turn_id']}-{job['policy']}",
    )
    quality_sanity, quality_score = score_real_output(
        result.get("output_text", ""),
        job.get("expected_answer", ""),
        job.get("unsafe_answer", "ORDER_ERROR"),
        job.get("violated_edges_raw", []),
    )
    row = {
        "concurrency": job["concurrency"],
        "trajectory_id": job["trajectory_id"],
        "turn_id": job["turn_id"],
        "case_type": job["case_type"],
        "policy": job["policy"],
        "selected_policy": job["selected_policy"],
        "layout_decision": job["layout_decision"],
        "success": result.get("success", False),
        "quality_sanity": quality_sanity,
        "quality_score": quality_score,
        "real_ttft_ms": result.get("ttft_ms", 0.0),
        "real_tpot_ms": result.get("tpot_ms", 0.0),
        "real_latency_ms": result.get("total_latency_ms", 0.0),
        "slo_ttft_ms": slo_ttft_ms,
        "replay_wall_time_sec": 0.0,
        "actual_prompt_tokens": job["actual_prompt_tokens"],
        "estimated_lcp_tokens": job["estimated_lcp_tokens"],
        "estimated_new_prefill_tokens": job["estimated_new_prefill_tokens"],
        "estimated_future_stable_tokens": job["estimated_future_stable_tokens"],
        "output_tokens": result.get("output_tokens", 0),
        "cached_tokens_observable": result.get("cached_tokens_observable", False),
        "violated_edges": job["violated_edges"],
        "topological_order": job["topological_order"],
        "oracle_source_policy": "",
        "request_id": result.get("request_id", ""),
        "error_type": result.get("error_type", ""),
        "error_message": result.get("error_message", ""),
        "claim_boundary": "real vLLM concurrent replay; SLO req/s uses measured policy wall-clock replay time.",
    }
    return {field: row.get(field, "") for field in CONCURRENT_RAW_FIELDS}


def run_concurrent_replay(
    cases: list[dict[str, Any]],
    base_url: str,
    model: str,
    policies: list[str],
    concurrencies: list[int],
    max_tokens: int,
    timeout: float,
    slo_ttft_ms: float,
    warmup_once: bool = False,
    quiet: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concurrency in concurrencies:
        jobs = prepare_concurrent_jobs(cases, policies, concurrency)
        if warmup_once:
            warmup_jobs = list(jobs)
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(_run_job, base_url, model, max_tokens, timeout, slo_ttft_ms, job)
                    for job in warmup_jobs
                ]
                for future in concurrent.futures.as_completed(futures):
                    future.result()
        for policy in policies:
            policy_jobs = [job for job in jobs if job["policy"] == policy]
            started = time.perf_counter()
            policy_rows: list[dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(_run_job, base_url, model, max_tokens, timeout, slo_ttft_ms, job)
                    for job in policy_jobs
                ]
                for future in concurrent.futures.as_completed(futures):
                    row = future.result()
                    policy_rows.append(row)
                    if not quiet:
                        print(json.dumps(row, ensure_ascii=False))
            wall = round(time.perf_counter() - started, 6)
            for row in policy_rows:
                row["replay_wall_time_sec"] = wall
            policy_rows.sort(key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"]), str(item["policy"])))
            rows.extend(policy_rows)
    return rows


def _oracle_key(row: dict[str, Any]) -> tuple[int, str, int, str]:
    return (int(row["concurrency"]), str(row["trajectory_id"]), int(row["turn_id"]), str(row["case_type"]))


def build_concurrent_oracle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, int, str], list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("policy")) == "oracle-best-layout":
            continue
        grouped.setdefault(_oracle_key(row), []).append(row)
    oracle: list[dict[str, Any]] = []
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
        row["claim_boundary"] = "non-deployable concurrent oracle upper bound."
        oracle.append({field: row.get(field, "") for field in CONCURRENT_RAW_FIELDS})
    return oracle


def summarize_concurrent_rows(rows: list[dict[str, Any]], slo_buckets_ms: list[float]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((int(row["concurrency"]), str(row["policy"])), []).append(row)
    out: list[dict[str, Any]] = []
    for (concurrency, policy), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("success"))]
        ttft = [_float(row.get("real_ttft_ms")) for row in successes]
        tpot = [_float(row.get("real_tpot_ms")) for row in successes]
        latency = [_float(row.get("real_latency_ms")) for row in successes]
        wall = max(_float(group[0].get("replay_wall_time_sec")), 1e-9) if group else 1e-9
        for slo in slo_buckets_ms:
            compliant = [row for row in successes if _float(row.get("real_ttft_ms")) <= float(slo)]
            record = {
                "concurrency": concurrency,
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
                "mean_real_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
                "replay_wall_time_sec": wall,
                "slo_compliant_requests": len(compliant),
                "slo_compliant_req_per_sec": round(len(compliant) / wall, 6),
                "mean_estimated_lcp_tokens": round(statistics.mean(_float(row.get("estimated_lcp_tokens")) for row in group), 6) if group else 0.0,
                "mean_estimated_new_prefill_tokens": round(statistics.mean(_float(row.get("estimated_new_prefill_tokens")) for row in group), 6) if group else 0.0,
                "cached_tokens_observable_rate": round(sum(_bool(row.get("cached_tokens_observable")) for row in group) / len(group), 6) if group else 0.0,
                "claim_boundary": "real vLLM concurrent replay; oracle-best-layout is posthoc upper bound.",
            }
            out.append({field: record.get(field, "") for field in CONCURRENT_SUMMARY_FIELDS})
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


def _parse_csv_floats(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def _parse_csv_ints(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--trajectories", type=Path)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--policies", default="boolean-guarded,posc,cache-aware-posc,cache-aware-posc-rebase")
    parser.add_argument("--concurrencies", default="1,2,4")
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--slo-ttft-ms", type=float, default=300.0)
    parser.add_argument("--slo-buckets-ms", default="100,200,300,500,700,1000")
    parser.add_argument("--include-oracle", action="store_true")
    parser.add_argument("--warmup-once", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12g_concurrent_caposc_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12g_concurrent_caposc_summary_v0.csv"))
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
        rows = run_concurrent_replay(
            cases,
            args.base_url,
            args.model,
            policies,
            _parse_csv_ints(args.concurrencies),
            args.max_tokens,
            args.timeout,
            args.slo_ttft_ms,
            warmup_once=args.warmup_once,
            quiet=args.quiet,
        )
        if args.include_oracle:
            rows.extend(build_concurrent_oracle_rows(rows))
        write_jsonl(args.raw_output, rows)
    summary = summarize_concurrent_rows(rows, _parse_csv_floats(args.slo_buckets_ms))
    write_csv(args.summary_output, summary, CONCURRENT_SUMMARY_FIELDS)
    print(f"raw_rows={len(rows)} summary_rows={len(summary)}")
    return 0 if rows and all(str(row.get("error_type")) in {"", "none"} for row in rows if str(row.get("policy")) != "oracle-best-layout") else 1


if __name__ == "__main__":
    raise SystemExit(main())
