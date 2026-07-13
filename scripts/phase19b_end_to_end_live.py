#!/usr/bin/env python3
"""Run one fresh-server Phase 19B task-bearing future-turn cell."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_certificate_scope import (
    CertificateValidityScope, RequestValidityContext, ScopeMode,
    validation_errors,
)
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, compile_static_policy
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase15d_task_bearing_certified_replay import output_contract
from scripts.phase17_live_common import api_root, digest, generate_raw, post_json, tokenize


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def messages(case: dict[str, Any], order: list[str]) -> list[dict[str, str]]:
    result = quality_messages(case, _ordered_text(order, case["segments"]))
    result[0]["content"] = f"[PHASE19B:{case['trajectory_id']}]\n" + result[0]["content"]
    return result


def turn_case(sample: dict[str, Any], turn: int, stable_word_limit: int) -> dict[str, Any]:
    case = build_case(sample, stable_word_limit=stable_word_limit)
    case["turn_id"] = turn
    for segment in case["segments"]:
        if segment.get("segment_type") == "TOOL_OBS":
            segment["text"] = f"[TOOL_OBS_DYNAMIC] turn={turn}; no extra evidence is provided."
    return case


def stable_order(case: dict[str, Any], order: list[str]) -> list[str]:
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    volatile = {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}
    result = []
    for segment_id in order:
        if str(by_id[segment_id].get("segment_type")) in volatile:
            break
        result.append(segment_id)
    return result


def validity_scope(
    args: argparse.Namespace,
    sample: dict[str, Any],
    case: dict[str, Any],
    layout: dict[str, Any],
) -> CertificateValidityScope:
    order = [str(value) for value in layout["topological_order"]]
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    stable_ids = stable_order(case, order)
    layout_identity = [
        (segment_id, tuple(sorted(str(value) for value in by_id[segment_id].get("dependencies", []))))
        for segment_id in order
    ]
    stable_identity = [
        (segment_id, str(by_id[segment_id].get("segment_type", "")), str(by_id[segment_id].get("text", "")))
        for segment_id in stable_ids
    ]
    observations = [
        (str(segment.get("segment_id", "")), str(segment.get("text", "")))
        for segment in case["segments"]
        if str(segment.get("segment_type", "")) == "TOOL_OBS"
    ]
    return CertificateValidityScope(
        model_identity=args.model_identity or args.model,
        task_family=f"{sample.get('dataset', '')}:{sample.get('task', '')}",
        layout_hash=digest(layout_identity),
        stable_prefix_hash=digest(stable_identity),
        scope_mode=args.certificate_scope_mode,
        observation_identity=digest(observations),
        observation_epoch=int(case.get("turn_id", 0)),
        policy_hash=args.policy_hash,
        qualification_hash=args.qualification_hash or args.policy_hash,
    )


def request_context(scope: CertificateValidityScope) -> RequestValidityContext:
    return RequestValidityContext(
        model_identity=scope.model_identity,
        task_family=scope.task_family,
        layout_hash=scope.layout_hash,
        stable_prefix_hash=scope.stable_prefix_hash,
        observation_identity=scope.observation_identity,
        observation_epoch=scope.observation_epoch,
        policy_hash=scope.policy_hash,
        qualification_hash=scope.qualification_hash,
    )


def compile_layout(policy: str, case: dict[str, Any], ledger: SegmentPrefixLedger,
                   session_id: str, turn: int, slack_ms: float) -> dict[str, Any]:
    if policy == "raw-order":
        return compile_static_policy(case["segments"], "raw-order")
    if policy == "static-dependency-layout":
        return compile_static_policy(case["segments"], "posc")
    return cache_aware_posc_compile(case["segments"], ledger, session_id, turn, slack_ms)


def compact_verify(args: argparse.Namespace, sample: dict[str, Any], case: dict[str, Any],
                   layout: dict[str, Any], raw: dict[str, Any], session_id: str) -> dict[str, Any]:
    order = [str(value) for value in layout["topological_order"]]
    candidate_messages = messages(case, order)
    prefix_messages = messages(case, stable_order(case, order))
    stable_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    stable_end = lcp_length(stable_ids, candidate_ids)
    payload = {
        "request_id": f"phase19b-verify-{args.load_tier}-{session_id}",
        "prompt_token_ids": candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]],
        "txn_id": f"phase19b-txn-{args.load_tier}-{session_id}",
        "policy_hash": args.policy_hash, "policy_version": "phase19a-frozen-v0",
        "attestation_mode": "same-backend-teacher-forced-strict-top1",
        "stable_prefix_end_token": stable_end, "verify_start_token": len(candidate_ids),
        "reference_answer_ids": raw["token_ids"], "reference_raw_margins": raw["margins"],
        "terminal_stop_token_id": raw["terminal_stop_token_id"],
        "stable_content_hash": digest(stable_ids), "layout_hash": digest(candidate_ids),
        "dependency_graph_hash": digest([(segment["segment_id"], segment.get("dependencies", [])) for segment in case["segments"]]),
        "timeout_s": args.timeout,
    }
    verify_started = time.perf_counter()
    body = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
    endpoint_ms = (time.perf_counter() - verify_started) * 1000.0
    return {**body, "preparation_ms": 0.0, "verify_endpoint_ms": endpoint_ms,
            "verification_ms": endpoint_ms,
            "compact_bytes": len(json.dumps(body, separators=(",", ":")).encode()),
            "stable_prefix_tokens": stable_end,
            "_candidate_prompt_ids": candidate_ids}


def metric_index(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists(): return {}
    rows = load_jsonl(path)
    return {str(row.get("request_id")): row for row in rows
            if row.get("event") == "prefix_cache_request_observation"
            and row.get("initial_prefill_observation") is True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--policy", choices=["raw-order", "static-dependency-layout", "physical-cache-aware", "contractkv-full"], required=True)
    parser.add_argument("--policy-hash", required=True); parser.add_argument("--load-tier", required=True)
    parser.add_argument("--concurrency", type=int, required=True); parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--stable-word-limit", type=int, default=2600); parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--tool-slack-ms", type=float, default=2000); parser.add_argument("--slo-ms", type=float, default=1000)
    parser.add_argument("--timeout", type=float, default=300); parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--certificate-scope-mode", choices=[mode.value for mode in ScopeMode],
                        default=ScopeMode.QUALIFIED_SESSION.value)
    parser.add_argument("--model-identity", default="")
    parser.add_argument("--qualification-hash", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sessions = load_jsonl(args.sessions); ledger = SegmentPrefixLedger(); rows = []
    certificates: dict[str, dict[str, Any]] = {}
    previous_prompt_ids: dict[str, list[int]] = {}
    # Keep each active-session working set within the requested load tier. The
    # complete dataset is still replayed, but a session's next turn arrives
    # before unrelated cohorts evict its stable prefix.
    cohorts = [sessions[index:index + args.concurrency]
               for index in range(0, len(sessions), args.concurrency)]

    for cohort_index, cohort in enumerate(cohorts):
      if args.policy == "contractkv-full":
        for index, sample in enumerate(cohort):
            sid = str(sample["phase19b_session_id"]); case = turn_case(sample, 0, args.stable_word_limit)
            raw_layout = compile_static_policy(case["segments"], "raw-order")
            layout = compile_layout("physical-cache-aware", case, ledger, sid, 0, args.tool_slack_ms)
            raw_messages = messages(case, raw_layout["topological_order"])
            started = time.perf_counter()
            try:
                raw = generate_raw(args.base_url, args.model, f"phase19b-canary-raw-{args.load_tier}-{sid}",
                                   raw_messages, args.timeout, args.max_tokens)
                verify = compact_verify(args, sample, case, layout, raw, sid)
                score = score_answer(raw["text"], sample.get("answer", ""), str(sample.get("dataset", "")))["score"]
                issued = bool(verify.get("certificate_issued"))
                scope = validity_scope(args, sample, case, layout)
                if issued:
                    verify["validity_scope"] = scope.__dict__.copy()
                certificates[sid] = verify
                rows.append({"row_type": "canary", "policy": args.policy, "load_tier": args.load_tier,
                             "concurrency": args.concurrency, "session_id": sid, "dataset": sample.get("dataset"),
                             "task": sample.get("task"), "sample_id": sample.get("sample_id"), "turn_id": 0,
                             "request_id": f"phase19b-canary-raw-{args.load_tier}-{sid}", "success": True,
                             "output_text": raw["text"], "task_score": score, "ttft_ms": "", "tpot_ms": "",
                             "latency_ms": (time.perf_counter()-started)*1000, "slo_compliant": "",
                             "certificate_issued": issued, "verify_decision": verify.get("verify_decision", ""),
                             "certificate_scope_mode": scope.scope_mode,
                             "certificate_scope_valid": issued,
                             "certificate_scope_errors": [],
                             "txn_state": verify.get("txn_state", ""), "committed_tokens": verify.get("committed_tokens", 0),
                             "preparation_ms": verify.get("preparation_ms", 0),
                             "verify_endpoint_ms": verify.get("verify_endpoint_ms", 0),
                             "verification_ms": verify.get("verification_ms", 0), "compact_bytes": verify.get("compact_bytes", 0),
                             "certified_stable_prefix_tokens": verify.get("stable_prefix_tokens", 0),
                             "unhidden_verifier_ms": max(0.0, float(verify.get("verification_ms", 0))-args.tool_slack_ms),
                             "selected_layout": layout.get("selected_policy", ""), "violated_edges": layout.get("violated_edges", []),
                             "error_type": "none", "error_message": ""})
                previous_prompt_ids[sid] = (verify["_candidate_prompt_ids"] if issued else
                                            tokenize(args.base_url, args.model, raw_messages, True, args.timeout))
            except Exception as exc:
                certificates[sid] = {"certificate_issued": False, "verify_decision": "INCOMPLETE"}
                rows.append({"row_type": "canary", "policy": args.policy, "load_tier": args.load_tier,
                             "concurrency": args.concurrency, "session_id": sid, "dataset": sample.get("dataset"),
                             "task": sample.get("task"), "sample_id": sample.get("sample_id"), "turn_id": 0,
                             "request_id": "", "success": False, "certificate_issued": False,
                             "verify_decision": "INCOMPLETE", "txn_state": "ABORTED", "committed_tokens": 0,
                             "preparation_ms": 0, "verify_endpoint_ms": 0,
                             "verification_ms": 0, "compact_bytes": 0,
                             "certified_stable_prefix_tokens": 0, "unhidden_verifier_ms": 0,
                             "selected_layout": layout.get("selected_policy", ""), "violated_edges": layout.get("violated_edges", []),
                             "error_type": type(exc).__name__, "error_message": str(exc)})
                previous_prompt_ids[sid] = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
            ledger.update(sid, 0, case["segments"], layout["topological_order"], policy="cache-aware-posc")

      else:
        # Prime each policy with the same unmeasured turn-0 working set.  The
        # previous protocol counted this cold request for baselines while the
        # ContractKV canary occupied turn 0, which biased the warm comparison.
        warmups = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {}
            for sample in cohort:
                sid = str(sample["phase19b_session_id"])
                case = turn_case(sample, 0, args.stable_word_limit)
                layout = compile_layout(args.policy, case, ledger, sid, 0, args.tool_slack_ms)
                warmup_messages = messages(case, layout["topological_order"])
                prompt_ids = tokenize(args.base_url, args.model, warmup_messages, True, args.timeout)
                rid = f"phase19b-{args.policy}-{args.load_tier}-{sid}-warmup"
                future = pool.submit(send_chat_stream, args.base_url, args.model,
                                     warmup_messages, args.max_tokens,
                                     args.timeout, rid)
                futures[future] = (sample, sid, case, layout, rid, prompt_ids)
            for future in as_completed(futures):
                sample, sid, case, layout, rid, prompt_ids = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"success": False, "error_type": type(exc).__name__,
                              "error_message": str(exc)}
                warmups.append({
                    "row_type": "warmup", "policy": args.policy,
                    "load_tier": args.load_tier, "concurrency": args.concurrency,
                    "session_id": sid, "dataset": sample.get("dataset"),
                    "task": sample.get("task"), "sample_id": sample.get("sample_id"),
                    "turn_id": 0, "request_id": result.get("request_id") or rid,
                    "success": result.get("success", False),
                    "output_text": result.get("output_text", ""),
                    "ttft_ms": result.get("ttft_ms", 0),
                    "tpot_ms": result.get("tpot_ms", 0),
                    "latency_ms": result.get("total_latency_ms", 0),
                    "selected_layout": layout.get("selected_policy", ""),
                    "violated_edges": layout.get("violated_edges", []),
                    "error_type": result.get("error_type", "none"),
                    "error_message": result.get("error_message", ""),
                })
                ledger.update(sid, 0, case["segments"], layout["topological_order"],
                              policy=str(layout.get("selected_policy", args.policy)))
                previous_prompt_ids[sid] = prompt_ids
        rows.extend(warmups)

      for turn in range(1, args.turns):
        jobs = []
        for sample in cohort:
            sid = str(sample["phase19b_session_id"]); case = turn_case(sample, turn, args.stable_word_limit)
            effective = args.policy
            scope_errors: list[str] = []
            if effective == "contractkv-full":
                probe_layout = compile_layout("physical-cache-aware", case, ledger, sid, turn, args.tool_slack_ms)
                stored = certificates[sid].get("validity_scope")
                if stored:
                    current = validity_scope(args, sample, case, probe_layout)
                    scope_errors = validation_errors(
                        CertificateValidityScope(**dict(stored)), request_context(current))
                else:
                    scope_errors = ["certificate_missing_or_unissued"]
                effective = "physical-cache-aware" if not scope_errors else "raw-order"
            layout = compile_layout(effective, case, ledger, sid, turn, args.tool_slack_ms)
            request_messages = messages(case, layout["topological_order"])
            prompt_ids = tokenize(args.base_url, args.model, request_messages, True, args.timeout)
            exact_lcp_tokens = lcp_length(previous_prompt_ids.get(sid, []), prompt_ids)
            jobs.append((sample, sid, case, layout, effective, request_messages,
                         prompt_ids, exact_lcp_tokens, list(scope_errors)))
        batch_started = time.perf_counter(); batch_id = f"{args.policy}-{args.load_tier}-c{cohort_index}-t{turn}"
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {}
            for (sample, sid, case, layout, effective, request_messages,
                 prompt_ids, exact_lcp_tokens, job_scope_errors) in jobs:
                rid = f"phase19b-{args.policy}-{args.load_tier}-{sid}-t{turn}"
                future = pool.submit(send_chat_stream, args.base_url, args.model,
                                     request_messages, args.max_tokens,
                                     args.timeout, rid)
                futures[future] = (sample, sid, case, layout, effective, rid,
                                   prompt_ids, exact_lcp_tokens, job_scope_errors)
            finished = []
            for future in as_completed(futures):
                (sample, sid, case, layout, effective, rid, prompt_ids,
                 exact_lcp_tokens, job_scope_errors) = futures[future]
                try: result = future.result()
                except Exception as exc: result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
                score = score_answer(result.get("output_text", ""), sample.get("answer", ""), str(sample.get("dataset", "")))["score"] if result.get("success") else 0.0
                finished.append({"row_type": "future", "policy": args.policy, "effective_policy": effective,
                                 "load_tier": args.load_tier, "concurrency": args.concurrency, "batch_id": batch_id,
                                 "session_id": sid, "dataset": sample.get("dataset"), "task": sample.get("task"),
                                 "sample_id": sample.get("sample_id"), "turn_id": turn,
                                 "request_id": result.get("request_id") or rid, "success": result.get("success", False),
                                 "output_text": result.get("output_text", ""), "task_score": score,
                                 "ttft_ms": result.get("ttft_ms", 0), "tpot_ms": result.get("tpot_ms", 0),
                                 "latency_ms": result.get("total_latency_ms", 0),
                                 "slo_compliant": bool(result.get("success") and float(result.get("ttft_ms", 0)) <= args.slo_ms),
                                 "certificate_issued": bool(certificates.get(sid, {}).get("certificate_issued")) if args.policy == "contractkv-full" else "",
                                 "certificate_scope_mode": args.certificate_scope_mode if args.policy == "contractkv-full" else "",
                                 "certificate_scope_valid": not job_scope_errors if args.policy == "contractkv-full" else "",
                                 "certificate_scope_errors": job_scope_errors if args.policy == "contractkv-full" else [],
                                 "verification_ms": certificates.get(sid, {}).get("verification_ms", 0) if args.policy == "contractkv-full" else 0,
                                 "unhidden_verifier_ms": max(0.0, float(certificates.get(sid, {}).get("verification_ms", 0))-args.tool_slack_ms) if args.policy == "contractkv-full" else 0,
                                 "certified_stable_prefix_tokens": certificates.get(sid, {}).get("stable_prefix_tokens", 0) if args.policy == "contractkv-full" else "",
                                 "selected_layout": layout.get("selected_policy", ""), "violated_edges": layout.get("violated_edges", []),
                                 "exact_prompt_lcp_tokens": exact_lcp_tokens,
                                 "error_type": result.get("error_type", "none"), "error_message": result.get("error_message", "")})
                ledger.update(sid, turn, case["segments"], layout["topological_order"], policy=str(layout.get("selected_policy", effective)))
                previous_prompt_ids[sid] = prompt_ids
        batch_wall = (time.perf_counter()-batch_started)*1000
        for row in finished: row["batch_wall_ms"] = batch_wall
        rows.extend(finished)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    time.sleep(1.0); metrics = metric_index(args.metrics_events)
    for row in rows:
        metric = metrics.get(str(row.get("request_id", "")), {})
        row["prompt_tokens"] = metric.get("prompt_tokens", "")
        row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
        row["scheduler_initial_prefill_tokens"] = metric.get("new_prefill_tokens_this_iteration", "")
        row["new_prefill_tokens"] = max(
            0, int(metric.get("prompt_tokens", 0)) - int(metric.get("prefix_hit_tokens", 0))
        ) if metric else ""
        row["physical_block_count"] = metric.get("physical_block_count", "")
        row["reused_physical_blocks"] = metric.get("reused_physical_blocks", "")
        row["free_gpu_blocks"] = metric.get("free_gpu_blocks", "")
        exact_lcp_tokens = row.get("exact_prompt_lcp_tokens", "")
        row["dynamic_suffix_reuse_tokens"] = max(
            0, int(metric.get("prefix_hit_tokens", 0)) - int(exact_lcp_tokens)
        ) if exact_lcp_tokens not in {"", None} and metric else ""
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "future": sum(row["row_type"] == "future" for row in rows),
                      "success": sum(row.get("success") is True for row in rows),
                      "certificates": sum(row.get("certificate_issued") is True for row in rows if row["row_type"] == "canary")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
