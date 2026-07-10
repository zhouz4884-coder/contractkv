#!/usr/bin/env python3
"""Run Phase 14D mixed-agent live serving with calibrated QC-CAPOSC."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile
from scripts.phase12_posc_layout_compiler import prefix_max_topological_order, raw_order
from scripts.phase12f_real_vllm_caposc_replay import _messages_for_case, _ordered_text, score_real_output
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _feature_for_candidate, _retokenize_case
from scripts.phase14r_qc_candidate_calibration import FEATURE_NAMES, _feature_vector, predict


POLICIES = ["vllm-raw-order", "static-posc", "contractkv-caposc", "qc-caposc-v2"]
FAMILY_SOURCES = {
    "code_agent": ("RepoBench", "python_v1.1"),
    "rag_agent": ("LongBench", "hotpotqa"),
    "structured_document_qa": ("LongBench", "qasper"),
    "tool_function_agent": ("RULER", "niah_single_1"),
    "long_history_agent": ("LongBench", "narrativeqa"),
}

RAW_FIELDS = [
    "cell_id", "arrival_mode", "concurrency", "policy", "session_id", "turn_id",
    "workload_family", "dataset", "task", "request_id", "success", "quality_sanity",
    "quality_score", "ttft_ms", "tpot_ms", "latency_ms", "output_tokens",
    "compiler_overhead_ms", "predicted_risk", "qc_fallback", "selected_layout_policy",
    "layout_decision", "actual_prompt_tokens", "estimated_lcp_tokens",
    "estimated_new_prefill_tokens", "prefix_hit_tokens", "observed_new_prefill_tokens",
    "metric_join_success", "error_type", "error_message", "batch_wall_time_ms",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "arrival_mode", "concurrency", "policy", "slo_ttft_ms", "requests",
    "completed_requests", "completion_rate", "quality_sanity_rate", "quality_bad",
    "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "p95_tpot_ms",
    "slo_compliant_requests", "slo_compliant_req_per_sec", "mean_compiler_overhead_ms",
    "qc_fallback_rate", "mean_predicted_risk", "metric_join_success_rate",
    "mean_prefix_hit_tokens", "mean_observed_new_prefill_tokens", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def build_sessions(
    full_pool: list[dict[str, Any]],
    sessions_per_family: int,
    turns: int,
    tokenizer: Any,
    max_model_len: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    output = []
    for family, (dataset, task) in FAMILY_SOURCES.items():
        candidates = [
            sample for sample in full_pool
            if sample.get("dataset") == dataset
            and sample.get("task") == task
            and sample.get("metadata", {}).get("phase14_partition") == "live_serving"
        ]
        rng.shuffle(candidates)
        if len(candidates) < sessions_per_family:
            raise ValueError(f"not enough live-serving samples for {family}: {len(candidates)}")
        for index, sample in enumerate(candidates[:sessions_per_family]):
            session_id = f"phase14d:{family}:{index}:{sample.get('sample_id')}"
            session_turns = []
            for turn in range(turns):
                case = build_case(sample, stable_word_limit=0)
                marker = f"PHASE14D_{family}_{index}_{turn}"
                case["trajectory_id"] = session_id
                case["turn_id"] = turn
                case["case_type"] = family
                case["expected_answer"] = marker
                case["unsafe_answer"] = "ORDER_ERROR"
                for segment in case["segments"]:
                    if segment.get("segment_type") == "TOOL_OBS":
                        segment["text"] = f"[TOOL_OBS_DYNAMIC] session={session_id}; turn={turn}; status=ok; no extra answer evidence."
                    elif segment.get("segment_type") == "USER_QUERY":
                        segment["text"] = f"Return exactly the marker {marker}."
                stable = next(
                    segment for segment in case["segments"]
                    if segment.get("segment_type") not in {"SYS_PROMPT", "TOOL_OBS", "USER_QUERY"}
                )
                stable["text"] = str(stable.get("text", "")) + f"\nThe required marker for turn {turn} is {marker}."
                case = _retokenize_case(case, tokenizer, max_model_len)
                session_turns.append({"case": case, "source_sample": sample, "family": family})
            output.append({"session_id": session_id, "turns": session_turns})
    return output


def _model_weights(model: dict[str, Any]) -> list[float]:
    return [float(model.get("intercept", 0.0))] + [float(model.get("weights", {}).get(name, 0.0)) for name in FEATURE_NAMES]


def _compile_job(
    policy: str,
    entry: dict[str, Any],
    ledger: SegmentPrefixLedger,
    qc_model: dict[str, Any],
    tokenizer: Any,
    max_model_len: int,
) -> dict[str, Any]:
    case = entry["case"]
    segments = case["segments"]
    if policy == "vllm-raw-order":
        order = raw_order(segments)
        compiled = {"topological_order": order, "selected_policy": "raw-order", "layout_decision": "raw_order", "estimated_lcp_tokens": 0, "estimated_new_prefill_tokens": sum(int(segment.get("token_count") or 0) for segment in segments), "actual_prompt_tokens": sum(int(segment.get("token_count") or 0) for segment in segments), "violated_edges": []}
        risk, fallback = 0.0, False
    elif policy == "static-posc":
        order = prefix_max_topological_order(segments)
        compiled = {"topological_order": order, "selected_policy": "posc", "layout_decision": "partial_canonical", "estimated_lcp_tokens": 0, "estimated_new_prefill_tokens": sum(int(segment.get("token_count") or 0) for segment in segments), "actual_prompt_tokens": sum(int(segment.get("token_count") or 0) for segment in segments), "violated_edges": []}
        risk, fallback = 0.0, False
    else:
        base = cache_aware_posc_compile(segments, ledger, case["trajectory_id"], int(case["turn_id"]), 100.0)
        if policy == "contractkv-caposc":
            compiled, risk, fallback = base, 0.0, False
        else:
            unique: dict[tuple[str, ...], dict[str, Any]] = {}
            for candidate in base.get("candidates", []):
                if candidate.get("violated_edges"):
                    continue
                unique.setdefault(tuple(candidate["topological_order"]), candidate)
            weighted = _model_weights(qc_model)
            scored = []
            for candidate in unique.values():
                feature = _feature_for_candidate(entry["source_sample"], case, list(candidate["topological_order"]), candidate, tokenizer, max_model_len)
                scored.append((predict(weighted, _feature_vector(feature)), candidate))
            threshold = float(qc_model.get("threshold", -1.0))
            accepted = [(risk_value, candidate) for risk_value, candidate in scored if risk_value <= threshold]
            if accepted:
                risk, compiled = min(accepted, key=lambda item: (int(item[1].get("estimated_new_prefill_tokens") or 0), item[0]))
                fallback = compiled.get("policy") == "raw-order"
            else:
                risk, compiled = min(scored, key=lambda item: 0 if item[1].get("policy") == "raw-order" else 1)
                fallback = True
    text = _ordered_text(compiled["topological_order"], segments)
    return {"compiled": compiled, "predicted_risk": risk, "qc_fallback": fallback, "messages": _messages_for_case(case, text)}


def prepare_cell(
    sessions: list[dict[str, Any]],
    policy: str,
    cell_id: str,
    qc_model: dict[str, Any],
    tokenizer: Any,
    max_model_len: int,
) -> list[list[dict[str, Any]]]:
    prepared = []
    for session in sessions:
        ledger = SegmentPrefixLedger()
        turns = []
        for entry in session["turns"]:
            started = time.perf_counter()
            job = _compile_job(policy, entry, ledger, qc_model, tokenizer, max_model_len)
            job["compiler_overhead_ms"] = (time.perf_counter() - started) * 1000.0
            messages = [dict(message) for message in job["messages"]]
            messages[0]["content"] = f"[CACHE_CELL:{cell_id}]\n" + messages[0]["content"]
            job["messages"] = messages
            job["entry"] = entry
            turns.append(job)
            compiled = job["compiled"]
            ledger.update(entry["case"]["trajectory_id"], int(entry["case"]["turn_id"]), entry["case"]["segments"], compiled["topological_order"], policy=policy)
        prepared.append(turns)
    return prepared


def _run_session(
    turns: list[dict[str, Any]],
    delay_s: float,
    cell_started: float,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    cell_id: str,
    policy: str,
    concurrency: int,
    arrival_mode: str,
) -> list[dict[str, Any]]:
    remaining = delay_s - (time.perf_counter() - cell_started)
    if remaining > 0:
        time.sleep(remaining)
    rows = []
    for job in turns:
        entry, compiled = job["entry"], job["compiled"]
        case = entry["case"]
        result = send_chat_stream(base_url, model, job["messages"], max_tokens, timeout, f"{cell_id}-{case['trajectory_id']}-{case['turn_id']}")
        quality, score = score_real_output(result.get("output_text", ""), case["expected_answer"], case["unsafe_answer"], compiled.get("violated_edges", []))
        rows.append({
            "cell_id": cell_id, "arrival_mode": arrival_mode, "concurrency": concurrency, "policy": policy,
            "session_id": case["trajectory_id"], "turn_id": case["turn_id"], "workload_family": entry["family"],
            "dataset": entry["source_sample"].get("dataset", ""), "task": entry["source_sample"].get("task", ""),
            "request_id": result.get("request_id", ""), "success": result.get("success", False), "quality_sanity": quality,
            "quality_score": score, "ttft_ms": result.get("ttft_ms", 0), "tpot_ms": result.get("tpot_ms", 0),
            "latency_ms": result.get("total_latency_ms", 0), "output_tokens": result.get("output_tokens", 0),
            "compiler_overhead_ms": job["compiler_overhead_ms"], "predicted_risk": job["predicted_risk"],
            "qc_fallback": job["qc_fallback"], "selected_layout_policy": compiled.get("selected_policy", compiled.get("policy", "")),
            "layout_decision": compiled.get("layout_decision", ""), "actual_prompt_tokens": compiled.get("actual_prompt_tokens", 0),
            "estimated_lcp_tokens": compiled.get("estimated_lcp_tokens", 0), "estimated_new_prefill_tokens": compiled.get("estimated_new_prefill_tokens", 0),
            "prefix_hit_tokens": "", "observed_new_prefill_tokens": "", "metric_join_success": False,
            "error_type": result.get("error_type", ""), "error_message": result.get("error_message", ""), "batch_wall_time_ms": 0,
            "claim_boundary": "Fresh live vLLM mixed-agent request; QC uses calibration-only model and marker sanity is not official task scoring.",
        })
    return rows


def run_live(args: argparse.Namespace, sessions: list[dict[str, Any]], qc_model: dict[str, Any], tokenizer: Any) -> list[dict[str, Any]]:
    rows = []
    rng = random.Random(args.seed)
    for arrival_mode in args.arrival_modes:
        for concurrency in args.concurrencies:
            for policy in POLICIES:
                cell_id = f"phase14d-{arrival_mode}-c{concurrency}-{policy}"
                prepared = prepare_cell(sessions, policy, cell_id, qc_model, tokenizer, args.max_model_len)
                if arrival_mode == "poisson":
                    delays, total = [], 0.0
                    for _ in prepared:
                        total += rng.expovariate(1000.0 / args.poisson_mean_interarrival_ms)
                        delays.append(total)
                else:
                    delays = [0.0] * len(prepared)
                started = time.perf_counter()
                cell_rows = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(_run_session, turns, delay, started, args.base_url, args.model, args.max_tokens, args.timeout, cell_id, policy, concurrency, arrival_mode) for turns, delay in zip(prepared, delays)]
                    for future in concurrent.futures.as_completed(futures):
                        cell_rows.extend(future.result())
                wall = (time.perf_counter() - started) * 1000.0
                for row in cell_rows:
                    row["batch_wall_time_ms"] = wall
                rows.extend(cell_rows)
                _write_csv(args.raw_output, rows, RAW_FIELDS)
                print(f"cell={cell_id} rows={len(cell_rows)} wall_ms={wall:.3f}")
    return rows


def join_metrics(rows: list[dict[str, Any]], metrics_path: Path | None) -> None:
    if not metrics_path or not metrics_path.exists():
        return
    initial = {
        str(event.get("request_id", "")): event
        for event in load_jsonl(metrics_path)
        if event.get("initial_prefill_observation") is True
    }
    for row in rows:
        metric = initial.get(str(row.get("request_id", "")))
        if metric:
            row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
            row["observed_new_prefill_tokens"] = metric.get("new_prefill_tokens_this_iteration", "")
            row["metric_join_success"] = True


def summarize(rows: list[dict[str, Any]], slos: list[float]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["arrival_mode"]), int(row["concurrency"]), str(row["policy"]))].append(row)
    output = []
    for (arrival, concurrency, policy), group in sorted(groups.items()):
        success = [row for row in group if _bool(row["success"])]
        ttft = [_float(row["ttft_ms"]) for row in success]
        tpot = [_float(row["tpot_ms"]) for row in success]
        wall_s = max(_float(group[0]["batch_wall_time_ms"]) / 1000.0, 1e-9)
        for slo in slos:
            compliant = [row for row in success if _bool(row["quality_sanity"]) and _float(row["ttft_ms"]) <= slo]
            observed = [row for row in group if _bool(row["metric_join_success"])]
            output.append({
                "arrival_mode": arrival, "concurrency": concurrency, "policy": policy, "slo_ttft_ms": slo,
                "requests": len(group), "completed_requests": len(success), "completion_rate": round(len(success) / len(group), 6),
                "quality_sanity_rate": round(sum(_bool(row["quality_sanity"]) for row in success) / max(1, len(success)), 6),
                "quality_bad": sum(not _bool(row["quality_sanity"]) for row in success),
                "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0, "p95_ttft_ms": round(percentile(ttft, .95), 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0, "p95_tpot_ms": round(percentile(tpot, .95), 6),
                "slo_compliant_requests": len(compliant), "slo_compliant_req_per_sec": round(len(compliant) / wall_s, 6),
                "mean_compiler_overhead_ms": round(statistics.mean(_float(row["compiler_overhead_ms"]) for row in group), 6),
                "qc_fallback_rate": round(sum(_bool(row["qc_fallback"]) for row in group) / len(group), 6),
                "mean_predicted_risk": round(statistics.mean(_float(row["predicted_risk"]) for row in group), 6),
                "metric_join_success_rate": round(len(observed) / len(group), 6),
                "mean_prefix_hit_tokens": round(statistics.mean(_float(row["prefix_hit_tokens"]) for row in observed), 6) if observed else "",
                "mean_observed_new_prefill_tokens": round(statistics.mean(_float(row["observed_new_prefill_tokens"]) for row in observed), 6) if observed else "",
                "claim_boundary": "Phase 14D real endpoint summary; marker sanity is paired with separate fresh task-quality calibration.",
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--qc-model", type=Path, required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--sessions-per-family", type=int, default=12)
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--arrival-modes", default="burst,poisson")
    parser.add_argument("--concurrencies", default="1,2,4,8")
    parser.add_argument("--slo-buckets-ms", default="1000,2000,3000,5000")
    parser.add_argument("--poisson-mean-interarrival-ms", type=float, default=50.0)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--seed", type=int, default=14014)
    parser.add_argument("--metrics-events", type=Path)
    parser.add_argument("--allow-closed-gate-smoke", action="store_true")
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    args.arrival_modes = [value.strip() for value in args.arrival_modes.split(",") if value.strip()]
    args.concurrencies = [int(value) for value in args.concurrencies.split(",") if value.strip()]
    slos = [float(value) for value in args.slo_buckets_ms.split(",") if value.strip()]
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    qc_model = json.loads(args.qc_model.read_text(encoding="utf-8"))
    if not qc_model.get("deployment_gate_open", False) and not args.allow_closed_gate_smoke:
        raise SystemExit("QC deployment gate is closed; refusing full Phase 14D live replay")
    sessions = build_sessions(load_jsonl(args.full_pool), args.sessions_per_family, args.turns, tokenizer, args.max_model_len, args.seed)
    rows = run_live(args, sessions, qc_model, tokenizer)
    join_metrics(rows, args.metrics_events)
    _write_csv(args.raw_output, rows, RAW_FIELDS)
    _write_csv(args.summary_output, summarize(rows, slos), SUMMARY_FIELDS)
    print(f"phase14d_requests={len(rows)} sessions={len(sessions)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
