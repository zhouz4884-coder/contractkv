#!/usr/bin/env python3
"""Run one fresh fused Exact/Typed/Benefit held-out cell."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase17_live_common import api_root, tokenize
from scripts.phase19b_end_to_end_live import load_jsonl, messages, metric_index, turn_case
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


def exact_free_path(raw: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return bool(
        raw.get("complete") and candidate.get("complete")
        and [int(value) for value in raw.get("token_ids", [])]
        == [int(value) for value in candidate.get("token_ids", [])]
        and raw.get("terminal_stop_token_id") == candidate.get("terminal_stop_token_id")
    )


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
    sessions = load_jsonl(args.sessions); rows: list[dict[str, Any]] = []
    state: dict[str, dict[str, Any]] = {}; previous_prompt_ids: dict[str, list[int]] = {}
    canary_rows: dict[str, dict[str, Any]] = {}

    for sample in sessions:
        sid = str(sample["phase19b_session_id"]); family = family_key(sample)
        case = expand_stable_segments(turn_case(sample, 0, args.stable_word_limit), 4)
        raw_layout = layout_for_level(case, "L0")
        selected_layout = raw_layout; selected_level = "L0"; tier = "RAW_FALLBACK"
        total_verify_ms = 0.0; attempts = []; raw_finish = ""
        spec = manifest["family_specs"][family]
        if args.mode != "raw" and spec["selected_level"] != "L0":
            try:
                raw = free_decode(
                    args, f"phase26d-v1-{args.load_tier}-{sid}-raw",
                    messages(case, raw_layout["topological_order"]), int(budgets[family]),
                    cache_salt=f"phase26-v1-raw-{args.load_tier}-{sid}")
                raw_finish = str(raw.get("finish_reason", ""))
            except Exception as exc:
                raw = {"complete": False, "token_ids": [], "output_text": "",
                       "terminal_stop_token_id": None, "finish_reason": "request_error"}
                raw_finish = "request_error"
                attempts.append({"decision": "INCOMPLETE", "failure_reason": exception_detail(exc)})
            if raw.get("complete"):
                level = str(spec["selected_level"]); layout = layout_for_level(case, level)
                deadline_s = (float(manifest["verification_deadline_ms"]) / 1000.0
                              if args.mode == "contract" else args.timeout)
                started = time.perf_counter()
                try:
                    candidate = free_decode(
                        args, f"phase26d-v1-{args.load_tier}-{sid}-{level}",
                        messages(case, layout["topological_order"]), int(budgets[family]),
                        cache_salt=f"phase26-v1-candidate-{args.load_tier}-{sid}-{level}",
                        request_timeout_s=deadline_s, retry_count=0)
                    candidate_ms = (time.perf_counter() - started) * 1000.0
                    total_verify_ms += candidate_ms
                    is_exact = exact_free_path(raw, candidate)
                    contract = evaluate_typed_contract(
                        str(sample["dataset"]), str(sample["task"]), raw["output_text"],
                        candidate["output_text"], qa_f1_threshold=float(manifest["qa_f1_threshold"]))
                    typed_allowed = args.mode in {"typed", "contract"} and spec["verifier_policy"] == "fused_typed"
                    decision = "EXACT" if is_exact else ("TYPED" if typed_allowed and
                                                           contract.decision == "PASS" and
                                                           candidate.get("complete") else "FAIL")
                    attempts.append({"level": level, "decision": decision,
                                     "candidate_ms": candidate_ms,
                                     "candidate_finish_reason": candidate.get("finish_reason", ""),
                                     "typed_contract": contract.as_dict()})
                    if decision in {"EXACT", "TYPED"}:
                        selected_layout = layout; selected_level = level; tier = decision
                except Exception as exc:
                    elapsed = (time.perf_counter() - started) * 1000.0
                    total_verify_ms += min(elapsed, deadline_s * 1000.0)
                    attempts.append({"level": level, "decision": "INCOMPLETE",
                                     "candidate_ms": min(elapsed, deadline_s * 1000.0),
                                     "failure_reason": exception_detail(exc)})
        state[sid] = {"layout": selected_layout, "level": selected_level, "tier": tier,
                      "verification_ms": total_verify_ms,
                      "unhidden_verifier_ms": max(0.0, total_verify_ms - args.tool_slack_ms)}
        row = {"row_type": "canary", "load_tier": args.load_tier, "mode": args.mode,
               "session_id": sid, "dataset": sample["dataset"], "task": sample["task"],
               "sample_id": str(sample["sample_id"]), "turn_id": 0,
               "effective_level": selected_level, "certificate_tier": tier,
               "certificate_issued": tier in {"EXACT", "TYPED"},
               "verification_ms": total_verify_ms,
               "unhidden_verifier_ms": state[sid]["unhidden_verifier_ms"],
               "raw_finish_reason": raw_finish, "attempts": attempts}
        rows.append(row); canary_rows[sid] = row; write_rows(args.output, rows)
        print(f"canary {len(state)}/{len(sessions)} {sid} {family} -> {tier}:{selected_level}", flush=True)

    reset_ok = reset_prefix_cache(args)
    for sample in sessions:
        sid = str(sample["phase19b_session_id"])
        case = expand_stable_segments(turn_case(sample, 0, args.stable_word_limit), 4)
        layout = state[sid]["layout"]
        warm = send_chat_stream(args.base_url, args.model, messages(case, layout["topological_order"]),
                                1, args.timeout, f"phase26d-v1-{args.load_tier}-{sid}-promotion")
        promotion_ms = float(warm.get("total_latency_ms", 0.0))
        state[sid]["promotion_ms"] = promotion_ms
        state[sid]["unhidden_verifier_ms"] = max(
            0.0, state[sid]["verification_ms"] + promotion_ms - args.tool_slack_ms)
        canary_rows[sid]["promotion_ms"] = promotion_ms
        canary_rows[sid]["unhidden_verifier_ms"] = state[sid]["unhidden_verifier_ms"]
        previous_prompt_ids[sid] = tokenize(
            args.base_url, args.model, messages(case, layout["topological_order"]), True, args.timeout)
    write_rows(args.output, rows)

    cohorts = [sessions[index:index + args.concurrency] for index in range(0, len(sessions), args.concurrency)]
    for cohort_index, cohort in enumerate(cohorts):
        for turn in range(1, args.turns):
            jobs = []
            for sample in cohort:
                sid = str(sample["phase19b_session_id"])
                case = expand_stable_segments(turn_case(sample, turn, args.stable_word_limit), 4)
                layout = layout_for_level(case, state[sid]["level"])
                request_messages = messages(case, layout["topological_order"])
                prompt_ids = tokenize(args.base_url, args.model, request_messages, True, args.timeout)
                jobs.append((sample, sid, request_messages, prompt_ids,
                             lcp_length(previous_prompt_ids[sid], prompt_ids)))
            started = time.perf_counter(); finished = []
            batch_id = f"{args.load_tier}-c{cohort_index}-t{turn}"
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {}
                for sample, sid, request_messages, prompt_ids, exact_lcp in jobs:
                    rid = f"phase26d-v1-{args.load_tier}-{sid}-t{turn}"
                    futures[pool.submit(send_chat_stream, args.base_url, args.model, request_messages,
                                        int(budgets[family_key(sample)]), args.timeout, rid)] = (
                                            sample, sid, prompt_ids, exact_lcp, rid)
                for future in as_completed(futures):
                    sample, sid, prompt_ids, exact_lcp, rid = futures[future]
                    try:
                        result = future.result()
                        score, metric, source = standard_score(
                            str(sample["dataset"]), str(sample["task"]),
                            str(result.get("output_text", "")), sample.get("answer", ""))
                    except Exception as exc:
                        result = {"success": False, "error_type": type(exc).__name__,
                                  "error_message": str(exc)}
                        score = 0.0; metric = "unavailable"; source = "request_error"
                    finished.append({"row_type": "future", "load_tier": args.load_tier,
                                     "mode": args.mode, "batch_id": batch_id,
                                     "session_id": sid, "dataset": sample["dataset"],
                                     "task": sample["task"], "sample_id": str(sample["sample_id"]),
                                     "turn_id": turn, "request_id": result.get("request_id") or rid,
                                     "success": bool(result.get("success")),
                                     "finish_reason": result.get("finish_reason", ""),
                                     "output_text": result.get("output_text", ""), "task_score": score,
                                     "metric": metric, "metric_source": source,
                                     "ttft_ms": result.get("ttft_ms", 0.0),
                                     "tpot_ms": result.get("tpot_ms", 0.0),
                                     "latency_ms": result.get("total_latency_ms", 0.0),
                                     "effective_level": state[sid]["level"],
                                     "certificate_tier": state[sid]["tier"],
                                     "certificate_issued": state[sid]["tier"] in {"EXACT", "TYPED"},
                                     "unhidden_verifier_ms_per_future": state[sid]["unhidden_verifier_ms"] / max(1, args.turns - 1),
                                     "exact_prompt_lcp_tokens": exact_lcp,
                                     "error_type": result.get("error_type", "none"),
                                     "error_message": result.get("error_message", "")})
                    previous_prompt_ids[sid] = prompt_ids
            batch_wall = (time.perf_counter() - started) * 1000.0
            for row in finished:
                row["batch_wall_ms"] = batch_wall
            rows.extend(finished); write_rows(args.output, rows)

    time.sleep(1.0); metrics = metric_index(args.metrics_events)
    for row in rows:
        if row.get("row_type") != "future":
            continue
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
        if row.get("row_type") == "canary":
            row["cache_reset_success"] = reset_ok
    write_rows(args.output, rows)
    print(json.dumps({"mode": args.mode, "rows": len(rows),
                      "future": sum(row.get("row_type") == "future" for row in rows),
                      "completed": sum(row.get("row_type") == "future" and row.get("success") for row in rows),
                      "certificates": sum(row.get("row_type") == "canary" and row.get("certificate_issued") for row in rows),
                      "cache_reset_success": reset_ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
