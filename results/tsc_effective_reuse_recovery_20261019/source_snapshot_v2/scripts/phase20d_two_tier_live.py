#!/usr/bin/env python3
"""Run sealed-heldout two-tier ContractKV replay against a live vLLM endpoint."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase19b_end_to_end_live import (compile_layout, load_jsonl, messages,
                                               metric_index, turn_case)
from scripts.phase20c_two_tier_development import run_one
from scripts.phase17_live_common import tokenize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--frozen-policy", type=Path, required=True); parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--load-tier", default="phase20-heldout"); parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--concurrency", type=int, default=2); parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=96); parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tool-slack-ms", type=float, default=3000); parser.add_argument("--slo-ms", type=float, default=1000)
    parser.add_argument("--timeout", type=float, default=300); parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); policy = json.loads(args.frozen_policy.read_text(encoding="utf-8"))
    if policy.get("heldout_opened_for_tuning") is not False:
        raise RuntimeError("frozen policy is not sealed")
    if str(policy.get("policy_hash")) != args.policy_hash:
        raise RuntimeError("policy hash mismatch")
    budget_admitted = float(policy["frozen_total_cost_budget_ms"]) <= float(args.tool_slack_ms)
    sessions = load_jsonl(args.sessions); ledger = SegmentPrefixLedger(); rows: list[dict[str, Any]] = []
    certificates: dict[str, dict[str, Any]] = {}; previous_prompt_ids: dict[str, list[int]] = {}

    cohorts = [sessions[index:index + args.concurrency] for index in range(0, len(sessions), args.concurrency)]
    for cohort_index, cohort in enumerate(cohorts):
      for sample in cohort:
        # Match Phase 19B/Tier-1 lifecycle exactly: certify one active cohort,
        # then consume its future turns before admitting unrelated sessions.
        row = run_one(args, sample)
        sid = str(row["session_id"]); row.update({"row_type": "canary", "policy": "contractkv-two-tier",
                                                   "frozen_policy_hash": args.policy_hash,
                                                   "frozen_incremental_budget_fits_full_slack": budget_admitted})
        row["task_score"] = score_answer(str(row.get("raw_output", "")), sample.get("answer", ""),
                                          str(sample.get("dataset", "")))["score"]
        rows.append(row); certificates[sid] = row
        case = turn_case(sample, 0, args.stable_word_limit)
        effective = "physical-cache-aware" if row.get("certificate_issued") else "raw-order"
        layout = compile_layout(effective, case, ledger, sid, 0, args.tool_slack_ms)
        prompt_ids = tokenize(args.base_url, args.model, messages(case, layout["topological_order"]), True, args.timeout)
        previous_prompt_ids[sid] = prompt_ids
        ledger.update(sid, 0, case["segments"], layout["topological_order"], policy=effective)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
      for turn in range(1, args.turns):
        batch_id = f"phase20d-two-tier-c{cohort_index}-t{turn}"
        jobs = []
        for sample in cohort:
            sid = str(sample["phase20_session_id"]); case = turn_case(sample, turn, args.stable_word_limit)
            effective = "physical-cache-aware" if certificates[sid].get("certificate_issued") else "raw-order"
            layout = compile_layout(effective, case, ledger, sid, turn, args.tool_slack_ms)
            request_messages = messages(case, layout["topological_order"])
            prompt_ids = tokenize(args.base_url, args.model, request_messages, True, args.timeout)
            jobs.append((sample, sid, case, layout, effective, request_messages, prompt_ids,
                         lcp_length(previous_prompt_ids[sid], prompt_ids)))
        batch_started = time.perf_counter(); finished = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {}
            for sample, sid, case, layout, effective, request_messages, prompt_ids, exact_lcp in jobs:
                rid = f"phase20d-two-tier-{sid}-t{turn}"
                futures[pool.submit(send_chat_stream, args.base_url, args.model, request_messages,
                                    args.max_tokens, args.timeout, rid)] = (sample, sid, case, layout, effective, rid, prompt_ids, exact_lcp)
            for future in as_completed(futures):
                sample, sid, case, layout, effective, rid, prompt_ids, exact_lcp = futures[future]
                try: result = future.result()
                except Exception as exc: result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
                score = score_answer(result.get("output_text", ""), sample.get("answer", ""), str(sample.get("dataset", "")))["score"] if result.get("success") else 0.0
                cert = certificates[sid]
                finished.append({"row_type": "future", "policy": "contractkv-two-tier", "effective_policy": effective,
                    "session_id": sid, "dataset": sample.get("dataset"), "task": sample.get("task"), "sample_id": sample.get("sample_id"),
                    "turn_id": turn, "batch_id": batch_id,
                    "request_id": result.get("request_id") or rid, "success": result.get("success", False),
                    "output_text": result.get("output_text", ""), "task_score": score, "ttft_ms": result.get("ttft_ms", 0),
                    "tpot_ms": result.get("tpot_ms", 0), "latency_ms": result.get("total_latency_ms", 0),
                    "slo_compliant": bool(result.get("success") and float(result.get("ttft_ms", 0)) <= args.slo_ms),
                    "certificate_issued": bool(cert.get("certificate_issued")), "certificate_tier": cert.get("certificate_tier", "none"),
                    "tier2_total_ms": cert.get("tier2_total_ms", 0), "stable_prefix_tokens": cert.get("stable_prefix_tokens", 0),
                    "selected_layout": layout.get("selected_policy", ""), "violated_edges": layout.get("violated_edges", []),
                    "exact_prompt_lcp_tokens": exact_lcp, "error_type": result.get("error_type", "none"),
                    "error_message": result.get("error_message", "")})
                ledger.update(sid, turn, case["segments"], layout["topological_order"], policy=effective)
                previous_prompt_ids[sid] = prompt_ids
        wall = (time.perf_counter() - batch_started) * 1000.0
        for row in finished: row["batch_wall_ms"] = wall
        rows.extend(finished)
        args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")

    time.sleep(1); metrics = metric_index(args.metrics_events)
    for row in rows:
        metric = metrics.get(str(row.get("request_id", "")), {})
        row["prompt_tokens"] = metric.get("prompt_tokens", ""); row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
        row["new_prefill_tokens"] = (max(0, int(metric.get("prompt_tokens", 0)) - int(metric.get("prefix_hit_tokens", 0))) if metric else "")
        exact = row.get("exact_prompt_lcp_tokens", "")
        row["dynamic_suffix_reuse_tokens"] = (max(0, int(metric.get("prefix_hit_tokens", 0)) - int(exact)) if metric and exact not in {"", None} else "")
    events = load_jsonl(args.event_log)
    by_id: dict[str, list[dict[str, Any]]] = {}
    for event in events: by_id.setdefault(str(event.get("request_id", "")), []).append(event)
    for row in rows:
        if row.get("row_type") != "canary": continue
        ephemeral_id = str(row.get("tier2_candidate_request_id", ""))
        promotion_id = str(row.get("tier2_promotion_request_id", ""))
        ephemeral = by_id.get(ephemeral_id, []) + by_id.get("chatcmpl-" + ephemeral_id, [])
        promotion = by_id.get(promotion_id, []) + by_id.get("chatcmpl-" + promotion_id, [])
        row["ephemeral_abort_clean"] = any(e.get("event") == "pstp_finalize" and e.get("action") == "abort"
                                                   and int(e.get("cache_entries_after", 0)) == int(e.get("cache_entries_before", 0)) for e in ephemeral)
        row["promotion_commit_observed"] = any(e.get("event") == "pstp_finalize" and e.get("action") == "commit" for e in promotion)
    args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "canaries": len(sessions),
                      "tier1": sum(r.get("certificate_tier") == "tier1" for r in rows if r.get("row_type") == "canary"),
                      "tier2": sum(r.get("certificate_tier") == "tier2" for r in rows if r.get("row_type") == "canary"),
                      "future_success": sum(r.get("success") is True for r in rows if r.get("row_type") == "future")}, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
