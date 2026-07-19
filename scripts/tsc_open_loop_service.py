#!/usr/bin/env python3
"""Run one real-vLLM TSC open-loop service cell on a frozen trace."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream, send_chat_stream_async
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, compile_static_policy
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case
from scripts.phase17_live_common import generate_raw
from scripts.contractkv_pstp import lcp_length
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase17_live_common import api_root, digest, post_json, tokenize


POLICIES = ("D0-native-apc", "D1-frozen-safe", "D2-full-contractkv")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def slope(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((value - mx) ** 2 for value in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator if denominator else 0.0


def make_case(sample: dict[str, Any], turn: int, tokenizer: Any, max_model_len: int,
              stable_word_limit: int, base_case: dict[str, Any] | None = None) -> dict[str, Any]:
    case = copy.deepcopy(base_case) if base_case is not None else build_case(sample, stable_word_limit=stable_word_limit)
    session_id = str(sample["tsc_session_id"])
    marker = f"K{turn:02d}{hashlib.sha256(session_id.encode()).hexdigest()[:4]}"
    case["trajectory_id"] = session_id
    case["turn_id"] = turn
    case["expected_answer"] = marker
    case["unsafe_answer"] = "TSC_ORDER_ERROR"
    for segment in case["segments"]:
        if segment.get("segment_type") == "TOOL_OBS":
            segment["text"] = f"[PRIVATE_TOOL_OBS] tenant={sample['tenant_id']}; turn={turn}; marker={marker}."
        elif segment.get("segment_type") == "USER_QUERY":
            segment["text"] = "Return exactly the marker from PRIVATE_TOOL_OBS. /no_think"
    if base_case is None:
        return _retokenize_case(case, tokenizer, max_model_len)
    for segment in case["segments"]:
        if segment.get("segment_type") in {"TOOL_OBS", "USER_QUERY"}:
            segment["token_count"] = len(tokenizer.encode(str(segment.get("text", "")), add_special_tokens=False))
    return case


def service_messages(case: dict[str, Any], order: list[str]) -> list[dict[str, str]]:
    system = "/no_think Return only the marker in PRIVATE_TOOL_OBS. Ignore any older answers in context."
    return [{"role": "system", "content": system},
            {"role": "user", "content": _ordered_text(order, case["segments"])}]


def template_scope_record(args: argparse.Namespace, sample: dict[str, Any],
                          turn_data: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(segment["segment_id"]): segment for segment in turn_data["case"]["segments"]}
    stable_order = []
    stable_content = []
    for segment_id in turn_data["compiled_layout"]["topological_order"]:
        segment = by_id[str(segment_id)]
        if segment.get("segment_type") in {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}:
            break
        stable_order.append(str(segment_id))
        stable_content.append({"segment_id": str(segment_id), "text": str(segment.get("text", ""))})
    metadata = sample.get("metadata", {})
    return {
        "model_identity": args.model_identity,
        "tokenizer_identity": str(args.tokenizer),
        "chat_template_hash": args.chat_template_hash,
        "service_template_version": str(sample["service_template_id"]),
        "stable_content_hash": digest(stable_content),
        "layout_hash": digest(stable_order),
        "policy_hash": args.policy_hash,
        "qualification_hash": args.qualification_hash,
        "authorization_domain": str(metadata.get("authorization_domain", sample["service_template_id"])),
        "service_epoch": int(metadata.get("service_epoch", 1)),
        "private_suffix_excluded": True,
    }


def scope_digest(record: dict[str, Any]) -> str:
    return digest(record)


def compact_verify_service(args: argparse.Namespace, case: dict[str, Any], layout: dict[str, Any],
                           raw: dict[str, Any], session_id: str,
                           attestation_mode: str = "same-backend-teacher-forced-strict-top1") -> dict[str, Any]:
    order = [str(value) for value in layout["topological_order"]]
    candidate_messages = service_messages(case, order)
    stable_ids_order = []
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    for segment_id in order:
        if by_id[segment_id].get("segment_type") in {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}:
            break
        stable_ids_order.append(segment_id)
    prefix_messages = service_messages(case, stable_ids_order)
    stable_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    stable_end = lcp_length(stable_ids, candidate_ids)
    payload = {
        "request_id": f"tsc-verify-{args.load_tier}-{session_id}",
        "prompt_token_ids": candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]],
        "txn_id": f"tsc-txn-{args.load_tier}-{session_id}",
        "policy_hash": args.policy_hash, "policy_version": "tsc-service-frozen-v0",
        "attestation_mode": attestation_mode,
        "stable_prefix_end_token": stable_end, "verify_start_token": len(candidate_ids),
        "reference_answer_ids": raw["token_ids"], "reference_raw_margins": raw["margins"],
        "terminal_stop_token_id": raw["terminal_stop_token_id"],
        "stable_content_hash": digest(stable_ids), "layout_hash": digest(candidate_ids),
        "dependency_graph_hash": digest([(segment["segment_id"], segment.get("dependencies", [])) for segment in case["segments"]]),
        "timeout_s": args.timeout, "cache_salt": f"{args.policy_hash}:{session_id}",
    }
    started = time.perf_counter()
    body = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
    elapsed = (time.perf_counter() - started) * 1000.0
    return {**body, "verification_ms": elapsed, "stable_prefix_tokens": stable_end}


def compile_session(sample: dict[str, Any], turns: int, tokenizer: Any,
                    max_model_len: int, stable_word_limit: int) -> dict[int, dict[str, Any]]:
    ledger = SegmentPrefixLedger()
    output: dict[int, dict[str, Any]] = {}
    sid = str(sample["tsc_session_id"])
    base_case = make_case(sample, 0, tokenizer, max_model_len, stable_word_limit)
    for turn in range(turns):
        case = base_case if turn == 0 else make_case(
            sample, turn, tokenizer, max_model_len, stable_word_limit, base_case=base_case)
        raw = compile_static_policy(case["segments"], "raw-order")
        compiled = cache_aware_posc_compile(case["segments"], ledger, sid, turn, 6000.0)
        output[turn] = {
            "case": case,
            "raw_layout": raw,
            "compiled_layout": compiled,
            "raw_messages": service_messages(case, raw["topological_order"]),
            "compiled_messages": service_messages(case, compiled["topological_order"]),
        }
        ledger.update(sid, turn, case["segments"], compiled["topological_order"], policy="contractkv-caposc")
    if len(output) > 1:
        first = tokenizer.apply_chat_template(
            output[0]["compiled_messages"], tokenize=True, add_generation_prompt=True)
        second = tokenizer.apply_chat_template(
            output[1]["compiled_messages"], tokenize=True, add_generation_prompt=True)
        stable_prefix_tokens = lcp_length(first, second)
    else:
        stable_prefix_tokens = 0
    for item in output.values():
        item["allowed_prefix_tokens"] = stable_prefix_tokens
    return output


def eligible_families(path: Path, model_identity: str) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    levels = payload["models"][model_identity]
    return {family for family, level in levels.items() if str(level) != "L0"}


def registration_scope(args: argparse.Namespace, sample: dict[str, Any]) -> str:
    if args.certificate_scope_mode == "service_template":
        return str(sample["service_template_id"])
    return str(sample["tsc_session_id"])


def request_cache_salt(args: argparse.Namespace, sample: dict[str, Any]) -> str | None:
    """Match certificate scope without weakening the unsalted native baseline."""
    if args.certificate_scope_mode == "service_template" or args.policy == "D2-full-contractkv":
        return f"{args.policy_hash}:{registration_scope(args, sample)}"
    return None


def registration_one(args: argparse.Namespace, sample: dict[str, Any], prepared: dict[int, dict[str, Any]],
                     eligible: bool, scope_id: str) -> dict[str, Any]:
    sid = str(sample["tsc_session_id"])
    row = {
        "session_id": sid, "registration_scope_id": scope_id,
        "certificate_scope_mode": args.certificate_scope_mode,
        "family": sample["tsc_family"], "eligible": eligible,
        "certificate_issued": False, "verify_decision": "NOT_RUN", "verification_ms": 0.0,
        "registration_ms": 0.0, "unhidden_verification_ms": 0.0, "error_type": "none", "error_message": "",
        "prospective_qualification_pass": eligible,
    }
    started = time.perf_counter()
    cache_salt = request_cache_salt(args, sample)
    try:
        turn0 = prepared[0]
        if args.policy == "D0-native-apc" or not eligible:
            result = send_chat_stream(args.base_url, args.model, turn0["raw_messages"], args.max_tokens,
                                      args.timeout, f"{args.cell_id}-register-{sid}",
                                      cache_salt=cache_salt)
            row["certificate_issued"] = False
            row["verify_decision"] = "RAW_REGISTRATION"
        elif args.policy == "D1-frozen-safe":
            result = send_chat_stream(args.base_url, args.model, turn0["compiled_messages"], args.max_tokens,
                                      args.timeout, f"{args.cell_id}-register-{sid}",
                                      cache_salt=cache_salt)
            row["certificate_issued"] = True
            row["verify_decision"] = "FROZEN_SAFE"
        else:
            deployment_attestation = args.certificate_scope_mode == "service_template"
            reference_messages = turn0["compiled_messages"] if deployment_attestation else turn0["raw_messages"]
            raw = generate_raw(args.base_url, args.model, f"{args.cell_id}-canary-raw-{sid}",
                               reference_messages, args.timeout, args.registration_max_tokens)
            verify = compact_verify_service(
                args, turn0["case"], turn0["compiled_layout"], raw, scope_id,
                attestation_mode=("prospective-qualified-template-exact-path-v1"
                                  if deployment_attestation else "same-backend-teacher-forced-strict-top1"),
            )
            row["certificate_issued"] = bool(verify.get("certificate_issued"))
            row["verify_decision"] = str(verify.get("verify_decision", ""))
            row["verification_ms"] = number(verify.get("verification_ms"))
            for key in ("txn_state", "failure_reason", "committed_tokens", "committed_full_blocks",
                        "certificate_hash", "raw_margin_q05", "candidate_margin_q05",
                        "degradation_q95", "terminal_stop_margin", "stable_prefix_tokens"):
                row[key] = verify.get(key, "")
            row["deployment_attestation_mode"] = (
                "prospective-qualified-template-exact-path-v1" if deployment_attestation
                else "session-strict-output-path-v1"
            )
            record = template_scope_record(args, sample, turn0)
            row["certificate_scope_digest"] = scope_digest(record)
            row.update({f"scope_{key}": value for key, value in record.items()})
            warm_messages = turn0["compiled_messages"] if row["certificate_issued"] else turn0["raw_messages"]
            result = send_chat_stream(args.base_url, args.model, warm_messages, args.max_tokens,
                                      args.timeout, f"{args.cell_id}-register-warm-{sid}",
                                      cache_salt=cache_salt)
        if not result.get("success", True):
            raise RuntimeError(str(result.get("error_message", "registration request failed")))
    except Exception as exc:
        row.update({"certificate_issued": False, "verify_decision": "INCOMPLETE",
                    "error_type": type(exc).__name__, "error_message": str(exc)})
    row["registration_ms"] = (time.perf_counter() - started) * 1000.0
    row["unhidden_verification_ms"] = max(0.0, row["registration_ms"] - args.tool_slack_ms)
    return row


def register(args: argparse.Namespace, sessions: list[dict[str, Any]],
             prepared: dict[str, dict[int, dict[str, Any]]], eligible: set[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    representatives: dict[str, dict[str, Any]] = {}
    members: dict[str, list[str]] = defaultdict(list)
    for sample in sessions:
        scope_id = registration_scope(args, sample)
        representatives.setdefault(scope_id, sample)
        members[scope_id].append(str(sample["tsc_session_id"]))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.registration_concurrency) as pool:
        futures = [pool.submit(registration_one, args, sample, prepared[sample["tsc_session_id"]],
                               sample["tsc_family"] in eligible, scope_id)
                   for scope_id, sample in representatives.items()]
        for future in as_completed(futures):
            row = future.result()
            row["sessions_in_scope"] = len(members[row["registration_scope_id"]])
            rows.append(row)
    rows.sort(key=lambda row: row["registration_scope_id"])
    by_scope = {str(row["registration_scope_id"]): row for row in rows}
    index = {str(sample["tsc_session_id"]): by_scope[registration_scope(args, sample)] for sample in sessions}
    return rows, index


async def request_at(args: argparse.Namespace, session: Any, deadline: float, measurement_start: float,
                     arrival: dict[str, Any], messages_value: list[dict[str, str]], marker: str,
                     effective_policy: str, scope_check: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(max(0.0, deadline - time.perf_counter()))
    actual_start = time.perf_counter()
    rid = f"{args.cell_id}-{arrival['session_id']}-t{arrival['turn_id']}"
    try:
        result = await send_chat_stream_async(session, args.base_url, args.model, messages_value,
                                              args.max_tokens, rid,
                                              cache_salt=scope_check["request_cache_salt"])
    except Exception as exc:
        result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
    completed = time.perf_counter()
    result.update({
        "cell_id": args.cell_id, "model_identity": args.model_identity, "policy": args.policy_label or args.policy,
        "effective_policy": effective_policy, "sequence": arrival["sequence"],
        "session_id": arrival["session_id"], "turn_id": arrival["turn_id"],
        "arrival_offset_ms": (deadline - measurement_start) * 1000.0,
        "client_send_lag_ms": max(0.0, (actual_start - deadline) * 1000.0),
        "completion_offset_ms": (completed - measurement_start) * 1000.0,
        "quality_sanity": marker in str(result.get("output_text", "")),
        **scope_check,
    })
    return result


async def replay(args: argparse.Namespace, arrivals: list[dict[str, Any]], sessions_by_id: dict[str, dict[str, Any]],
                 prepared: dict[str, dict[int, dict[str, Any]]], registration: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    connector = aiohttp.TCPConnector(limit=0)
    measurement_start = time.perf_counter() + 1.0
    cumulative = 0.0
    tasks = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for arrival in arrivals[:args.max_requests or None]:
            gap = float(arrival["unit_exponential_gap"]) / (
                args.arrival_rate_rps * (2.0 if args.arrival_mode == "onoff" else 1.0))
            if args.arrival_mode == "onoff":
                position = cumulative % (args.on_seconds + args.off_seconds)
                if position >= args.on_seconds:
                    cumulative += args.on_seconds + args.off_seconds - position
                    position = 0.0
                if position + gap > args.on_seconds:
                    cumulative += args.on_seconds + args.off_seconds - position
            cumulative += gap
            sid, turn = str(arrival["session_id"]), int(arrival["turn_id"])
            sample, turn_data = sessions_by_id[sid], prepared[sid][turn]
            frozen_eligible = sample["tsc_family"] in args.eligible_families
            live_issued = truth(registration[sid]["certificate_issued"])
            scope_started = time.perf_counter()
            request_scope = template_scope_record(args, sample, turn_data)
            request_scope_digest = scope_digest(request_scope)
            registered_scope_digest = str(registration[sid].get("certificate_scope_digest", request_scope_digest))
            scope_match = (args.certificate_scope_mode != "service_template"
                           or request_scope_digest == registered_scope_digest)
            scope_check_ms = (time.perf_counter() - scope_started) * 1000.0
            use_compiled = (
                args.policy == "D1-frozen-safe" and frozen_eligible
            ) or (
                args.policy == "D2-full-contractkv" and frozen_eligible and live_issued and scope_match
            )
            effective = "compiled" if use_compiled else "raw-fallback"
            selected_messages = turn_data["compiled_messages"] if use_compiled else turn_data["raw_messages"]
            marker = str(turn_data["case"]["expected_answer"])
            tasks.append(asyncio.create_task(request_at(
                args, session, measurement_start + cumulative, measurement_start, arrival,
                selected_messages, marker, effective, {
                    "scope_check_pass": scope_match,
                    "request_scope_digest": request_scope_digest,
                    "registered_scope_digest": registered_scope_digest,
                    "private_suffix_excluded": True,
                    "scope_check_ms": scope_check_ms,
                    "service_template_id": sample["service_template_id"],
                    "tenant_id": sample["tenant_id"],
                    "authorization_domain": request_scope["authorization_domain"],
                    "allowed_prefix_tokens": turn_data["allowed_prefix_tokens"],
                    "request_cache_salt": request_cache_salt(args, sample),
                    "reuse_distance_requests": arrival.get("reuse_distance_requests", ""),
                },
            )))
        await asyncio.sleep(max(0.0, measurement_start + cumulative - time.perf_counter()))
        done, pending = await asyncio.wait(tasks, timeout=args.drain_seconds)
        for task in pending:
            task.cancel()
    rows = []
    for task in done:
        try:
            rows.append(task.result())
        except Exception as exc:
            rows.append({"success": False, "error_type": type(exc).__name__, "error_message": str(exc)})
    for _ in pending:
        rows.append({"success": False, "error_type": "drain_timeout", "error_message": "outstanding after drain"})
    args.offered_duration_s = cumulative
    return rows


def load_metric_events(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(offset)
        return [json.loads(line) for line in handle.read().decode("utf-8", errors="replace").splitlines() if line.strip()]


def join_metrics(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    index: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "prefix_cache_request_observation" and event.get("initial_prefill_observation"):
            index[str(event.get("request_id", ""))] = event
    for row in rows:
        event = index.get(str(row.get("request_id", "")), {})
        row.update({
            "metric_join_success": bool(event), "prompt_tokens": event.get("prompt_tokens", ""),
            "prefix_hit_tokens": event.get("prefix_hit_tokens", ""),
            "new_prefill_tokens": max(0, int(event.get("prompt_tokens", 0)) - int(event.get("prefix_hit_tokens", 0))) if event else "",
            "scheduler_wait_ms": event.get("scheduler_wait_ms", ""),
            "scheduler_running_requests": event.get("scheduler_running_requests", ""),
            "scheduler_waiting_requests": event.get("scheduler_waiting_requests", ""),
            "used_gpu_blocks": event.get("used_gpu_blocks", ""), "free_gpu_blocks": event.get("free_gpu_blocks", ""),
            "physical_block_count": event.get("physical_block_count", ""),
            "reused_physical_blocks": event.get("reused_physical_blocks", ""),
            "physical_block_ids": event.get("physical_block_ids", []),
            "physical_block_hashes": event.get("physical_block_hashes", []),
            "physical_block_refcounts": event.get("physical_block_refcounts", []),
            "block_size": event.get("block_size", ""),
            "prefix_cache_evictions": event.get("prefix_cache_evictions", ""),
            "prefix_cache_evictions_availability": event.get(
                "prefix_cache_evictions_availability", "unavailable"),
        })


def summarize(args: argparse.Namespace, rows: list[dict[str, Any]], registration_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    success = [row for row in rows if truth(row.get("success"))]
    ttft = [number(row.get("ttft_ms")) for row in success]
    waits = [number(row.get("scheduler_wait_ms")) for row in success if row.get("scheduler_wait_ms") not in ("", None)]
    send_lags = [number(row.get("client_send_lag_ms")) for row in success]
    arrivals = [number(row.get("arrival_offset_ms")) / 1000.0 for row in success if row.get("scheduler_wait_ms") not in ("", None)]
    final_completion = max((number(row.get("completion_offset_ms")) for row in success), default=0.0) / 1000.0
    service_wall = max(final_completion, args.offered_duration_s, 1e-9)
    unhidden_total = sum(number(row.get("unhidden_verification_ms")) for row in registration_rows)
    unhidden_per_future = unhidden_total / max(1, len(rows))
    hash_domains: dict[str, set[str]] = defaultdict(set)
    dynamic_suffix_reuse_blocks = 0
    for row in success:
        reused = int(number(row.get("reused_physical_blocks")))
        for value in row.get("physical_block_hashes", [])[:reused]:
            if value:
                hash_domains[str(value)].add(str(row.get("authorization_domain", "")))
        hit_tokens = int(number(row.get("prefix_hit_tokens")))
        allowed_tokens = int(number(row.get("allowed_prefix_tokens")))
        block_size = max(1, int(number(row.get("block_size"))))
        dynamic_suffix_reuse_blocks += max(0, hit_tokens - allowed_tokens - block_size) // block_size
    unauthorized_hashes = sum(len(domains) > 1 for domains in hash_domains.values())
    reuse_distances = [number(row.get("reuse_distance_requests")) for row in success
                       if number(row.get("reuse_distance_requests")) >= 0]
    zero_hit_after_prior = sum(
        number(row.get("reuse_distance_requests")) >= 0 and number(row.get("prefix_hit_tokens")) == 0
        for row in success
    )
    output = []
    for slo in args.slo_buckets_ms:
        compliant = [row for row in success if truth(row.get("quality_sanity"))
                     and number(row.get("ttft_ms")) + number(row.get("scope_check_ms")) + unhidden_per_future <= slo]
        verifier_calls = sum(row.get("verify_decision") not in {"NOT_RUN", "RAW_REGISTRATION", "FROZEN_SAFE"}
                             for row in registration_rows)
        output.append({
            "experiment_version": "tsc-service-v1",
            "cell_id": args.cell_id, "model_identity": args.model_identity, "policy": args.policy_label or args.policy,
            "arrival_mode": args.arrival_mode, "arrival_rate_rps": args.arrival_rate_rps, "slo_ttft_ms": slo,
            "offered_requests": len(rows), "completed_requests": len(success),
            "completion_rate": len(success) / max(1, len(rows)),
            "quality_sanity_rate": sum(truth(row.get("quality_sanity")) for row in success) / max(1, len(success)),
            "achieved_throughput_rps": len(success) / service_wall,
            "slo_compliant_requests": len(compliant), "slo_compliant_goodput_rps": len(compliant) / service_wall,
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0, "p50_ttft_ms": percentile(ttft, .50),
            "p95_ttft_ms": percentile(ttft, .95), "p99_ttft_ms": percentile(ttft, .99),
            "mean_tpot_ms": statistics.mean(number(row.get("tpot_ms")) for row in success) if success else 0.0,
            "mean_latency_ms": statistics.mean(number(row.get("total_latency_ms")) for row in success) if success else 0.0,
            "mean_scheduler_wait_ms": statistics.mean(waits) if waits else 0.0,
            "p95_scheduler_wait_ms": percentile(waits, .95), "p99_scheduler_wait_ms": percentile(waits, .99),
            "p95_client_send_lag_ms": percentile(send_lags, .95),
            "p99_client_send_lag_ms": percentile(send_lags, .99),
            "queue_wait_slope_sec_per_sec": slope(arrivals, [value / 1000.0 for value in waits]),
            "max_scheduler_waiting_requests": max((int(number(row.get("scheduler_waiting_requests"))) for row in success), default=0),
            "timeout_or_drop_rate": 1.0 - len(success) / max(1, len(rows)),
            "mean_prompt_tokens": statistics.mean(number(row.get("prompt_tokens")) for row in success) if success else 0.0,
            "mean_prefix_hit_tokens": statistics.mean(number(row.get("prefix_hit_tokens")) for row in success) if success else 0.0,
            "mean_new_prefill_tokens": statistics.mean(number(row.get("new_prefill_tokens")) for row in success) if success else 0.0,
            "template_prefix_hit_ratio": (sum(number(row.get("prefix_hit_tokens")) for row in success)
                                          / max(sum(number(row.get("prompt_tokens")) for row in success), 1.0)),
            "mean_reuse_distance_requests": statistics.mean(reuse_distances) if reuse_distances else 0.0,
            "p95_reuse_distance_requests": percentile(reuse_distances, .95),
            "zero_prefix_hit_after_prior_template_requests": zero_hit_after_prior,
            "prefix_cache_evictions_observable": False,
            "prefix_cache_evictions_observation": "unavailable_in_vllm_scheduler_probe",
            "metric_join_rate": sum(truth(row.get("metric_join_success")) for row in success) / max(1, len(success)),
            "peak_used_gpu_blocks": max((int(number(row.get("used_gpu_blocks"))) for row in success), default=0),
            "minimum_free_gpu_blocks": min((int(number(row.get("free_gpu_blocks"))) for row in success), default=0),
            "certificate_issue_rate": sum(truth(row.get("certificate_issued")) for row in registration_rows) / max(1, len(registration_rows)),
            "mean_verification_ms": statistics.mean(number(row.get("verification_ms")) for row in registration_rows),
            "unhidden_verification_ms_per_future_request": unhidden_per_future,
            "raw_fallback_rate": sum(row.get("effective_policy") == "raw-fallback" for row in rows) / max(1, len(rows)),
            "scope_check_pass_rate": sum(truth(row.get("scope_check_pass")) for row in rows) / max(1, len(rows)),
            "mean_scope_check_ms": statistics.mean(number(row.get("scope_check_ms")) for row in rows),
            "p95_scope_check_ms": percentile([number(row.get("scope_check_ms")) for row in rows], .95),
            "private_suffix_exclusion_rate": sum(truth(row.get("private_suffix_excluded")) for row in rows) / max(1, len(rows)),
            "unauthorized_cross_domain_reused_hashes": unauthorized_hashes,
            "dynamic_suffix_reuse_blocks": dynamic_suffix_reuse_blocks,
            "actual_verifier_endpoint_calls": verifier_calls,
            "transaction_commits": sum(truth(row.get("certificate_issued")) for row in registration_rows),
            "verification_fanout": len(rows) / max(1, verifier_calls),
            "committed_certificate_fanout": len(rows) / max(1, sum(truth(row.get("certificate_issued")) for row in registration_rows)),
            "claim_boundary": "Real vLLM open-loop future requests. Registration is real and its unhidden cost is amortized; marker sanity is not official task scoring.",
        })
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--arrivals", type=Path, required=True)
    parser.add_argument("--family-policy", type=Path, required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--policy-label", default="")
    parser.add_argument("--arrival-rate-rps", type=float, required=True)
    parser.add_argument("--arrival-mode", choices=("poisson", "onoff"), default="poisson")
    parser.add_argument("--on-seconds", type=float, default=5.0)
    parser.add_argument("--off-seconds", type=float, default=5.0)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--registration-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--registration-max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--drain-seconds", type=float, default=300.0)
    parser.add_argument("--registration-concurrency", type=int, default=2)
    parser.add_argument("--tool-slack-ms", type=float, default=6000.0)
    parser.add_argument("--slo-buckets-ms", default="500,750,1000,1500,3000")
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--policy-hash", default="tsc-service-frozen-v0")
    parser.add_argument("--qualification-hash", default="tsc-service-family-policy-v0")
    parser.add_argument("--certificate-scope-mode", choices=("qualified_session", "service_template"),
                        default="qualified_session")
    parser.add_argument("--load-tier", default="tsc-open-loop")
    args = parser.parse_args()
    args.slo_buckets_ms = [float(value) for value in args.slo_buckets_ms.split(",")]
    args.eligible_families = eligible_families(args.family_policy, args.model_identity)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    args.chat_template_hash = digest(str(getattr(tokenizer, "chat_template", "")))
    sessions = load_jsonl(args.sessions)
    arrivals = load_jsonl(args.arrivals)
    sessions_by_id = {str(row["tsc_session_id"]): row for row in sessions}
    prepared = {sid: compile_session(sample, args.turns, tokenizer, args.max_model_len, args.stable_word_limit)
                for sid, sample in sessions_by_id.items()}
    registration_offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    registration_rows, registration_index = register(args, sessions, prepared, args.eligible_families)
    measurement_offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else registration_offset
    rows = asyncio.run(replay(args, arrivals, sessions_by_id, prepared, registration_index))
    time.sleep(1.0)
    join_metrics(rows, load_metric_events(args.metrics_events, measurement_offset))
    summaries = summarize(args, rows, registration_rows)
    write_jsonl(args.raw_output, sorted(rows, key=lambda row: int(row.get("sequence", 10**9))))
    write_jsonl(args.registration_output, registration_rows)
    write_jsonl(args.summary_output, summaries)
    result = {
        "cell_id": args.cell_id, "offered": len(rows), "completed": sum(truth(row.get("success")) for row in rows),
        "registration_failures": sum(row.get("error_type") != "none" for row in registration_rows),
        "metric_join_rate": summaries[0]["metric_join_rate"] if summaries else 0,
    }
    print(json.dumps(result, indent=2))
    expected = args.max_requests or len(arrivals)
    # Overload cells are expected to expose timeouts or drops. They remain
    # valid measurements as long as every offered arrival has a terminal row.
    return 0 if len(rows) == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
