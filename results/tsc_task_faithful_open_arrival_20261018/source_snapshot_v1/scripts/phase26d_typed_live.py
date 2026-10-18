#!/usr/bin/env python3
"""Run one fresh raw or Exact+Typed+Benefit DeepSeek held-out cell."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase17_live_common import api_root, post_json, tokenize
from scripts.phase19b_end_to_end_live import compact_verify, load_jsonl, messages, metric_index, turn_case
from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_layout_ladder import expand_stable_segments, family_key, layout_for_level
from scripts.phase26_typed_behavior_contracts import evaluate_typed_contract
from scripts.phase26a_recoverability_audit import free_decode


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def reset_prefix_cache(args: argparse.Namespace) -> bool:
    request = urllib.request.Request(
        api_root(args.base_url) + "/reset_prefix_cache", data=b"{}",
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        return response.status == 200


def exception_detail(exc: BaseException) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        if body:
            detail += f"; response={body[:1000]}"
    return detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--mode", choices=["raw", "exact", "typed", "contract"], required=True)
    parser.add_argument("--load-tier", required=True); parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--concurrency", type=int, default=2); parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=1150)
    parser.add_argument("--tool-slack-ms", type=float, default=6000)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    budgets = json.loads(args.budgets.read_text(encoding="utf-8"))["budgets"]
    threshold = float(manifest["qa_f1_threshold"])
    sessions = load_jsonl(args.sessions); rows: list[dict[str, Any]] = []
    state: dict[str, dict[str, Any]] = {}; previous_prompt_ids: dict[str, list[int]] = {}
    args.certificate_scope_mode = "qualified_session"; args.qualification_hash = manifest["qualification_hash"]

    # Turn-0 decisions are isolated from the measured namespace. Exact probes
    # are reset globally; typed candidate generations use a unique cache salt.
    for sample in sessions:
        sid = str(sample["phase19b_session_id"]); family = family_key(sample)
        case = expand_stable_segments(turn_case(sample, 0, args.stable_word_limit), 4)
        raw_layout = layout_for_level(case, "L0")
        selected_layout = raw_layout; selected_level = "L0"; tier = "RAW_FALLBACK"
        total_verify_ms = 0.0; attempts = []; raw_finish = ""
        family_spec = manifest["family_specs"].get(family, {})
        qualified = bool(family_spec.get("qualified")) and args.mode != "raw"
        if qualified:
            try:
                raw = free_decode(
                    args, f"phase26d-{args.load_tier}-{sid}-raw",
                    messages(case, raw_layout["topological_order"]), int(budgets[family]),
                    cache_salt=f"phase26-raw-canary-{args.load_tier}-{sid}")
                raw_finish = str(raw.get("finish_reason", ""))
            except Exception as exc:
                raw = {"complete": False, "output_text": "", "finish_reason": "request_error"}
                raw_finish = "request_error"
                attempts.append({"level": "L0", "exact_decision": "INCOMPLETE",
                                 "typed_decision": "NOT_RUN", "failure_reason": exception_detail(exc)})

            # A bounded contract cannot establish equivalence against an
            # incomplete reference. This is a per-session fail-closed fallback,
            # not a reason to abort the sealed cell.
            if raw.get("complete"):
                for level in family_spec.get("eligible_descent_levels", []):
                    layout = layout_for_level(case, level)
                    started = time.perf_counter()
                    try:
                        exact = compact_verify(args, sample, case, layout, raw, sid + "-" + level)
                    except Exception as exc:
                        exact = {"verify_decision": "INCOMPLETE", "certificate_issued": False,
                                 "failure_reason": exception_detail(exc)}
                    exact_ms = (time.perf_counter() - started) * 1000.0
                    total_verify_ms += exact_ms
                    attempt = {"level": level, "exact_decision": exact.get("verify_decision", "INCOMPLETE"),
                               "exact_ms": exact_ms, "typed_decision": "NOT_RUN"}
                    if exact.get("failure_reason"):
                        attempt["exact_failure_reason"] = exact["failure_reason"]
                    if exact.get("certificate_issued"):
                        selected_layout = layout; selected_level = level; tier = "EXACT"; attempts.append(attempt); break
                    level_spec = family_spec["level_specs"][level]
                    tier_b_allowed = (
                        args.mode == "typed"
                        and int(level_spec.get("unsafe_admissions", 1)) == 0
                        and int(level_spec.get("typed_count", 0)) > 0
                    ) or (
                        args.mode == "contract" and bool(level_spec.get("tier_b_enabled"))
                    )
                    if not tier_b_allowed:
                        attempts.append(attempt); continue
                    try:
                        candidate = free_decode(
                            args, f"phase26d-{args.load_tier}-{sid}-{level}-typed",
                            messages(case, layout["topological_order"]), int(budgets[family]),
                            cache_salt=f"phase26-typed-{args.load_tier}-{sid}-{level}")
                        contract = evaluate_typed_contract(
                            str(sample["dataset"]), str(sample["task"]), raw["output_text"],
                            candidate["output_text"], qa_f1_threshold=threshold)
                        total_verify_ms += float(candidate["latency_ms"]) + float(contract.runtime_ms)
                        attempt.update({"typed_decision": contract.decision,
                                        "typed_contract_type": contract.contract_type,
                                        "typed_ms": candidate["latency_ms"] + contract.runtime_ms,
                                        "typed_finish_reason": candidate["finish_reason"]})
                        attempts.append(attempt)
                        if contract.decision == "PASS" and candidate.get("complete"):
                            selected_layout = layout; selected_level = level; tier = "TYPED"; break
                    except Exception as exc:
                        attempt.update({"typed_decision": "INCOMPLETE",
                                        "typed_failure_reason": exception_detail(exc)})
                        attempts.append(attempt)
        state[sid] = {"layout": selected_layout, "level": selected_level, "tier": tier,
                      "verification_ms": total_verify_ms,
                      "unhidden_verifier_ms": max(0.0, total_verify_ms - args.tool_slack_ms),
                      "attempts": attempts, "qualified_family": qualified, "raw_finish_reason": raw_finish}
        rows.append({"row_type": "canary", "load_tier": args.load_tier, "mode": args.mode,
                     "session_id": sid, "dataset": sample["dataset"], "task": sample["task"],
                     "sample_id": str(sample["sample_id"]), "turn_id": 0,
                     "effective_level": selected_level, "certificate_tier": tier,
                     "certificate_issued": tier in {"EXACT", "TYPED"},
                     "verification_ms": total_verify_ms,
                     "unhidden_verifier_ms": state[sid]["unhidden_verifier_ms"],
                     "raw_finish_reason": raw_finish, "attempts": attempts})
        write_rows(args.output, rows)
        print(f"canary {len(state)}/{len(sessions)} {sid} {family} -> {tier}:{selected_level}", flush=True)

    reset_ok = reset_prefix_cache(args)
    # Seed exactly the layout that will be consumed by the measured future path.
    for sample in sessions:
        sid = str(sample["phase19b_session_id"]); case = expand_stable_segments(
            turn_case(sample, 0, args.stable_word_limit), 4)
        layout = state[sid]["layout"]
        warm = send_chat_stream(args.base_url, args.model, messages(case, layout["topological_order"]),
                                1, args.timeout, f"phase26d-{args.load_tier}-{sid}-promotion")
        state[sid]["promotion_ms"] = float(warm.get("total_latency_ms", 0.0))
        state[sid]["unhidden_verifier_ms"] = max(
            0.0, state[sid]["verification_ms"] + state[sid]["promotion_ms"] - args.tool_slack_ms)
        previous_prompt_ids[sid] = tokenize(
            args.base_url, args.model, messages(case, layout["topological_order"]), True, args.timeout)

    cohorts = [sessions[index:index + args.concurrency] for index in range(0, len(sessions), args.concurrency)]
    for cohort_index, cohort in enumerate(cohorts):
        for turn in range(1, args.turns):
            jobs = []
            for sample in cohort:
                sid = str(sample["phase19b_session_id"]); case = expand_stable_segments(
                    turn_case(sample, turn, args.stable_word_limit), 4)
                level = state[sid]["level"] if args.mode == "contract" else "L0"
                layout = layout_for_level(case, level)
                request_messages = messages(case, layout["topological_order"])
                prompt_ids = tokenize(args.base_url, args.model, request_messages, True, args.timeout)
                exact_lcp = lcp_length(previous_prompt_ids[sid], prompt_ids)
                jobs.append((sample, sid, case, layout, request_messages, prompt_ids, exact_lcp))
            started = time.perf_counter(); finished = []
            batch_id = f"{args.load_tier}-c{cohort_index}-t{turn}"
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {}
                for job in jobs:
                    sample, sid, case, layout, request_messages, prompt_ids, exact_lcp = job
                    rid = f"phase26d-{args.load_tier}-{sid}-t{turn}"
                    budget = int(budgets[family_key(sample)])
                    futures[pool.submit(send_chat_stream, args.base_url, args.model, request_messages,
                                        budget, args.timeout, rid)] = (*job, rid)
                for future in as_completed(futures):
                    sample, sid, case, layout, request_messages, prompt_ids, exact_lcp, rid = futures[future]
                    try:
                        result = future.result(); score, metric, source = standard_score(
                            str(sample["dataset"]), str(sample["task"]),
                            str(result.get("output_text", "")), sample.get("answer", ""))
                    except Exception as exc:
                        result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
                        score = 0.0; metric = "unavailable"; source = "request_error"
                    finished.append({"row_type": "future", "load_tier": args.load_tier,
                                     "mode": args.mode, "batch_id": batch_id,
                                     "session_id": sid, "dataset": sample["dataset"], "task": sample["task"],
                                     "sample_id": str(sample["sample_id"]), "turn_id": turn,
                                     "request_id": result.get("request_id") or rid,
                                     "success": bool(result.get("success")), "finish_reason": result.get("finish_reason", ""),
                                     "output_text": result.get("output_text", ""), "task_score": score,
                                     "metric": metric, "metric_source": source,
                                     "ttft_ms": result.get("ttft_ms", 0.0), "tpot_ms": result.get("tpot_ms", 0.0),
                                     "latency_ms": result.get("total_latency_ms", 0.0),
                                     "effective_level": state[sid]["level"], "certificate_tier": state[sid]["tier"],
                                     "certificate_issued": state[sid]["tier"] in {"EXACT", "TYPED"},
                                     "unhidden_verifier_ms_per_future": state[sid]["unhidden_verifier_ms"] / max(1, args.turns - 1),
                                     "exact_prompt_lcp_tokens": exact_lcp,
                                     "error_type": result.get("error_type", "none"),
                                     "error_message": result.get("error_message", "")})
                    previous_prompt_ids[sid] = prompt_ids
            batch_wall = (time.perf_counter() - started) * 1000.0
            for row in finished: row["batch_wall_ms"] = batch_wall
            rows.extend(finished); write_rows(args.output, rows)

    time.sleep(1.0); metrics = metric_index(args.metrics_events)
    for row in rows:
        if row.get("row_type") != "future": continue
        metric = metrics.get(str(row.get("request_id", "")), {})
        row["prompt_tokens"] = metric.get("prompt_tokens", "")
        row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
        row["new_prefill_tokens"] = (max(0, int(metric.get("prompt_tokens", 0))
                                           - int(metric.get("prefix_hit_tokens", 0))) if metric else "")
        exact = row.get("exact_prompt_lcp_tokens", "")
        row["dynamic_suffix_reuse_tokens"] = (max(0, int(metric.get("prefix_hit_tokens", 0)) - int(exact))
                                               if metric and exact not in {"", None} else "")
        row["reused_physical_blocks"] = metric.get("reused_physical_blocks", "")
        row["physical_block_count"] = metric.get("physical_block_count", "")
    for row in rows:
        if row.get("row_type") == "canary": row["cache_reset_success"] = reset_ok
    write_rows(args.output, rows)
    print(json.dumps({"mode": args.mode, "rows": len(rows),
                      "future": sum(row.get("row_type") == "future" for row in rows),
                      "completed": sum(row.get("row_type") == "future" and row.get("success") for row in rows),
                      "certificates": sum(row.get("row_type") == "canary" and row.get("certificate_issued") for row in rows),
                      "cache_reset_success": reset_ok}, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
