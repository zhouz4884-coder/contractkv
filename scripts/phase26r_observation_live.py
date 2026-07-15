#!/usr/bin/env python3
"""Run one fresh Phase 26R observation-scoped live cell."""

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
from scripts.phase17_live_common import tokenize
from scripts.phase19b_end_to_end_live import compact_verify, load_jsonl, messages, metric_index, stable_order, turn_case
from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_layout_ladder import expand_stable_segments, family_key, layout_for_level
from scripts.phase26a_recoverability_audit import free_decode
from scripts.phase26r_policy import observation_verification_gate, session_benefit_gate
from scripts.phase26r_typed_contracts import (
    contract_manifest,
    evaluate_typed_contract,
    repository_context_text,
)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


def prepare_observation(args: argparse.Namespace, manifest: dict[str, Any],
                        budgets: dict[str, int], sample: dict[str, Any], turn: int,
                        previous_prompt_ids: list[int] | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[int]]:
    sid = str(sample["phase19b_session_id"])
    family = family_key(sample)
    case = expand_stable_segments(turn_case(sample, turn, args.stable_word_limit), 4)
    raw_layout = layout_for_level(case, "L0")
    raw_messages = messages(case, raw_layout["topological_order"])
    raw_prompt_ids = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
    selected_layout = raw_layout
    selected_level = "L0"
    tier = "RAW_FALLBACK"
    attempts: list[dict[str, Any]] = []
    preparation_ms = 0.0
    raw: dict[str, Any] | None = None
    spec = manifest["family_specs"][family]
    verification_cache_salt = (
        None if args.mode == "raw" else
        f"phase26r-observation-{args.policy_hash[:16]}-{sid}-t{turn}")

    verify_admitted = args.mode == "exact"
    if args.mode == "contract":
        level = str(spec["exact_probe_level"])
        candidate_layout = layout_for_level(case, level)
        candidate_order = [str(value) for value in candidate_layout["topological_order"]]
        prefix_messages = messages(case, stable_order(case, candidate_order))
        candidate_messages = messages(case, candidate_order)
        stable_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
        candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
        stable_prefix_tokens = lcp_length(stable_ids, candidate_ids)
        economics = manifest["economics"]
        exact_gate = observation_verification_gate(
            stable_prefix_tokens=stable_prefix_tokens,
            prefill_ms_per_token=float(economics["prefill_ms_per_token"]),
            exact_pass_probability_lcb=float(spec.get("exact_pass_probability_lcb", 0.0)),
            preparation_p95_ms=float(spec.get("preparation_p95_ms", float("inf"))),
            tool_slack_ms=args.tool_slack_ms,
        )
        attempts.append({
            "stage": "observation_verification_admission",
            "decision": "PASS" if exact_gate["admit"] else "REJECT",
            "gate": exact_gate,
        })
        verify_admitted = bool(exact_gate["admit"])

    if args.mode != "raw" and verify_admitted:
        raw_started = time.perf_counter()
        try:
            raw = free_decode(
                args, f"phase26r-{args.load_tier}-{sid}-t{turn}-raw-attestation",
                raw_messages, int(budgets[family]),
                cache_salt=f"phase26r-isolated-raw-{args.load_tier}-{sid}-t{turn}",
                retry_count=0,
            )
            raw_ms = (time.perf_counter() - raw_started) * 1000.0
            preparation_ms += raw_ms
        except Exception as exc:
            raw = {"complete": False, "output_text": "", "token_ids": [],
                   "terminal_stop_token_id": None, "finish_reason": "request_error"}
            raw_ms = (time.perf_counter() - raw_started) * 1000.0
            preparation_ms += raw_ms
            attempts.append({"stage": "raw_attestation", "decision": "INCOMPLETE",
                             "latency_ms": raw_ms,
                             "failure_reason": f"{type(exc).__name__}: {exc}"})

        if raw.get("complete"):
            level = str(spec["exact_probe_level"])
            candidate_layout = layout_for_level(case, level)
            exact_started = time.perf_counter()
            try:
                exact = compact_verify(
                    args, sample, case, candidate_layout, raw,
                    f"{sid}-t{turn}-{level}", cache_salt=verification_cache_salt)
            except Exception as exc:
                exact = {"certificate_issued": False, "verify_decision": "INCOMPLETE",
                         "failure_reason": f"{type(exc).__name__}: {exc}",
                         "stable_prefix_tokens": 0}
            exact_ms = (time.perf_counter() - exact_started) * 1000.0
            preparation_ms += exact_ms
            exact_attempt = {
                "stage": "tier_e_compact_teacher_forced",
                "level": level,
                "decision": exact.get("verify_decision", "INCOMPLETE"),
                "certificate_issued": bool(exact.get("certificate_issued")),
                "latency_ms": exact_ms,
                "failure_reason": exact.get("failure_reason", ""),
                "committed_tokens": exact.get("committed_tokens", 0),
                "committed_full_blocks": exact.get("committed_full_blocks", 0),
                "raw_margin_q05": exact.get("raw_margin_q05", ""),
                "candidate_margin_q05": exact.get("candidate_margin_q05", ""),
                "degradation_q95": exact.get("degradation_q95", ""),
                "terminal_stop_margin": exact.get("terminal_stop_margin", ""),
                "robustness_reserve": exact.get("robustness_reserve", ""),
            }
            attempts.append(exact_attempt)
            if exact.get("certificate_issued"):
                selected_layout = candidate_layout
                selected_level = level
                tier = "EXACT"
            elif args.mode == "contract":
                economics = manifest["economics"]
                gate = session_benefit_gate(
                    stable_prefix_tokens=int(exact.get("stable_prefix_tokens", 0) or 0),
                    prefill_ms_per_token=float(economics["prefill_ms_per_token"]),
                    remaining_future_turns=max(0, args.turns - turn - 1),
                    tool_slack_ms=args.tool_slack_ms,
                    candidate_budget_tokens=int(budgets[family]),
                    decode_ms_per_token=float(economics["decode_ms_per_token"]),
                    pass_probability_lcb=float(spec["typed_pass_probability_lcb"]),
                    promotion_ms_estimate=float(economics["promotion_ms_estimate"]),
                    observation_scoped=True,
                )
                typed_attempt: dict[str, Any] = {
                    "stage": "tier_b_session_gate", "decision": "PASS" if gate["admit"] else "REJECT",
                    "gate": gate, "typed_contract_enabled": bool(spec["typed_contract_enabled"]),
                    "typed_disable_reason": spec["typed_disable_reason"],
                }
                if gate["admit"] and spec["typed_contract_enabled"]:
                    typed_started = time.perf_counter()
                    try:
                        candidate = free_decode(
                            args, f"phase26r-{args.load_tier}-{sid}-t{turn}-{level}-typed",
                            messages(case, candidate_layout["topological_order"]), int(budgets[family]),
                            cache_salt=f"phase26r-isolated-typed-{args.load_tier}-{sid}-t{turn}-{level}",
                            retry_count=0,
                        )
                        contract = evaluate_typed_contract(
                            str(sample["dataset"]), str(sample["task"]),
                            str(raw.get("output_text", "")), str(candidate.get("output_text", "")),
                            context_text=repository_context_text(case),
                        )
                        typed_ms = (time.perf_counter() - typed_started) * 1000.0
                        preparation_ms += typed_ms
                        provenance = contract_manifest()
                        provenance_match = (
                            contract.contract_version == provenance["version"]
                            and contract.contract_code_hash == provenance["contract_code_hash"]
                            and provenance["manifest_hash"]
                            == manifest["typed_contract_manifest"]["manifest_hash"]
                        )
                        typed_attempt.update({
                            "contract": contract.as_dict(), "provenance_match": provenance_match,
                            "candidate_output_tokens": int(candidate.get("output_tokens", 0)),
                            "candidate_budget_tokens": int(budgets[family]), "latency_ms": typed_ms,
                        })
                        if candidate.get("complete") and contract.decision == "PASS" and provenance_match:
                            promote_started = time.perf_counter()
                            send_chat_stream(
                                args.base_url, args.model,
                                messages(case, candidate_layout["topological_order"]), 1, args.timeout,
                                f"phase26r-{args.load_tier}-{sid}-t{turn}-{level}-promotion",
                            )
                            promotion_ms = (time.perf_counter() - promote_started) * 1000.0
                            preparation_ms += promotion_ms
                            typed_attempt["promotion_ms"] = promotion_ms
                            selected_layout = candidate_layout
                            selected_level = level
                            tier = "TYPED"
                    except Exception as exc:
                        typed_attempt.update({"decision": "INCOMPLETE",
                                              "failure_reason": f"{type(exc).__name__}: {exc}"})
                attempts.append(typed_attempt)

    selected_messages = messages(case, selected_layout["topological_order"])
    selected_prompt_ids = tokenize(args.base_url, args.model, selected_messages, True, args.timeout)
    exact_lcp = lcp_length(previous_prompt_ids or [], selected_prompt_ids) if previous_prompt_ids else 0
    unhidden_ms = max(0.0, preparation_ms - args.tool_slack_ms)
    prep = {
        "session_id": sid, "family": family, "turn_id": turn,
        "observation_epoch": turn,
        "observation_identity": __import__("hashlib").sha256(
            f"{sid}:{turn}:{repository_context_text(case)}".encode()).hexdigest(),
        "certificate_scope": "observation",
        "effective_level": selected_level,
        "certificate_tier": tier,
        "certificate_issued": tier in {"EXACT", "TYPED"},
        "preparation_ms": preparation_ms,
        "unhidden_verifier_ms": unhidden_ms,
        "attempts": attempts,
        "raw_reference": raw,
        "exact_prompt_lcp_tokens": exact_lcp,
        # A compiled request may consume only the blocks published by its own
        # observation-scoped verifier. Raw fallback keeps vLLM's native APC.
        "observation_cache_salt": (
            verification_cache_salt if tier in {"EXACT", "TYPED"} else None),
        "selected_prompt_ids": selected_prompt_ids,
    }
    return prep, selected_messages, selected_prompt_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--mode", choices=["raw", "exact", "contract"], required=True)
    parser.add_argument("--load-tier", required=True)
    parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=1150)
    parser.add_argument("--tool-slack-ms", type=float, default=6000.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.certificate_scope_mode = "observation"
    args.qualification_hash = args.policy_hash

    sessions = load_jsonl(args.sessions)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    budgets = json.loads(args.budgets.read_text(encoding="utf-8"))["budgets"]
    if manifest["qualification_hash"] != args.policy_hash:
        raise RuntimeError("policy hash mismatch")
    if contract_manifest()["manifest_hash"] != manifest["typed_contract_manifest"]["manifest_hash"]:
        raise RuntimeError("typed contract provenance mismatch")

    rows: list[dict[str, Any]] = []
    previous: dict[str, list[int]] = {}
    cohorts = [sessions[i:i + args.concurrency] for i in range(0, len(sessions), args.concurrency)]
    for cohort_index, cohort in enumerate(cohorts):
        for turn in range(args.turns):
            prepared = []
            # Match the declared live concurrency during slack-time
            # preparation. Each transaction has a disjoint request ID and
            # cache salt, so parallel verification cannot publish across
            # sessions.
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                prep_futures = {}
                for sample in cohort:
                    sid = str(sample["phase19b_session_id"])
                    future = pool.submit(
                        prepare_observation, args, manifest, budgets, sample,
                        turn, previous.get(sid))
                    prep_futures[future] = sample
                for future in as_completed(prep_futures):
                    sample = prep_futures[future]
                    prep, request_messages, prompt_ids = future.result()
                    prepared.append((sample, prep, request_messages, prompt_ids))

            batch_started = time.perf_counter()
            completed = []
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {}
                for sample, prep, request_messages, prompt_ids in prepared:
                    sid = str(sample["phase19b_session_id"])
                    rid = f"phase26r-{args.load_tier}-{sid}-t{turn}-measured"
                    future = pool.submit(
                        send_chat_stream, args.base_url, args.model, request_messages,
                        int(budgets[family_key(sample)]), args.timeout, rid,
                        14014, prep["observation_cache_salt"])
                    futures[future] = (sample, prep, prompt_ids, rid)
                for future in as_completed(futures):
                    sample, prep, prompt_ids, rid = futures[future]
                    sid = str(sample["phase19b_session_id"])
                    try:
                        result = future.result()
                        score, metric, source = standard_score(
                            str(sample["dataset"]), str(sample["task"]),
                            str(result.get("output_text", "")), sample.get("answer", ""))
                    except Exception as exc:
                        result = {"success": False, "error_type": type(exc).__name__,
                                  "error_message": str(exc), "output_text": ""}
                        score, metric, source = 0.0, "unavailable", "request_error"
                    raw = prep.pop("raw_reference")
                    raw_score = ""
                    quality_drop = ""
                    if raw and raw.get("complete"):
                        raw_score, _, _ = standard_score(
                            str(sample["dataset"]), str(sample["task"]),
                            str(raw.get("output_text", "")), sample.get("answer", ""))
                        quality_drop = max(0.0, float(raw_score) - float(score))
                    completed.append({
                        "row_type": "request", "load_tier": args.load_tier, "mode": args.mode,
                        "batch_id": f"{args.load_tier}-c{cohort_index}-t{turn}",
                        "dataset": sample["dataset"], "task": sample["task"],
                        "sample_id": str(sample["sample_id"]), "request_id": result.get("request_id") or rid,
                        "success": bool(result.get("success")), "finish_reason": result.get("finish_reason", ""),
                        "output_text": result.get("output_text", ""), "task_score": score,
                        "raw_reference_output_text": (raw.get("output_text", "") if raw else ""),
                        "raw_reference_finish_reason": (raw.get("finish_reason", "") if raw else ""),
                        "raw_reference_score": raw_score, "same_process_quality_drop": quality_drop,
                        "policy_quality_violation": bool(
                            prep["effective_level"] != "L0" and quality_drop != "" and float(quality_drop) > .03),
                        "metric": metric, "metric_source": source,
                        "ttft_ms": result.get("ttft_ms", 0.0), "tpot_ms": result.get("tpot_ms", 0.0),
                        "latency_ms": result.get("total_latency_ms", 0.0),
                        "net_ttft_ms": float(result.get("ttft_ms", 0.0)) + prep["unhidden_verifier_ms"],
                        "error_type": result.get("error_type", "none"),
                        "error_message": result.get("error_message", ""),
                        **{key: value for key, value in prep.items() if key != "selected_prompt_ids"},
                    })
                    previous[sid] = prompt_ids
            batch_wall_ms = (time.perf_counter() - batch_started) * 1000.0
            for row in completed:
                row["batch_wall_ms"] = batch_wall_ms
            rows.extend(completed)
            write_rows(args.output, rows)
            print(f"{args.load_tier} cohort={cohort_index} turn={turn} rows={len(rows)}", flush=True)

    time.sleep(1.0)
    metrics = metric_index(args.metrics_events)
    for row in rows:
        metric = metrics.get(str(row["request_id"]), {})
        row["prompt_tokens"] = metric.get("prompt_tokens", "")
        row["prefix_hit_tokens"] = metric.get("prefix_hit_tokens", "")
        row["new_prefill_tokens"] = (
            max(0, int(metric.get("prompt_tokens", 0)) - int(metric.get("prefix_hit_tokens", 0)))
            if metric else "")
        lcp = row.get("exact_prompt_lcp_tokens", "")
        committed = max(
            [int(attempt.get("committed_tokens", 0) or 0)
             for attempt in row.get("attempts", [])
             if attempt.get("certificate_issued")]
            or [0])
        certified = row.get("certificate_tier") in {"EXACT", "TYPED"}
        allowed_reuse = max(int(lcp or 0), committed) if certified else 0
        prefix_hit = int(metric.get("prefix_hit_tokens", 0)) if metric else 0
        row["authorized_prefix_reuse_tokens"] = allowed_reuse
        row["raw_fallback_prefix_reuse_tokens"] = (
            prefix_hit if metric and not certified else 0)
        row["certified_dynamic_suffix_reuse_tokens"] = (
            max(0, prefix_hit - allowed_reuse)
            if metric and certified and lcp not in {"", None} else 0)
        row["dynamic_suffix_reuse_tokens"] = row[
            "certified_dynamic_suffix_reuse_tokens"]
        row["reused_physical_blocks"] = metric.get("reused_physical_blocks", "")
        row["physical_block_count"] = metric.get("physical_block_count", "")
    write_rows(args.output, rows)
    print(json.dumps({
        "mode": args.mode, "requests": len(rows),
        "completed": sum(bool(row["success"]) for row in rows),
        "exact": sum(row["certificate_tier"] == "EXACT" for row in rows),
        "typed": sum(row["certificate_tier"] == "TYPED" for row in rows),
        "quality_violations": sum(bool(row["policy_quality_violation"]) for row in rows),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
