#!/usr/bin/env python3
"""Run one fresh vLLM cell for the service-template task-quality audit."""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, compile_static_policy
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase17_live_common import api_root, digest, generate_raw, post_json, tokenize
from scripts.phase20a_official_quality import standard_score


DYNAMIC_TYPES = {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def family_budget(protocol: dict[str, Any], family: str) -> int:
    return int(protocol["generation_budgets"][family])


def turn_case(sample: dict[str, Any], turn: int, stable_word_limit: int) -> dict[str, Any]:
    case = build_case(sample, stable_word_limit=stable_word_limit)
    case["trajectory_id"] = str(sample["tsc_session_id"])
    case["turn_id"] = turn
    for segment in case["segments"]:
        if segment.get("segment_type") == "TOOL_OBS":
            segment["text"] = (
                f"[PRIVATE_TOOL_OBS] authorized tenant={sample['tenant_id']}; turn={turn}; "
                "no additional task evidence is provided."
            )
    return case


def compile_turns(sample: dict[str, Any], turns: int, stable_word_limit: int,
                  base_url: str, model: str, timeout: float) -> dict[int, dict[str, Any]]:
    ledger = SegmentPrefixLedger()
    sid = str(sample["tsc_session_id"])
    output = {}
    for turn in range(turns):
        case = turn_case(sample, turn, stable_word_limit)
        raw = compile_static_policy(case["segments"], "raw-order")
        compiled = cache_aware_posc_compile(case["segments"], ledger, sid, turn, 6000.0)
        raw_messages = quality_messages(case, _ordered_text(raw["topological_order"], case["segments"]))
        compiled_messages = quality_messages(case, _ordered_text(compiled["topological_order"], case["segments"]))
        output[turn] = {
            "case": case, "raw_layout": raw, "compiled_layout": compiled,
            "raw_messages": raw_messages, "compiled_messages": compiled_messages,
        }
        ledger.update(sid, turn, case["segments"], compiled["topological_order"], policy="contractkv-caposc")
    first = tokenize(base_url, model, output[0]["compiled_messages"], True, timeout)
    second = tokenize(base_url, model, output[1]["compiled_messages"], True, timeout)
    allowed = lcp_length(first, second)
    for row in output.values():
        row["allowed_prefix_tokens"] = allowed
    return output


def stable_prefix_order(case: dict[str, Any], order: list[str]) -> list[str]:
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    result = []
    for segment_id in order:
        if str(by_id[segment_id].get("segment_type")) in DYNAMIC_TYPES:
            break
        result.append(segment_id)
    return result


def scope_record(args: argparse.Namespace, sample: dict[str, Any], prepared: dict[str, Any]) -> dict[str, Any]:
    case, order = prepared["case"], [str(value) for value in prepared["compiled_layout"]["topological_order"]]
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    stable = stable_prefix_order(case, order)
    stable_content = [(value, str(by_id[value].get("text", ""))) for value in stable]
    return {
        "model_identity": args.model_identity,
        "tokenizer_identity": str(args.tokenizer),
        "service_template_version": str(sample["service_template_id"]),
        "stable_content_hash": digest(stable_content),
        "layout_hash": digest(order),
        "policy_hash": args.policy_hash,
        "qualification_hash": args.qualification_hash,
        "authorization_domain": str(sample.get("metadata", {}).get("authorization_domain", sample["service_template_id"])),
        "service_epoch": int(sample.get("metadata", {}).get("service_epoch", 1)),
        "private_suffix_excluded": True,
    }


def verify_template(args: argparse.Namespace, sample: dict[str, Any], prepared: dict[str, Any],
                    max_tokens: int) -> dict[str, Any]:
    order = [str(value) for value in prepared["compiled_layout"]["topological_order"]]
    case = prepared["case"]
    candidate_messages = prepared["compiled_messages"]
    prefix_order = stable_prefix_order(case, order)
    prefix_messages = quality_messages(case, _ordered_text(prefix_order, case["segments"]))
    raw = generate_raw(args.base_url, args.model,
                       f"{args.cell_id}-canary-{sample['service_template_id']}",
                       candidate_messages, args.timeout, max_tokens)
    prefix_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    stable_end = lcp_length(prefix_ids, candidate_ids)
    scope = scope_record(args, sample, prepared)
    payload = {
        "request_id": f"{args.cell_id}-verify-{sample['service_template_id']}",
        "prompt_token_ids": candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]],
        "txn_id": f"{args.cell_id}-txn-{sample['service_template_id']}",
        "policy_hash": args.policy_hash, "policy_version": "tsc-quality-v0",
        "attestation_mode": "prospective-qualified-template-exact-path-v1",
        "stable_prefix_end_token": stable_end, "verify_start_token": len(candidate_ids),
        "reference_answer_ids": raw["token_ids"], "reference_raw_margins": raw["margins"],
        "terminal_stop_token_id": raw["terminal_stop_token_id"],
        "stable_content_hash": digest(prefix_ids), "layout_hash": digest(candidate_ids),
        "dependency_graph_hash": digest([(segment["segment_id"], segment.get("dependencies", [])) for segment in case["segments"]]),
        "timeout_s": args.timeout, "cache_salt": f"{args.policy_hash}:{sample['service_template_id']}",
    }
    started = time.perf_counter()
    response = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
    return {**response, "verification_ms": (time.perf_counter() - started) * 1000.0,
            "stable_prefix_tokens": stable_end, "scope_record": scope,
            "scope_digest": digest(scope)}


