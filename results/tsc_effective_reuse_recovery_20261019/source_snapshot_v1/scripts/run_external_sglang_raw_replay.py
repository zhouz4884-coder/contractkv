#!/usr/bin/env python3
"""Replay the frozen raw-order agent trace against an SGLang endpoint."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, compile_static_policy
from scripts.phase19b_end_to_end_live import compile_layout, load_jsonl, messages, turn_case
from scripts.phase20a_official_quality import standard_score


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))] if ordered else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--backend-label", required=True)
    parser.add_argument("--layout-policy", choices=("raw-order", "offline-safe-compiled"),
                        default="raw-order")
    parser.add_argument("--safe-session-source", type=Path)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--slo-ms", type=float, default=1500)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    sessions = load_jsonl(args.sessions)
    safe_sessions: set[str] = set()
    if args.layout_policy == "offline-safe-compiled":
        if not args.safe_session_source:
            raise ValueError("offline-safe-compiled requires --safe-session-source")
        safe_sessions = {
            str(row["session_id"])
            for row in load_jsonl(args.safe_session_source)
            if row.get("row_type") == "canary" and row.get("certificate_issued") is True
        }
    ledger = SegmentPrefixLedger()
    rows: list[dict[str, Any]] = []
    cohorts = [sessions[index:index + args.concurrency]
               for index in range(0, len(sessions), args.concurrency)]
    for cohort_index, cohort in enumerate(cohorts):
        for turn in range(args.turns):
            jobs = []
            for sample in cohort:
                sid = str(sample["phase19b_session_id"])
                case = turn_case(sample, turn, args.stable_word_limit)
                qualified = sid in safe_sessions
                if args.layout_policy == "offline-safe-compiled" and qualified:
                    layout = compile_layout(
                        "physical-cache-aware", case, ledger, sid, turn, 2000.0)
                    effective_layout = "offline-safe-compiled"
                else:
                    layout = compile_static_policy(case["segments"], "raw-order")
                    effective_layout = "raw-order"
                request_messages = messages(case, layout["topological_order"])
                rendered = tokenizer.apply_chat_template(
                    request_messages, tokenize=True, add_generation_prompt=True)
                jobs.append((sample, sid, case, layout, effective_layout,
                             qualified, request_messages, len(rendered)))
            batch_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {}
                for (sample, sid, case, layout, effective_layout, qualified,
                     request_messages, prompt_tokens) in jobs:
                    rid = f"external-{args.backend_label}-{sid}-t{turn}"
                    future = pool.submit(
                        send_chat_stream, args.base_url, args.model,
                        request_messages, args.max_tokens, args.timeout, rid)
                    futures[future] = (sample, sid, case, layout, effective_layout,
                                       qualified, rid, prompt_tokens)
                finished = []
                for future in as_completed(futures):
                    (sample, sid, case, layout, effective_layout, qualified,
                     rid, prompt_tokens) = futures[future]
                    result = future.result()
                    score, metric, scoring_error = standard_score(
                        str(sample.get("dataset", "")), str(sample.get("task", "")),
                        str(result.get("output_text", "")), sample.get("answer", ""))
                    finished.append({
                        "backend": args.backend_label, "policy": args.layout_policy,
                        "effective_layout": effective_layout,
                        "offline_qualified": qualified,
                        "session_id": sid, "dataset": sample.get("dataset"),
                        "task": sample.get("task"), "sample_id": sample.get("sample_id"),
                        "turn_id": turn, "row_type": "warmup" if turn == 0 else "future",
                        "request_id": result.get("request_id") or rid,
                        "success": result.get("success", False),
                        "ttft_ms": result.get("ttft_ms", 0),
                        "tpot_ms": result.get("tpot_ms", 0),
                        "latency_ms": result.get("total_latency_ms", 0),
                        "prompt_tokens": prompt_tokens,
                        "output_tokens": result.get("output_tokens", 0),
                        "output_text": result.get("output_text", ""),
                        "task_score": score, "task_metric": metric,
                        "scoring_error": scoring_error,
                        "cached_tokens": result.get("cached_tokens", ""),
                        "cached_tokens_observable": result.get("cached_tokens_observable", False),
                        "peak_kv_blocks": "unavailable_without_backend_block_metric",
                        "error_type": result.get("error_type", "none"),
                        "error_message": result.get("error_message", ""),
                        "claim_boundary": (
                            "Official SGLang RadixAttention baseline; offline-safe-compiled "
                            "uses frozen ContractKV layouts without PSTP or online certificates."
                            if args.layout_policy == "offline-safe-compiled" else
                            "Official SGLang raw-order RadixAttention baseline; no ContractKV layout or hidden cache-hit inference."
                        ),
                    })
                    ledger.update(sid, turn, case["segments"],
                                  layout["topological_order"],
                                  policy=effective_layout)
            batch_wall_ms = (time.perf_counter() - batch_started) * 1000.0
            batch_id = f"{args.backend_label}-c{cohort_index}-t{turn}"
            for row in finished:
                row["batch_id"] = batch_id; row["batch_wall_ms"] = batch_wall_ms
            rows.extend(finished)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    future = [row for row in rows if row["row_type"] == "future"]
    successful = [row for row in future if row["success"]]
    ttft = [float(row["ttft_ms"]) for row in successful]
    tpot = [float(row["tpot_ms"]) for row in successful]
    batches: dict[str, float] = {}
    for row in successful:
        batches[row["batch_id"]] = max(batches.get(row["batch_id"], 0), float(row["batch_wall_ms"]))
    wall_s = sum(batches.values()) / 1000.0
    summary = {
        "backend": args.backend_label, "policy": args.layout_policy,
        "sessions": len(sessions), "future_requests": len(future),
        "completed_requests": len(successful),
        "completion_rate": len(successful) / max(1, len(future)),
        "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, .95),
        "mean_tpot_ms": statistics.fmean(tpot) if tpot else 0.0,
        "p95_tpot_ms": percentile(tpot, .95),
        "mean_prompt_tokens": statistics.fmean(float(row["prompt_tokens"]) for row in successful) if successful else 0.0,
        "mean_task_score": statistics.fmean(float(row["task_score"]) for row in successful) if successful else 0.0,
        "offline_qualified_sessions": len(safe_sessions),
        "peak_kv_blocks": "unavailable_without_backend_block_metric",
        "slo_ms": args.slo_ms,
        "slo_compliant_requests": sum(value <= args.slo_ms for value in ttft),
        "slo_compliant_req_per_sec": sum(value <= args.slo_ms for value in ttft) / max(wall_s, 1e-9),
        "cached_tokens_observable_rate": statistics.fmean(float(row["cached_tokens_observable"]) for row in successful) if successful else 0.0,
        "claim_boundary": (
            "Offline frozen safe layouts consumed by SGLang; not complete online ContractKV because PSTP and online certificate issuance are absent."
            if args.layout_policy == "offline-safe-compiled" else
            "External production prefix-cache baseline on the same raw-order trace; cached-token metrics are reported only if the backend exposes them."
        ),
    }
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
