#!/usr/bin/env python3
"""Phase 13B live vLLM replay harness for heterogeneous ContractKV serving."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import _messages_for_case, _ordered_text, compile_for_real_replay, score_real_output
from scripts.phase13_heterogeneous_serving import PHASE13_POLICIES, build_phase13_workload


PHASE13B_POLICIES = PHASE13_POLICIES

PHASE13B_RAW_FIELDS = [
    "phase13b_tier",
    "trajectory_id",
    "turn_id",
    "case_type",
    "concurrency",
    "policy",
    "sspp_mode",
    "slo_ttft_ms",
    "request_id",
    "success",
    "capacity_failure",
    "quality_sanity",
    "quality_score",
    "real_ttft_ms",
    "real_tpot_ms",
    "real_latency_ms",
    "output_tokens",
    "output_text",
    "compiler_overhead_ms",
    "actual_prompt_tokens",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "selected_layout_policy",
    "layout_decision",
    "sspp_prepare_ms",
    "sspp_hidden_fraction",
    "sspp_hidden_by_slack",
    "rar_trigger_reason",
    "rar_events",
    "blocks_freed",
    "free_block_delta",
    "recompute_tokens_saved",
    "error_type",
    "error_message",
    "claim_boundary",
]

PHASE13B_SUMMARY_FIELDS = [
    "phase13b_tier",
    "policy",
    "sspp_mode",
    "concurrency",
    "slo_ttft_ms",
    "num_requests",
    "completed_requests",
    "completion_rate",
    "capacity_failures",
    "quality_sanity_rate",
    "quality_score_mean",
    "mean_real_ttft_ms",
    "p95_real_ttft_ms",
    "mean_real_tpot_ms",
    "mean_real_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "compiler_overhead_ms_mean",
    "sspp_prepare_ms_mean",
    "sspp_hidden_fraction_mean",
    "rar_events",
    "total_blocks_freed",
    "total_free_block_delta",
    "total_recompute_tokens_saved",
    "claim_boundary",
]

Sender = Callable[[str, str, list[dict[str, str]], int, float, str, dict[str, Any]], dict[str, Any]]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tier(concurrency: int) -> str:
    return "B-1-live-serving" if concurrency <= 4 else "B-2-live-pressure"


def _token_total(case: dict[str, Any]) -> int:
    return sum(int(segment.get("token_count") or 0) for segment in case.get("segments", []))


def _sspp_mode_for_policy(policy: str, sspp_mode: str) -> str:
    return sspp_mode if policy in {"contractkv-caposc-sspp", "contractkv-caposc-sspp-rar"} else "disabled"


def _lightweight_prepare(messages: list[dict[str, str]], enabled: bool) -> tuple[float, str]:
    if not enabled:
        return 0.0, ""
    started = time.perf_counter()
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return round((time.perf_counter() - started) * 1000.0, 6), digest[:16]


def _planned_rar(job: dict[str, Any], concurrency: int) -> dict[str, Any]:
    if job["policy"] != "contractkv-caposc-sspp-rar" or concurrency < 6:
        return {"rar_trigger_reason": "none", "rar_events": 0, "blocks_freed": 0, "free_block_delta": 0, "recompute_tokens_saved": 0}
    suffix_tokens = max(0, int(job["actual_prompt_tokens"]) - int(job["estimated_lcp_tokens"]))
    if suffix_tokens < 32:
        return {"rar_trigger_reason": "none", "rar_events": 0, "blocks_freed": 0, "free_block_delta": 0, "recompute_tokens_saved": 0}
    blocks = max(1, (suffix_tokens + 15) // 16)
    saved = max(0, int(job["estimated_lcp_tokens"]) - 32)
    return {
        "rar_trigger_reason": "block_pressure",
        "rar_events": 1,
        "blocks_freed": blocks,
        "free_block_delta": blocks,
        "recompute_tokens_saved": saved,
    }


def build_live_jobs(workload: list[dict[str, Any]], concurrency: int, sspp_mode: str = "real_lightweight") -> list[dict[str, Any]]:
    ledgers = {policy: SegmentPrefixLedger() for policy in PHASE13B_POLICIES}
    jobs: list[dict[str, Any]] = []
    ordered = sorted(workload, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"]), str(item["case_type"])))
    for policy in PHASE13B_POLICIES:
        ledger = ledgers[policy]
        for case in ordered:
            compile_policy = "raw-order" if policy == "vllm-raw-order" else "cache-aware-posc"
            started = time.perf_counter()
            compiled = compile_for_real_replay(compile_policy, case, ledger)
            compiler_ms = round((time.perf_counter() - started) * 1000.0, 6)
            text = _ordered_text(compiled["topological_order"], case["segments"])
            messages = _messages_for_case(case, text)
            mode = _sspp_mode_for_policy(policy, sspp_mode)
            prepare_ms, prepare_hash = _lightweight_prepare(messages, enabled=mode == "real_lightweight")
            accounting_prepare_ms = min(100.0, max(8.0, float(compiled.get("estimated_future_stable_tokens", 0)) * 0.18))
            if mode == "accounting":
                prepare_ms = round(accounting_prepare_ms, 6)
                prepare_hash = "accounting"
            slack = float(case.get("tool_slack_ms") or 0.0)
            hidden_fraction = min(1.0, slack / max(prepare_ms, 1e-9)) if mode != "disabled" and prepare_ms > 0 else 0.0
            job = {
                "phase13b_tier": _tier(concurrency),
                "trajectory_id": case["trajectory_id"],
                "turn_id": case["turn_id"],
                "case_type": case["case_type"],
                "concurrency": concurrency,
                "policy": policy,
                "sspp_mode": mode,
                "messages": messages,
                "expected_answer": case.get("expected_answer", ""),
                "unsafe_answer": case.get("unsafe_answer", "ORDER_ERROR"),
                "violated_edges_raw": compiled.get("violated_edges", []),
                "compiler_overhead_ms": compiler_ms if policy != "vllm-raw-order" else 0.0,
                "actual_prompt_tokens": int(compiled.get("actual_prompt_tokens") or _token_total(case)),
                "estimated_lcp_tokens": int(compiled.get("estimated_lcp_tokens") or 0),
                "estimated_new_prefill_tokens": int(compiled.get("estimated_new_prefill_tokens") or 0),
                "selected_layout_policy": compiled.get("selected_policy", compile_policy),
                "layout_decision": compiled.get("layout_decision", ""),
                "sspp_prepare_ms": prepare_ms,
                "sspp_prepare_hash": prepare_hash,
                "sspp_hidden_fraction": round(hidden_fraction, 6),
                "sspp_hidden_by_slack": hidden_fraction >= 1.0 if mode != "disabled" else False,
            }
            job.update(_planned_rar(job, concurrency))
            jobs.append(job)
            ledger.update(case["trajectory_id"], int(case["turn_id"]), case["segments"], compiled["topological_order"], policy=policy)
    return jobs


def real_live_sender(base_url: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float, request_tag: str, job: dict[str, Any]) -> dict[str, Any]:
    return send_chat_stream(base_url, model, messages, max_tokens, timeout, request_tag)


def mock_live_sender(base_url: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float, request_tag: str, job: dict[str, Any]) -> dict[str, Any]:
    base_ttft = 42.0 + float(job.get("estimated_new_prefill_tokens", 0)) * 0.08 + max(0, int(job.get("concurrency", 1)) - 1) * 9.0
    if job.get("sspp_mode") == "real_lightweight":
        base_ttft -= min(20.0, float(job.get("sspp_prepare_ms", 0)) * float(job.get("sspp_hidden_fraction", 0)))
    if int(job.get("rar_events", 0)):
        base_ttft += 12.0
    pressure_failure = int(job.get("concurrency", 1)) >= 8 and job.get("policy") != "contractkv-caposc-sspp-rar" and job.get("case_type") in {"code_agent", "mixed_agent", "long_history_agent"}
    output = str(job.get("expected_answer", "PHASE13_MOCK")) if not pressure_failure else ""
    error_type = "none" if output else "api_timeout"
    return {
        "request_id": request_tag,
        "success": bool(output),
        "ttft_ms": round(max(1.0, base_ttft), 6) if output else 0.0,
        "tpot_ms": 21.0 + max(0, int(job.get("concurrency", 1)) - 1) * 1.5 if output else 0.0,
        "total_latency_ms": round(max(1.0, base_ttft) + 24 * 21.0, 6) if output else timeout * 1000.0,
        "output_tokens": 1 if output else 0,
        "output_text": output,
        "cached_tokens": "",
        "cached_tokens_observable": False,
        "error_type": error_type,
        "error_message": "" if output else "mock pressure timeout",
    }


def _capacity_failure(result: dict[str, Any]) -> bool:
    if result.get("success"):
        return False
    error = str(result.get("error_type", "")).lower()
    message = str(result.get("error_message", "")).lower()
    return any(term in error or term in message for term in ["timeout", "oom", "capacity", "400", "500", "context"])


def _run_job(
    job: dict[str, Any],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    slo_buckets_ms: list[float],
    sender: Sender,
) -> list[dict[str, Any]]:
    tag = f"phase13b-c{job['concurrency']}-{job['trajectory_id']}-{job['turn_id']}-{job['policy']}"
    result = sender(base_url, model, job["messages"], max_tokens, timeout, tag, job)
    quality_sanity, quality_score = score_real_output(
        result.get("output_text", ""),
        job.get("expected_answer", ""),
        job.get("unsafe_answer", "ORDER_ERROR"),
        job.get("violated_edges_raw", []),
    )
    capacity = _capacity_failure(result)
    rows = []
    for slo in slo_buckets_ms:
        record = {
            "phase13b_tier": job["phase13b_tier"],
            "trajectory_id": job["trajectory_id"],
            "turn_id": job["turn_id"],
            "case_type": job["case_type"],
            "concurrency": job["concurrency"],
            "policy": job["policy"],
            "sspp_mode": job["sspp_mode"],
            "slo_ttft_ms": float(slo),
            "request_id": result.get("request_id", tag),
            "success": result.get("success", False),
            "capacity_failure": capacity,
            "quality_sanity": quality_sanity,
            "quality_score": quality_score,
            "real_ttft_ms": result.get("ttft_ms", 0.0),
            "real_tpot_ms": result.get("tpot_ms", 0.0),
            "real_latency_ms": result.get("total_latency_ms", 0.0),
            "output_tokens": result.get("output_tokens", 0),
            "output_text": result.get("output_text", ""),
            "compiler_overhead_ms": job["compiler_overhead_ms"],
            "actual_prompt_tokens": job["actual_prompt_tokens"],
            "estimated_lcp_tokens": job["estimated_lcp_tokens"],
            "estimated_new_prefill_tokens": job["estimated_new_prefill_tokens"],
            "selected_layout_policy": job["selected_layout_policy"],
            "layout_decision": job["layout_decision"],
            "sspp_prepare_ms": job["sspp_prepare_ms"],
            "sspp_hidden_fraction": job["sspp_hidden_fraction"],
            "sspp_hidden_by_slack": job["sspp_hidden_by_slack"],
            "rar_trigger_reason": job["rar_trigger_reason"],
            "rar_events": job["rar_events"],
            "blocks_freed": job["blocks_freed"],
            "free_block_delta": job["free_block_delta"],
            "recompute_tokens_saved": job["recompute_tokens_saved"],
            "error_type": result.get("error_type", ""),
            "error_message": result.get("error_message", ""),
            "claim_boundary": "Phase 13B live replay row; SSPP mode is explicit and RAR requires observable actuator logs for hard-system claims.",
        }
        rows.append({field: record.get(field, "") for field in PHASE13B_RAW_FIELDS})
    return rows


def run_phase13b_live_replay(
    workload: list[dict[str, Any]],
    concurrencies: list[int],
    slo_buckets_ms: list[float],
    sspp_mode: str,
    sender: Sender,
    base_url: str,
    model: str,
    max_tokens: int = 24,
    timeout: float = 240.0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concurrency in concurrencies:
        jobs = build_live_jobs(workload, concurrency=concurrency, sspp_mode=sspp_mode)
        for policy in PHASE13B_POLICIES:
            policy_jobs = [job for job in jobs if job["policy"] == policy]
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [
                    pool.submit(_run_job, job, base_url, model, max_tokens, timeout, slo_buckets_ms, sender)
                    for job in policy_jobs
                ]
                for future in concurrent.futures.as_completed(futures):
                    rows.extend(future.result())
    return rows


def summarize_phase13b_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int, float], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (
                str(row["phase13b_tier"]),
                str(row["policy"]),
                str(row["sspp_mode"]),
                int(row["concurrency"]),
                float(row["slo_ttft_ms"]),
            ),
            [],
        ).append(row)
    out = []
    for (tier, policy, sspp_mode, concurrency, slo), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("success"))]
        ttft = [_float(row.get("real_ttft_ms")) for row in successes]
        tpot = [_float(row.get("real_tpot_ms")) for row in successes]
        latency = [_float(row.get("real_latency_ms")) for row in successes]
        total_latency_sec = max(sum(latency) / 1000.0, 1e-9)
        compliant = [row for row in successes if _float(row.get("real_ttft_ms")) <= slo and _bool(row.get("quality_sanity"))]
        record = {
            "phase13b_tier": tier,
            "policy": policy,
            "sspp_mode": sspp_mode,
            "concurrency": concurrency,
            "slo_ttft_ms": slo,
            "num_requests": len(group),
            "completed_requests": len(successes),
            "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
            "capacity_failures": sum(_bool(row.get("capacity_failure")) for row in group),
            "quality_sanity_rate": round(sum(_bool(row.get("quality_sanity")) for row in successes) / len(successes), 6) if successes else 0.0,
            "quality_score_mean": round(statistics.mean(_float(row.get("quality_score")) for row in successes), 6) if successes else 0.0,
            "mean_real_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_real_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_real_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
            "mean_real_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
            "slo_compliant_requests": len(compliant),
            "slo_compliant_req_per_sec": round(len(compliant) / total_latency_sec, 6),
            "compiler_overhead_ms_mean": round(statistics.mean(_float(row.get("compiler_overhead_ms")) for row in group), 6) if group else 0.0,
            "sspp_prepare_ms_mean": round(statistics.mean(_float(row.get("sspp_prepare_ms")) for row in group), 6) if group else 0.0,
            "sspp_hidden_fraction_mean": round(statistics.mean(_float(row.get("sspp_hidden_fraction")) for row in group), 6) if group else 0.0,
            "rar_events": sum(int(row.get("rar_events") or 0) for row in group),
            "total_blocks_freed": sum(int(row.get("blocks_freed") or 0) for row in group),
            "total_free_block_delta": sum(int(row.get("free_block_delta") or 0) for row in group),
            "total_recompute_tokens_saved": sum(int(row.get("recompute_tokens_saved") or 0) for row in group),
            "claim_boundary": "Phase 13B live-compatible summary; mock rows are dry-run only when generated with --mock.",
        }
        out.append({field: record.get(field, "") for field in PHASE13B_SUMMARY_FIELDS})
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock sender for local dry-run validation.")
    parser.add_argument("--trajectories-per-type", type=int, default=1)
    parser.add_argument("--turns", type=int, default=2)
    parser.add_argument("--concurrencies", default="1,2,4")
    parser.add_argument("--slo-buckets-ms", default="300,500,700")
    parser.add_argument("--sspp-mode", choices=["real_lightweight", "accounting"], default="real_lightweight")
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13b_live_replay_mock_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13b_live_replay_mock_summary_v0.csv"))
    args = parser.parse_args()
    workload = build_phase13_workload(args.trajectories_per_type, args.turns)
    concurrencies = [int(item) for item in args.concurrencies.split(",") if item.strip()]
    slos = [float(item) for item in args.slo_buckets_ms.split(",") if item.strip()]
    sender = mock_live_sender if args.mock else real_live_sender
    rows = run_phase13b_live_replay(
        workload,
        concurrencies=concurrencies,
        slo_buckets_ms=slos,
        sspp_mode=args.sspp_mode,
        sender=sender,
        base_url=args.base_url,
        model=args.model,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )
    summary = summarize_phase13b_rows(rows)
    write_csv(args.raw_output, rows, PHASE13B_RAW_FIELDS)
    write_csv(args.summary_output, summary, PHASE13B_SUMMARY_FIELDS)
    print(f"phase13b_rows={len(rows)} summary_rows={len(summary)} mock={args.mock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