def metric_events(path: Path, offset: int) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        handle.seek(offset)
        rows = [json.loads(line) for line in handle.read().decode("utf-8", errors="replace").splitlines() if line.strip()]
    return {str(row.get("request_id")): row for row in rows
            if row.get("event") == "prefix_cache_request_observation" and row.get("initial_prefill_observation")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--policy", choices=("D0-native-apc", "D2-template-contractkv"), required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--cell-id", required=True); parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--registration-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=10); parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--policy-hash", default="tsc-quality-qwen-v0")
    parser.add_argument("--qualification-hash", default="tsc-service-family-policy-v0")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    sessions = load_jsonl(args.sessions)
    by_template: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in sessions:
        by_template[str(sample["service_template_id"])].append(sample)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    prepared = {str(sample["tsc_session_id"]): compile_turns(
        sample, args.turns, args.stable_word_limit, args.base_url, args.model, args.timeout)
        for sample in sessions}
    metric_offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0

    registrations = []
    certificates: dict[str, dict[str, Any]] = {}
    for template_id, members in sorted(by_template.items()):
        representative = members[0]
        family = str(representative["tsc_family"])
        family_qualified = truth(protocol.get("template_qualification", {}).get(family, True))
        started = time.perf_counter()
        if args.policy == "D2-template-contractkv" and family_qualified:
            try:
                result = verify_template(args, representative, prepared[str(representative["tsc_session_id"])][0],
                                         family_budget(protocol, family))
                issued = truth(result.get("certificate_issued"))
                row = {"service_template_id": template_id, "family": family,
                       "certificate_issued": issued, "verify_decision": result.get("verify_decision", ""),
                       "txn_state": result.get("txn_state", ""), "verification_ms": result["verification_ms"],
                       "stable_prefix_tokens": result["stable_prefix_tokens"],
                       "scope_record": result["scope_record"], "scope_digest": result["scope_digest"],
                       "error_type": "none", "error_message": ""}
            except Exception as exc:
                row = {"service_template_id": template_id, "family": family,
                       "certificate_issued": False, "verify_decision": "INCOMPLETE", "txn_state": "ABORTED",
                       "verification_ms": 0.0, "stable_prefix_tokens": 0, "scope_record": {}, "scope_digest": "",
                       "error_type": type(exc).__name__, "error_message": str(exc)}
        elif args.policy == "D2-template-contractkv":
            row = {"service_template_id": template_id, "family": family,
                   "certificate_issued": False, "verify_decision": "FROZEN_RAW_FALLBACK", "txn_state": "NOT_RUN",
                   "verification_ms": 0.0, "stable_prefix_tokens": 0, "scope_record": {}, "scope_digest": "",
                   "error_type": "none", "error_message": "",
                   "fallback_reason": protocol.get("template_qualification_source", {}).get(
                       family, "service template is outside the frozen qualified scope")}
        else:
            row = {"service_template_id": template_id, "family": family,
                   "certificate_issued": False, "verify_decision": "RAW_REGISTRATION", "txn_state": "NOT_RUN",
                   "verification_ms": 0.0, "stable_prefix_tokens": 0, "scope_record": {}, "scope_digest": "",
                   "error_type": "none", "error_message": ""}
        row["registration_ms"] = (time.perf_counter() - started) * 1000.0
        row["authorized_tenants"] = len(members)
        registrations.append(row); certificates[template_id] = row

        warm = prepared[str(representative["tsc_session_id"])][0]
        messages = warm["compiled_messages"] if truth(row["certificate_issued"]) else warm["raw_messages"]
        send_chat_stream(args.base_url, args.model, messages, family_budget(protocol, family), args.timeout,
                         f"{args.cell_id}-warm-{template_id}",
                         cache_salt=(f"{args.policy_hash}:{template_id}" if truth(row["certificate_issued"]) else None))

    rows = []
    for turn in range(1, args.turns):
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {}
            for sample in sessions:
                sid, template_id = str(sample["tsc_session_id"]), str(sample["service_template_id"])
                cert = certificates[template_id]; turn_data = prepared[sid][turn]
                current_scope = scope_record(args, sample, turn_data)
                scope_match = (not truth(cert["certificate_issued"])
                               or digest(current_scope) == str(cert.get("scope_digest", "")))
                compiled = args.policy == "D2-template-contractkv" and truth(cert["certificate_issued"]) and scope_match
                messages = turn_data["compiled_messages"] if compiled else turn_data["raw_messages"]
                rid = f"{args.cell_id}-{sid}-t{turn}"
                future = pool.submit(send_chat_stream, args.base_url, args.model, messages,
                                     family_budget(protocol, str(sample["tsc_family"])), args.timeout, rid,
                                     cache_salt=(f"{args.policy_hash}:{template_id}" if compiled else None))
                futures[future] = (sample, turn_data, turn, rid, scope_match, compiled)
            for future in as_completed(futures):
                sample, turn_data, turn, rid, scope_match, compiled = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"success": False, "error_type": type(exc).__name__, "error_message": str(exc)}
                score = 0.0; metric = "unavailable"; source = "generation incomplete"
                if truth(result.get("success")):
                    score, metric, source = standard_score(
                        str(sample["dataset"]), str(sample["task"]),
                        str(result.get("output_text", "")), sample.get("answer", ""))
                rows.append({
                    "cell_id": args.cell_id, "repeat": args.repeat, "policy": args.policy,
                    "service_template_id": sample["service_template_id"], "tenant_id": sample["tenant_id"],
                    "session_id": sample["tsc_session_id"], "family": sample["tsc_family"],
                    "dataset": sample["dataset"], "task": sample["task"], "sample_id": sample["sample_id"],
                    "turn_id": turn, "request_id": result.get("request_id") or rid,
                    "success": truth(result.get("success")), "effective_policy": "compiled" if compiled else "raw-fallback",
                    "scope_check_pass": scope_match, "scope_invalid_admission": compiled and not scope_match,
                    "authorization_domain": sample.get("metadata", {}).get("authorization_domain", sample["service_template_id"]),
                    "allowed_prefix_tokens": turn_data["allowed_prefix_tokens"],
                    "task_score": score, "metric": metric, "metric_source": source,
                    "output_text": result.get("output_text", ""), "output_tokens": result.get("output_tokens", 0),
                    "finish_reason": result.get("finish_reason", ""), "ttft_ms": result.get("ttft_ms", 0),
                    "tpot_ms": result.get("tpot_ms", 0), "latency_ms": result.get("total_latency_ms", 0),
                    "error_type": result.get("error_type", "none"), "error_message": result.get("error_message", ""),
                })

    time.sleep(1.0)
    metrics = metric_events(args.metrics_events, metric_offset)
    hash_domains: dict[str, set[str]] = defaultdict(set)
    dynamic_suffix = 0
    for row in rows:
        event = metrics.get(str(row["request_id"]), {})
        row["metric_join_success"] = bool(event)
        for key in ("prompt_tokens", "prefix_hit_tokens", "used_gpu_blocks", "free_gpu_blocks",
                    "physical_block_count", "reused_physical_blocks", "block_size"):
            row[key] = event.get(key, "")
        row["new_prefill_tokens"] = (max(0, int(event.get("prompt_tokens", 0)) - int(event.get("prefix_hit_tokens", 0)))
                                      if event else "")
        reused = int(number(event.get("reused_physical_blocks")))
        for value in event.get("physical_block_hashes", [])[:reused]:
            if value:
                hash_domains[str(value)].add(str(row["authorization_domain"]))
        block_size = max(1, int(number(event.get("block_size"))))
        dynamic_suffix += max(0, int(number(event.get("prefix_hit_tokens")))
                              - int(number(row["allowed_prefix_tokens"])) - block_size) // block_size
    success = [row for row in rows if truth(row["success"])]
    summary = {
        "cell_id": args.cell_id, "repeat": args.repeat, "policy": args.policy,
        "offered_requests": len(rows), "completed_requests": len(success),
        "completion_rate": len(success) / max(1, len(rows)),
        "mean_task_score": statistics.mean(number(row["task_score"]) for row in success) if success else 0.0,
        "scope_invalid_admissions": sum(truth(row["scope_invalid_admission"]) for row in rows),
        "unauthorized_cross_template_reused_hashes": sum(len(domains) > 1 for domains in hash_domains.values()),
        "dynamic_suffix_reuse_blocks": dynamic_suffix,
        "metric_join_rate": sum(truth(row["metric_join_success"]) for row in success) / max(1, len(success)),
        "actual_verifier_endpoint_calls": sum(row["verify_decision"] not in {
            "RAW_REGISTRATION", "FROZEN_RAW_FALLBACK", "NOT_RUN"} for row in registrations),
        "transaction_commits": sum(truth(row["certificate_issued"]) for row in registrations),
        "raw_fallback_rate": sum(row["effective_policy"] == "raw-fallback" for row in rows) / max(1, len(rows)),
        "claim_boundary": "Real task outputs and frozen task metrics for five deployed service templates; not full benchmark scoring.",
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in sorted(rows, key=lambda item: (item["family"], item["session_id"], item["turn_id"]))), encoding="utf-8")
    args.registration_output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in registrations), encoding="utf-8")
    args.summary_output.write_text(json.dumps(summary, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["completion_rate"] == 1.0 and summary["scope_invalid_admissions"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
