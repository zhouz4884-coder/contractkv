#!/usr/bin/env python3
"""Run one raw, development-ladder, or frozen broad-scope Llama cell."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_certificate_scope import CertificateValidityScope, validation_errors
from scripts.contractkv_pstp import lcp_length
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase17_live_common import generate_raw, tokenize
from scripts.phase19b_end_to_end_live import (
    compact_verify, load_jsonl, messages, metric_index, request_context,
    stable_order, turn_case, validity_scope,
)
from scripts.phase22_llama_layout_ladder import expand_stable_segments, family_key, layout_for_level


def parse_ladder(value: str) -> dict[str, float]:
    ladder = {item.split("=", 1)[0]: float(item.split("=", 1)[1])
              for item in value.split(",") if item.strip()}
    if set(ladder) != {"L0", "L1", "L2", "L3"} or ladder["L0"] != 0.0:
        raise ValueError("layout ladder must define L0-L3 with L0=0")
    if list(ladder.values()) != sorted(ladder.values()):
        raise ValueError("layout ladder fractions must be monotonic")
    return ladder


def chosen_level(args: argparse.Namespace, sample: dict[str, Any]) -> str:
    if args.mode == "raw":
        return "L0"
    if args.mode == "level":
        return args.level
    manifest = json.loads(args.qualification_manifest.read_text(encoding="utf-8"))
    return str(manifest["frozen_family_levels"].get(family_key(sample), "L0"))


def eligible_level_descent(args: argparse.Namespace, sample: dict[str, Any], requested: str) -> list[str]:
    if args.mode != "frozen" or requested == "L0":
        return [requested]
    manifest = json.loads(args.qualification_manifest.read_text(encoding="utf-8"))
    eligible = set(manifest.get("family_eligible_levels", {}).get(family_key(sample), []))
    levels = [level for level in ("L3", "L2", "L1")
              if level in eligible and int(level[1:]) <= int(requested[1:])]
    return levels or ["L0"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--mode", choices=["raw", "level", "frozen"], required=True)
    parser.add_argument("--level", choices=["L0", "L1", "L2", "L3"], default="L0")
    parser.add_argument("--layout-ladder", default="L0=0,L1=.25,L2=.5,L3=1")
    parser.add_argument("--qualification-manifest", type=Path)
    parser.add_argument("--policy-hash", required=True); parser.add_argument("--load-tier", required=True)
    parser.add_argument("--concurrency", type=int, default=2); parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--stable-pieces", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--tool-slack-ms", type=float, default=6000)
    parser.add_argument("--slo-ms", type=float, default=1500)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "frozen" and not args.qualification_manifest:
        parser.error("--qualification-manifest is required for frozen mode")

    qualification_hash = args.policy_hash
    ladder = parse_ladder(args.layout_ladder)
    if args.qualification_manifest:
        frozen = json.loads(args.qualification_manifest.read_text(encoding="utf-8"))
        qualification_hash = frozen["qualification_hash"]
        ladder = {key: float(value) for key, value in frozen["layout_ladder"].items()}
    # compact_verify and validity_scope consume these established argument names.
    args.certificate_scope_mode = "qualified_session"
    args.qualification_hash = qualification_hash

    sessions = load_jsonl(args.sessions)
    ledger = SegmentPrefixLedger()
    rows: list[dict[str, Any]] = []
    certificates: dict[str, dict[str, Any]] = {}
    previous_prompt_ids: dict[str, list[int]] = {}
    levels: dict[str, str] = {}
    cohorts = [sessions[index:index + args.concurrency]
               for index in range(0, len(sessions), args.concurrency)]

    for cohort_index, cohort in enumerate(cohorts):
        for sample in cohort:
            sid = str(sample["phase19b_session_id"])
            level = chosen_level(args, sample); levels[sid] = level
            case = expand_stable_segments(turn_case(sample, 0, args.stable_word_limit), args.stable_pieces)
            raw_layout = layout_for_level(case, "L0", ladder)
            selected_layout = raw_layout
            raw_messages = messages(case, raw_layout["topological_order"])
            if level == "L0":
                result = send_chat_stream(args.base_url, args.model, raw_messages, args.max_tokens,
                                          args.timeout, f"phase22-{args.load_tier}-{sid}-warmup")
                prompt_ids = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
                certificates[sid] = {"certificate_issued": False, "verify_decision": "NOT_REQUIRED",
                                     "verification_ms": 0.0, "stable_prefix_tokens": 0,
                                     "validity_scope": None, "raw_finish_reason": result.get("finish_reason", "")}
                previous_prompt_ids[sid] = prompt_ids
                effective = "L0"
            else:
                try:
                    raw = generate_raw(args.base_url, args.model,
                                       f"phase22-{args.load_tier}-{sid}-raw-canary",
                                       raw_messages, args.timeout, args.max_tokens)
                    attempts = []
                    issued = False; selected_level = "L0"; verify = {}
                    for candidate_level in eligible_level_descent(args, sample, level):
                        if candidate_level == "L0":
                            break
                        candidate_layout = layout_for_level(case, candidate_level, ladder)
                        attempt = compact_verify(args, sample, case, candidate_layout, raw, sid)
                        attempts.append({"level": candidate_level,
                                         "decision": attempt.get("verify_decision", "INCOMPLETE")})
                        if attempt.get("certificate_issued"):
                            issued = True; selected_level = candidate_level; verify = attempt
                            selected_layout = candidate_layout
                            break
                    if not issued:
                        selected_layout = raw_layout
                        verify = {"certificate_issued": False, "verify_decision": "REJECTED_ALL_LEVELS",
                                  "verification_ms": 0.0, "stable_prefix_tokens": 0}
                    scope = validity_scope(args, sample, case, selected_layout)
                    certificates[sid] = {**verify, "validity_scope": asdict(scope),
                                         "raw_finish_reason": raw.get("finish_reason", "unknown"),
                                         "selected_level": selected_level, "level_attempts": attempts}
                    effective = selected_level if issued else "L0"
                    previous_prompt_ids[sid] = (verify["_candidate_prompt_ids"] if issued else
                                                tokenize(args.base_url, args.model, raw_messages, True, args.timeout))
                except Exception as exc:
                    certificates[sid] = {"certificate_issued": False, "verify_decision": "INCOMPLETE",
                                         "verification_ms": 0.0, "stable_prefix_tokens": 0,
                                         "validity_scope": None, "raw_finish_reason": "error",
                                         "failure_reason": f"{type(exc).__name__}: {exc}"}
                    effective = "L0"
                    previous_prompt_ids[sid] = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
            cert = certificates[sid]
            rows.append({
                "row_type": "canary", "load_tier": args.load_tier, "session_id": sid,
                "dataset": sample.get("dataset"), "task": sample.get("task"),
                "sample_id": sample.get("sample_id"), "turn_id": 0,
                "requested_level": level, "effective_level": effective,
                "certificate_issued": bool(cert.get("certificate_issued")),
                "verify_decision": cert.get("verify_decision", "INCOMPLETE"),
                "verification_ms": cert.get("verification_ms", 0),
                "unhidden_verifier_ms": max(0.0, float(cert.get("verification_ms", 0) or 0) - args.tool_slack_ms),
                "certified_stable_prefix_tokens": cert.get("stable_prefix_tokens", 0),
                "raw_finish_reason": cert.get("raw_finish_reason", ""),
                "length_stop": cert.get("raw_finish_reason") == "length",
                "moved_stable_tokens": selected_layout["moved_stable_tokens"],
                "level_attempts": cert.get("level_attempts", []),
                "failure_reason": cert.get("failure_reason", ""),
            })
            initial_layout = selected_layout if effective != "L0" else raw_layout
            ledger.update(sid, 0, case["segments"], initial_layout["topological_order"], policy=effective)

        for turn in range(1, args.turns):
            jobs = []
            for sample in cohort:
                sid = str(sample["phase19b_session_id"]); requested = levels[sid]
                case = expand_stable_segments(turn_case(sample, turn, args.stable_word_limit), args.stable_pieces)
                raw_layout = layout_for_level(case, "L0", ladder)
                selected_level = str(certificates[sid].get("selected_level") or requested)
                selected_layout = layout_for_level(case, selected_level, ladder)
                scope_errors: list[str] = []
                admitted = bool(certificates[sid].get("certificate_issued")) and requested != "L0"
                if admitted:
                    stored = certificates[sid].get("validity_scope")
                    if stored:
                        current = validity_scope(args, sample, case, selected_layout)
                        scope_errors = validation_errors(CertificateValidityScope(**stored), request_context(current))
                    else:
                        scope_errors = ["certificate_missing_scope"]
                effective = selected_level if admitted and not scope_errors else "L0"
                layout = selected_layout if effective != "L0" else raw_layout
                request_messages = messages(case, layout["topological_order"])
                prompt_ids = tokenize(args.base_url, args.model, request_messages, True, args.timeout)
                exact_lcp = lcp_length(previous_prompt_ids.get(sid, []), prompt_ids)
                jobs.append((sample, sid, case, layout, requested, effective, scope_errors,
                             request_messages, prompt_ids, exact_lcp))
            batch_started = time.perf_counter()
            batch_id = f"{args.load_tier}-c{cohort_index}-t{turn}"
            finished = []
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {}
                for job in jobs:
                    sample, sid, case, layout, requested, effective, scope_errors, request_messages, prompt_ids, exact_lcp = job
                    rid = f"phase22-{args.load_tier}-{sid}-t{turn}"
                    future = pool.submit(send_chat_stream, args.base_url, args.model, request_messages,
                                         args.max_tokens, args.timeout, rid)
                    futures[future] = (*job, rid)
                for future in as_completed(futures):
                    sample, sid, case, layout, requested, effective, scope_errors, request_messages, prompt_ids, exact_lcp, rid = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
                    finished.append({
                        "row_type": "future", "load_tier": args.load_tier, "batch_id": batch_id,
                        "session_id": sid, "dataset": sample.get("dataset"), "task": sample.get("task"),
                        "sample_id": sample.get("sample_id"), "turn_id": turn,
                        "request_id": result.get("request_id") or rid, "success": result.get("success", False),
                        "output_text": result.get("output_text", ""), "finish_reason": result.get("finish_reason", ""),
                        "ttft_ms": result.get("ttft_ms", 0), "tpot_ms": result.get("tpot_ms", 0),
                        "latency_ms": result.get("total_latency_ms", 0),
                        "requested_level": requested, "effective_level": effective,
                        "certificate_issued": bool(certificates[sid].get("certificate_issued")),
                        "certificate_scope_valid": not scope_errors,
                        "certificate_scope_errors": scope_errors,
                        "certified_stable_prefix_tokens": certificates[sid].get("stable_prefix_tokens", 0),
                        "exact_prompt_lcp_tokens": exact_lcp,
                        "moved_stable_tokens": layout["moved_stable_tokens"],
                        "error_type": result.get("error_type", "none"), "error_message": result.get("error_message", ""),
                    })
                    ledger.update(sid, turn, case["segments"], layout["topological_order"], policy=effective)
                    previous_prompt_ids[sid] = prompt_ids
            batch_wall = (time.perf_counter() - batch_started) * 1000.0
            for row in finished:
                row["batch_wall_ms"] = batch_wall
            rows.extend(finished)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    time.sleep(1.0)
    metrics = metric_index(args.metrics_events)
    for row in rows:
        metric = metrics.get(str(row.get("request_id", "")), {})
        if row.get("row_type") != "future":
            continue
        row["prompt_tokens"] = metric.get("prompt_tokens", "")
        row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
        row["new_prefill_tokens"] = (max(0, int(metric.get("prompt_tokens", 0)) - int(metric.get("prefix_hit_tokens", 0)))
                                             if metric else "")
        exact = row.get("exact_prompt_lcp_tokens", "")
        row["dynamic_suffix_reuse_tokens"] = (max(0, int(metric.get("prefix_hit_tokens", 0)) - int(exact))
                                                       if metric and exact not in {"", None} else "")
        row["reused_physical_blocks"] = metric.get("reused_physical_blocks", "")
        row["physical_block_count"] = metric.get("physical_block_count", "")
        row["block_size"] = metric.get("block_size", "")
        row["newly_allocated_blocks"] = metric.get("newly_allocated_blocks", "")
        row["free_gpu_blocks"] = metric.get("free_gpu_blocks", "")
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "future": sum(r.get("row_type") == "future" for r in rows),
                      "completed": sum(r.get("row_type") == "future" and r.get("success") for r in rows),
                      "certificates": sum(r.get("row_type") == "canary" and r.get("certificate_issued") for r in rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
