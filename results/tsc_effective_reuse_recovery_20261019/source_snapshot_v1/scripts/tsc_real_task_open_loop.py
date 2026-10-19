#!/usr/bin/env python3
"""Real-task open-loop D0/D1/D2 service cell with in-engine verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream, send_chat_stream_async
from scripts.phase20a_official_quality import standard_score
from scripts.contractkv_certificate_binding import (
    CertificateBinding, RequestBinding, sign as sign_binding,
    validation_errors as binding_validation_errors,
)
from scripts.tsc_service_template_quality_live import (
    compile_turns, digest, family_budget, load_jsonl, metric_events, number,
    scope_record, truth, verify_template,
)


POLICIES = ("D0-native-apc", "D1-frozen-safe", "D2-template-contractkv")


def issue_binding(args: argparse.Namespace, sample: dict[str, Any], scope: dict[str, Any],
                  protocol: dict[str, Any], secret: bytes) -> tuple[dict[str, Any], str]:
    binding = CertificateBinding(
        schema_version="contractkv.binding.v1", certificate_id=f"{args.cell_id}:{sample['service_template_id']}",
        model_id=args.model_identity, model_revision=args.model_revision,
        tokenizer_hash=digest(str(args.tokenizer)), chat_template_hash=args.chat_template_hash,
        serving_runtime="vllm", runtime_revision=args.runtime_revision,
        generation_config_hash=digest(protocol["generation_budgets"]),
        qualification_manifest_hash=args.qualification_hash, policy_hash=args.policy_hash,
        tenant_id="*", authorization_domain=str(scope["authorization_domain"]),
        service_template_id=str(sample["service_template_id"]),
        service_template_epoch=int(scope["service_epoch"]),
        stable_prefix_hash=str(scope["stable_content_hash"]), layout_hash=str(scope["layout_hash"]),
        expires_at_epoch=int(scope["service_epoch"]) + 100,
    )
    return asdict(binding), sign_binding(binding, secret)


def check_binding(args: argparse.Namespace, sample: dict[str, Any], scope: dict[str, Any],
                  protocol: dict[str, Any], certificate: dict[str, Any], secret: bytes) -> list[str]:
    if not certificate.get("signed_binding"):
        return ["signed_binding_missing"]
    binding = CertificateBinding(**certificate["signed_binding"])
    request = RequestBinding(
        model_id=args.model_identity, model_revision=args.model_revision,
        tokenizer_hash=digest(str(args.tokenizer)), chat_template_hash=args.chat_template_hash,
        serving_runtime="vllm", runtime_revision=args.runtime_revision,
        generation_config_hash=digest(protocol["generation_budgets"]),
        qualification_manifest_hash=args.qualification_hash, policy_hash=args.policy_hash,
        tenant_id="*", authorization_domain=str(scope["authorization_domain"]),
        service_template_id=str(sample["service_template_id"]),
        service_template_epoch=int(scope["service_epoch"]),
        stable_prefix_hash=str(scope["stable_content_hash"]), layout_hash=str(scope["layout_hash"]),
        current_epoch=int(scope["service_epoch"]), private_suffix_excluded=bool(scope["private_suffix_excluded"]),
    )
    return binding_validation_errors(binding, request, str(certificate.get("binding_signature", "")), secret)


def arrivals(sessions: list[dict[str, Any]], turns: int, rate: float, seed: int) -> list[dict[str, Any]]:
    jobs = [(str(sample["tsc_session_id"]), turn) for sample in sessions for turn in range(1, turns)]
    rng = random.Random(seed); rng.shuffle(jobs)
    elapsed = 0.0; result = []
    for sequence, (sid, turn) in enumerate(jobs):
        elapsed += rng.expovariate(rate)
        result.append({"sequence": sequence, "session_id": sid, "turn_id": turn, "arrival_s": elapsed})
    return result


async def replay(args: argparse.Namespace, sessions: list[dict[str, Any]], prepared: dict[str, Any],
                 certificates: dict[str, dict[str, Any]], protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    import aiohttp
    by_sid = {str(sample["tsc_session_id"]): sample for sample in sessions}
    trace = arrivals(sessions, args.turns, args.arrival_rate_rps, args.seed)
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    connector = aiohttp.TCPConnector(limit=0)
    secret = args.certificate_secret.encode("utf-8")
    started = time.perf_counter() + 1.0

    async def request_one(session: Any, item: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(max(0.0, started + item["arrival_s"] - time.perf_counter()))
        actual = time.perf_counter()
        sid, turn = item["session_id"], item["turn_id"]
        sample = by_sid[sid]; template_id = str(sample["service_template_id"])
        cert = certificates[template_id]; turn_data = prepared[sid][turn]
        current_scope = scope_record(args, sample, turn_data)
        scope_match = not truth(cert.get("certificate_issued")) or digest(current_scope) == str(cert.get("scope_digest", ""))
        binding_errors = (check_binding(args, sample, current_scope, protocol, cert, secret)
                          if args.policy == "D2-template-contractkv" and truth(cert.get("certificate_issued")) else [])
        if args.policy == "D1-frozen-safe":
            compiled = truth(protocol["template_qualification"].get(str(sample["tsc_family"]), False))
        else:
            compiled = (args.policy == "D2-template-contractkv" and truth(cert.get("certificate_issued"))
                        and scope_match and not binding_errors)
        message_value = turn_data["compiled_messages"] if compiled else turn_data["raw_messages"]
        rid = f"{args.cell_id}-{sid}-t{turn}"
        salt = f"{args.policy_hash}:{template_id}" if compiled else None
        result = await send_chat_stream_async(
            session, args.base_url, args.model, message_value,
            family_budget(protocol, str(sample["tsc_family"])), rid, cache_salt=salt)
        completed = time.perf_counter()
        score, metric, source = (0.0, "unavailable", "generation incomplete")
        if truth(result.get("success")):
            score, metric, source = standard_score(
                str(sample["dataset"]), str(sample["task"]),
                str(result.get("output_text", "")), sample.get("answer", ""))
        result.update({
            "cell_id": args.cell_id, "repeat": args.repeat, "policy": args.policy,
            "sequence": item["sequence"], "session_id": sid, "turn_id": turn,
            "service_template_id": template_id, "tenant_id": sample["tenant_id"],
            "family": sample["tsc_family"], "dataset": sample["dataset"], "task": sample["task"],
            "sample_id": sample["sample_id"], "effective_policy": "compiled" if compiled else "raw-fallback",
            "scope_check_pass": scope_match, "scope_invalid_admission": compiled and not scope_match,
            "certificate_binding_valid": not binding_errors,
            "certificate_binding_errors": binding_errors,
            "authorization_domain": sample.get("metadata", {}).get("authorization_domain", template_id),
            "allowed_prefix_tokens": turn_data["allowed_prefix_tokens"],
            "arrival_offset_ms": item["arrival_s"] * 1000.0,
            "client_send_lag_ms": max(0.0, (actual - started - item["arrival_s"]) * 1000.0),
            "completion_offset_ms": (completed - started) * 1000.0,
            "task_score": score, "task_metric": metric, "metric_source": source,
        })
        return result

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [asyncio.create_task(request_one(session, item)) for item in trace]
        done = await asyncio.gather(*tasks)
    wall = max((number(row.get("completion_offset_ms")) for row in done), default=0.0) / 1000.0
    return done, wall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True); parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tokenizer", required=True); parser.add_argument("--model-identity", required=True)
    parser.add_argument("--policy", choices=POLICIES, required=True); parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True); parser.add_argument("--cell-id", required=True)
    parser.add_argument("--arrival-rate-rps", type=float, default=1.6); parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--turns", type=int, default=10); parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=900); parser.add_argument("--policy-hash", default="tsc-real-task-v1")
    parser.add_argument("--qualification-hash", default="tsc-service-family-policy-v0")
    parser.add_argument("--model-revision", default="local-frozen")
    parser.add_argument("--runtime-revision", default="vllm-0.10.2-contractkv-phase19c")
    parser.add_argument("--certificate-secret", default="contractkv-tsc-closure-v1")
    parser.add_argument("--slo-buckets-ms", default="500,1000,1500,3000")
    parser.add_argument("--metrics-events", type=Path, required=True); parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--registration-output", type=Path, required=True); parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args(); args.slo_buckets_ms = [float(value) for value in args.slo_buckets_ms.split(",")]
    protocol = json.loads(args.protocol.read_text(encoding="utf-8")); sessions = load_jsonl(args.sessions)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    args.chat_template_hash = digest(str(getattr(tokenizer, "chat_template", "")))
    prepared = {str(sample["tsc_session_id"]): compile_turns(
        sample, args.turns, args.stable_word_limit, args.base_url, args.model, args.timeout) for sample in sessions}
    by_template: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in sessions: by_template[str(sample["service_template_id"])].append(sample)
    metric_offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    service_start = time.perf_counter(); registrations = []; certificates = {}
    for template_id, members in sorted(by_template.items()):
        sample = members[0]; family = str(sample["tsc_family"]); qualified = truth(protocol["template_qualification"].get(family, False))
        begin = time.perf_counter()
        if args.policy == "D2-template-contractkv" and qualified:
            try:
                result = verify_template(args, sample, prepared[str(sample["tsc_session_id"])][0], family_budget(protocol, family))
                row = {"service_template_id": template_id, "family": family, "certificate_issued": truth(result.get("certificate_issued")),
                       "verify_decision": result.get("verify_decision", ""), "txn_state": result.get("txn_state", ""),
                       "verification_ms": result.get("verification_ms", 0), "scope_digest": result.get("scope_digest", ""),
                       "transport": "same_vllm_engine_contractkv_verify_endpoint", "error_type": "none", "error_message": ""}
            except Exception as exc:
                row = {"service_template_id": template_id, "family": family, "certificate_issued": False,
                       "verify_decision": "INCOMPLETE", "txn_state": "ABORTED", "verification_ms": 0,
                       "scope_digest": "", "transport": "same_vllm_engine_contractkv_verify_endpoint",
                       "error_type": type(exc).__name__, "error_message": str(exc)}
        elif args.policy == "D1-frozen-safe" and qualified:
            row = {"service_template_id": template_id, "family": family, "certificate_issued": True,
                   "verify_decision": "FROZEN_SAFE_NO_ONLINE_VERIFY", "txn_state": "NOT_RUN", "verification_ms": 0,
                   "scope_digest": digest(scope_record(args, sample, prepared[str(sample["tsc_session_id"])][0])),
                   "transport": "none", "error_type": "none", "error_message": ""}
        else:
            row = {"service_template_id": template_id, "family": family, "certificate_issued": False,
                   "verify_decision": "RAW_FALLBACK", "txn_state": "NOT_RUN", "verification_ms": 0,
                   "scope_digest": "", "transport": "none", "error_type": "none", "error_message": ""}
        row["registration_ms"] = (time.perf_counter() - begin) * 1000.0; registrations.append(row); certificates[template_id] = row
        if args.policy == "D2-template-contractkv" and truth(row["certificate_issued"]):
            binding, signature = issue_binding(args, sample, scope_record(args, sample, prepared[str(sample["tsc_session_id"])][0]), protocol,
                                               args.certificate_secret.encode("utf-8"))
            row["signed_binding"] = binding; row["binding_signature"] = signature
        warm = prepared[str(sample["tsc_session_id"])][0]
        compiled = args.policy == "D1-frozen-safe" and qualified or args.policy == "D2-template-contractkv" and truth(row["certificate_issued"])
        send_chat_stream(args.base_url, args.model, warm["compiled_messages"] if compiled else warm["raw_messages"],
                         family_budget(protocol, family), args.timeout, f"{args.cell_id}-warm-{template_id}",
                         cache_salt=f"{args.policy_hash}:{template_id}" if compiled else None)
    registration_wall_s = time.perf_counter() - service_start
    rows, replay_wall_s = asyncio.run(replay(args, sessions, prepared, certificates, protocol))
    time.sleep(1); metrics = metric_events(args.metrics_events, metric_offset)
    for row in rows:
        event = metrics.get(str(row.get("request_id", "")), {}); row["metric_join_success"] = bool(event)
        for key in ("prompt_tokens", "prefix_hit_tokens", "used_gpu_blocks", "free_gpu_blocks", "physical_block_count", "reused_physical_blocks", "block_size"):
            row[key] = event.get(key, "")
        row["new_prefill_tokens"] = max(0, int(event.get("prompt_tokens", 0)) - int(event.get("prefix_hit_tokens", 0))) if event else ""
    success = [row for row in rows if truth(row.get("success"))]; e2e_wall_s = registration_wall_s + replay_wall_s
    summaries = []
    for slo in args.slo_buckets_ms:
        compliant = [row for row in success if number(row.get("ttft_ms")) <= slo]
        summaries.append({
            "schema_version": "contractkv.tsc.real-task-open-loop.v1", "cell_id": args.cell_id,
            "repeat": args.repeat, "policy": args.policy, "arrival_rate_rps": args.arrival_rate_rps, "slo_ttft_ms": slo,
            "offered_requests": len(rows), "completed_requests": len(success), "completion_rate": len(success)/max(1,len(rows)),
            "drop_rate": 1-len(success)/max(1,len(rows)), "registration_wall_s": registration_wall_s,
            "replay_wall_s": replay_wall_s, "end_to_end_wall_s": e2e_wall_s,
            "mean_ttft_ms": statistics.fmean(number(row["ttft_ms"]) for row in success) if success else 0,
            "p95_ttft_ms": percentile([number(row["ttft_ms"]) for row in success], .95),
            "p99_ttft_ms": percentile([number(row["ttft_ms"]) for row in success], .99),
            "mean_tpot_ms": statistics.fmean(number(row["tpot_ms"]) for row in success) if success else 0,
            "mean_latency_ms": statistics.fmean(number(row["total_latency_ms"]) for row in success) if success else 0,
            "mean_task_score": statistics.fmean(number(row["task_score"]) for row in success) if success else 0,
            "slo_compliant_requests": len(compliant), "replay_slo_goodput_rps": len(compliant)/max(replay_wall_s,1e-9),
            "end_to_end_slo_goodput_rps": len(compliant)/max(e2e_wall_s,1e-9),
            "mean_prompt_tokens": statistics.fmean(number(row["prompt_tokens"]) for row in success) if success else 0,
            "mean_prefix_hit_tokens": statistics.fmean(number(row["prefix_hit_tokens"]) for row in success) if success else 0,
            "mean_new_prefill_tokens": statistics.fmean(number(row["new_prefill_tokens"]) for row in success) if success else 0,
            "metric_join_rate": sum(truth(row["metric_join_success"]) for row in success)/max(1,len(success)),
            "actual_verifier_endpoint_calls": sum(row["transport"].startswith("same_vllm") for row in registrations),
            "transaction_commits": sum(truth(row["certificate_issued"]) and row["txn_state"] == "COMMITTED" for row in registrations),
            "registration_failures": sum(row["error_type"] != "none" for row in registrations),
            "scope_invalid_admissions": sum(truth(row["scope_invalid_admission"]) for row in rows),
            "certificate_binding_failures": sum(not truth(row["certificate_binding_valid"]) for row in rows),
            "raw_fallback_rate": sum(row["effective_policy"] == "raw-fallback" for row in rows)/max(1,len(rows)),
            "claim_boundary": "Real task outputs under Poisson open-loop arrivals. D2 verification is an in-engine request and registration wall is charged to end-to-end goodput.",
        })
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in sorted(rows,key=lambda x:x["sequence"])),encoding="utf-8")
    args.registration_output.write_text("".join(json.dumps(row)+"\n" for row in registrations),encoding="utf-8")
    args.summary_output.write_text("".join(json.dumps(row)+"\n" for row in summaries),encoding="utf-8")
    print(json.dumps({"offered":len(rows),"completed":len(success),"policy":args.policy,"repeat":args.repeat,"e2e_wall_s":e2e_wall_s},indent=2))
    return 0 if len(success)==len(rows) and not any(row["scope_invalid_admission"] for row in rows) else 2


if __name__ == "__main__": raise SystemExit(main())
