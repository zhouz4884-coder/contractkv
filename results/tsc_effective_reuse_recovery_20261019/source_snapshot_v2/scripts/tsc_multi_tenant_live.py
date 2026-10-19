#!/usr/bin/env python3
"""Measure real multi-tenant sharing, isolation, fairness, and consolidation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream, send_chat_stream_async
from scripts.phase14m_physical_dedup import fit_shared_text
from scripts.contractkv_pstp import lcp_length
from scripts.phase17_live_common import api_root, digest, generate_raw, post_json, tokenize


CLASSES = {
    "Gold": {"slo_ms": 750.0, "weight": 3.0},
    "Silver": {"slo_ms": 1500.0, "weight": 2.0},
    "Bronze": {"slo_ms": 3000.0, "weight": 1.0},
}


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def scope_token(scope_id: str) -> str:
    return hashlib.sha256(scope_id.encode()).hexdigest()[:24]


def tenant_specs(tenants: int, sharing_ratio: float) -> list[dict[str, Any]]:
    shared = round(tenants * sharing_ratio)
    specs = []
    classes = list(CLASSES)
    for index in range(tenants):
        allowed_shared = index < shared
        scope_id = "approved-service-template-v1" if allowed_shared else f"private-service-{index:03d}"
        specs.append({
            "tenant_id": f"tenant-{index:03d}", "scope_id": scope_id,
            "allowed_shared": allowed_shared, "service_class": classes[index % len(classes)],
            "policy_hash": "approved-policy-v1" if allowed_shared else f"private-policy-{index:03d}",
        })
    return specs


def messages(policy: str, tenant: dict[str, Any], stable: str, turn: int) -> tuple[list[dict[str, str]], str]:
    marker = f"T{turn:02d}{hashlib.sha256(str(tenant['tenant_id']).encode()).hexdigest()[:4]}"
    scope = f"[CERTIFIED_SCOPE:{scope_token(tenant['scope_id'] + ':' + tenant['policy_hash'])}]"
    observation = f"[PRIVATE_OBS] tenant={tenant['tenant_id']}; turn={turn}; marker={marker}."
    context = f"[STABLE_SERVICE_CONTEXT]\n{stable}"
    query = "Return exactly the marker from PRIVATE_OBS. /no_think"
    if policy == "raw-order":
        body = f"{scope}\n{observation}\n\n{context}\n\n{query}"
    else:
        body = f"{scope}\n{context}\n\n{observation}\n\n{query}"
    return [{"role": "system", "content": f"{scope} Follow the authorized tenant request exactly."},
            {"role": "user", "content": body}], marker


async def one_request(sem: asyncio.Semaphore, session: Any, args: argparse.Namespace,
                      tenant: dict[str, Any], stable: str, turn: int) -> dict[str, Any]:
    scope_started = time.perf_counter()
    scope_check_pass = (str(tenant["scope_id"]) == str(tenant.get("registered_scope_id", "")))
    scope_check_ms = (time.perf_counter() - scope_started) * 1000.0
    effective_policy = tenant["effective_policy"] if scope_check_pass else "raw-order"
    request_messages, marker = messages(effective_policy, tenant, stable, turn)
    rid = f"{args.cell_id}-{tenant['tenant_id']}-t{turn}"
    async with sem:
        result = await send_chat_stream_async(session, args.base_url, args.model,
                                              request_messages, args.max_tokens, rid,
                                              cache_salt=f"{args.policy_hash}:{tenant['scope_id']}")
    result.update({
        "cell_id": args.cell_id, "policy": args.policy, "effective_policy": effective_policy,
        "tenant_id": tenant["tenant_id"],
        "scope_id": tenant["scope_id"], "allowed_shared": tenant["allowed_shared"],
        "service_class": tenant["service_class"], "slo_ms": CLASSES[tenant["service_class"]]["slo_ms"],
        "turn_id": turn, "allowed_prefix_tokens": tenant["allowed_prefix_tokens"],
        "scope_check_pass": scope_check_pass, "scope_check_ms": scope_check_ms,
        "quality_sanity": marker in str(result.get("output_text", "")),
    })
    return result


async def replay(args: argparse.Namespace, tenants: list[dict[str, Any]], stable: str) -> list[dict[str, Any]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    connector = aiohttp.TCPConnector(limit=0)
    rows: list[dict[str, Any]] = []
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        sem = asyncio.Semaphore(args.concurrency)
        for turn in range(1, args.turns):
            started = time.perf_counter()
            offset = turn % max(1, len(tenants))
            ordered_tenants = tenants[offset:] + tenants[:offset]
            tasks = [asyncio.create_task(one_request(sem, session, args, tenant, stable, turn))
                     for tenant in ordered_tenants]
            wave = await asyncio.gather(*tasks, return_exceptions=True)
            wall_ms = (time.perf_counter() - started) * 1000.0
            for tenant, result in zip(ordered_tenants, wave):
                if isinstance(result, Exception):
                    result = {"cell_id": args.cell_id, "policy": args.policy,
                              "tenant_id": tenant["tenant_id"], "scope_id": tenant["scope_id"],
                              "allowed_shared": tenant["allowed_shared"], "service_class": tenant["service_class"],
                              "slo_ms": CLASSES[tenant["service_class"]]["slo_ms"], "turn_id": turn,
                              "success": False, "quality_sanity": False,
                              "error_type": type(result).__name__, "error_message": str(result)}
                result["wave_wall_ms"] = wall_ms
                rows.append(result)
    return rows


def initial_metrics(path: Path, offset: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return {}, {"allowed_refcount_match_rate": 0.0, "concurrent_shared_blocks": 0}
    with path.open("rb") as handle:
        handle.seek(offset)
        events = [json.loads(line) for line in handle.read().decode("utf-8", errors="replace").splitlines() if line.strip()]
    initial = {str(event.get("request_id")): event for event in events
               if event.get("event") == "prefix_cache_request_observation" and event.get("initial_prefill_observation")}
    pairs = []
    for event in events:
        if event.get("event") != "prefix_cache_concurrent_snapshot":
            continue
        pairs.extend(zip(event.get("shared_block_request_counts", []), event.get("shared_block_refcounts", [])))
    return initial, {
        "allowed_refcount_match_rate": sum(int(refcount) >= int(count) for count, refcount in pairs) / len(pairs) if pairs else 1.0,
        "concurrent_shared_blocks": len(pairs),
    }


def join(rows: list[dict[str, Any]], metrics: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        event = metrics.get(str(row.get("request_id", "")), {})
        row.update({
            "metric_join_success": bool(event), "prompt_tokens": event.get("prompt_tokens", ""),
            "prefix_hit_tokens": event.get("prefix_hit_tokens", ""),
            "reused_physical_blocks": event.get("reused_physical_blocks", ""),
            "physical_block_ids": event.get("physical_block_ids", []),
            "physical_block_hashes": event.get("physical_block_hashes", []),
            "physical_block_refcounts": event.get("physical_block_refcounts", []),
            "newly_allocated_blocks": event.get("newly_allocated_blocks", ""),
            "block_size": event.get("block_size", ""), "used_gpu_blocks": event.get("used_gpu_blocks", ""),
            "free_gpu_blocks": event.get("free_gpu_blocks", ""),
            "scheduler_waiting_requests": event.get("scheduler_waiting_requests", ""),
        })


def jain(values: list[float]) -> float:
    return sum(values) ** 2 / (len(values) * sum(value * value for value in values)) if values and any(values) else 0.0


def isolation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if truth(row.get("success")) and truth(row.get("metric_join_success"))]
    unauthorized_pairs = set()
    allowed_shared_hashes: dict[tuple[int, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    dynamic_suffix_reuse = 0
    for row in successful:
        reused = int(number(row.get("reused_physical_blocks")))
        hashes = [str(value) for value in row.get("physical_block_hashes", [])[:reused] if value]
        key = (int(row["turn_id"]), str(row["scope_id"]))
        for value in hashes:
            allowed_shared_hashes[key][value].add(str(row["tenant_id"]))
    by_turn_hash: dict[tuple[int, str], set[str]] = defaultdict(set)
    for row in successful:
        reused = int(number(row.get("reused_physical_blocks")))
        for value in row.get("physical_block_hashes", [])[:reused]:
            if value:
                by_turn_hash[(int(row["turn_id"]), str(value))].add(str(row["scope_id"]))
    for key, scopes in by_turn_hash.items():
        if len(scopes) > 1:
            unauthorized_pairs.add((key[0], key[1], tuple(sorted(scopes))))
    # A changed private observation follows the certified stable region. Any
    # cross-tenant hash equality beyond the scope-qualified prefix is caught
    # above; per-request suffix hit is conservatively checked at block level.
    for row in successful:
        hit_tokens = int(number(row.get("prefix_hit_tokens")))
        allowed_tokens = int(number(row.get("allowed_prefix_tokens")))
        block_size = max(1, int(number(row.get("block_size"))))
        if hit_tokens > allowed_tokens + block_size:
            dynamic_suffix_reuse += (hit_tokens - allowed_tokens) // block_size
    shared_instances = [len(tenants) for (_, _), tenants_by_hash in allowed_shared_hashes.items()
                        for tenants in tenants_by_hash.values() if len(tenants) > 1]
    return {
        "unauthorized_cross_tenant_reuse": len(unauthorized_pairs),
        "dynamic_suffix_reuse_blocks": dynamic_suffix_reuse,
        "allowed_shared_hash_instances": len(shared_instances),
        "max_allowed_shared_tenant_refcount": max(shared_instances, default=1),
    }


def summarize(args: argparse.Namespace, rows: list[dict[str, Any]], tenants: list[dict[str, Any]],
              snapshot_stats: dict[str, Any]) -> list[dict[str, Any]]:
    success = [row for row in rows if truth(row.get("success"))]
    iso = isolation(rows)
    per_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in success:
        per_tenant[str(row["tenant_id"])].append(row)
    tenant_rates = []
    for tenant in tenants:
        group = per_tenant.get(tenant["tenant_id"], [])
        compliant = sum(number(row.get("ttft_ms")) <= CLASSES[tenant["service_class"]]["slo_ms"]
                        and truth(row.get("quality_sanity")) for row in group)
        tenant_rates.append(compliant / max(1, args.turns - 1))
    wave_walls = {}
    for row in rows:
        wave_walls[int(row.get("turn_id", 0))] = number(row.get("wave_wall_ms"))
    wall_s = max(sum(wave_walls.values()) / 1000.0, 1e-9)
    expected_all = args.tenants * (args.turns - 1)
    total_registration_ms = getattr(args, "total_registration_ms", 0.0)
    registration_per_request_ms = total_registration_ms / max(1, expected_all)
    cold_start_wall_s = wall_s + total_registration_ms / 1000.0
    output = []
    for class_name in ["ALL", *CLASSES]:
        group = success if class_name == "ALL" else [row for row in success if row["service_class"] == class_name]
        ttft = [number(row.get("ttft_ms")) for row in group]
        slo_compliant = [row for row in group if number(row.get("ttft_ms")) <= number(row.get("slo_ms"))
                         and truth(row.get("quality_sanity"))]
        cold_start_compliant = [
            row for row in group
            if number(row.get("ttft_ms")) + registration_per_request_ms <= number(row.get("slo_ms"))
            and truth(row.get("quality_sanity"))
        ]
        expected = args.tenants * (args.turns - 1) if class_name == "ALL" else sum(
            tenant["service_class"] == class_name for tenant in tenants) * (args.turns - 1)
        output.append({
            "experiment_version": "tsc-service-v1",
            "cell_id": args.cell_id, "policy": args.policy, "tenants": args.tenants,
            "sharing_ratio": args.sharing_ratio, "service_class": class_name,
            "requests": len(group), "completion_rate": len(group) / max(1, expected),
            "quality_sanity_rate": sum(truth(row.get("quality_sanity")) for row in group) / max(1, len(group)),
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
            "p95_ttft_ms": percentile(ttft, .95), "p99_ttft_ms": percentile(ttft, .99),
            "slo_compliant_goodput_rps": len(slo_compliant) / wall_s,
            "cold_start_amortized_slo_goodput_rps": len(cold_start_compliant) / cold_start_wall_s,
            "registration_amortized_ms_per_request": registration_per_request_ms,
            "total_registration_ms": total_registration_ms,
            "weighted_slo_goodput": sum(CLASSES[row["service_class"]]["weight"] for row in slo_compliant) / wall_s,
            "jain_tenant_slo_fairness": jain(tenant_rates),
            "metric_join_rate": sum(truth(row.get("metric_join_success")) for row in group) / max(1, len(group)),
            "peak_used_gpu_blocks": max((int(number(row.get("used_gpu_blocks"))) for row in group), default=0),
            "minimum_free_gpu_blocks": min((int(number(row.get("free_gpu_blocks"))) for row in group), default=0),
            "mean_newly_allocated_blocks": statistics.mean(number(row.get("newly_allocated_blocks")) for row in group) if group else 0.0,
            "max_scheduler_waiting_requests": max((int(number(row.get("scheduler_waiting_requests"))) for row in group), default=0),
            "certificate_issue_rate": getattr(args, "certificate_issue_rate", 0.0),
            "mean_verification_ms": getattr(args, "mean_verification_ms", 0.0),
            "mean_registration_ms": getattr(args, "mean_registration_ms", 0.0),
            "raw_fallback_rate": sum(row.get("effective_policy") == "raw-order" for row in group) / max(1, len(group)),
            **snapshot_stats,
            **iso,
            "scope_invalid_admissions": sum(
                not truth(row.get("scope_check_pass")) and row.get("effective_policy") != "raw-order"
                for row in group),
            "scope_check_pass_rate": sum(truth(row.get("scope_check_pass")) for row in group) / max(1, len(group)),
            "mean_scope_check_ms": statistics.mean(number(row.get("scope_check_ms")) for row in group) if group else 0.0,
            "actual_verifier_endpoint_calls": getattr(args, "actual_verifier_endpoint_calls", 0),
            "transaction_commits": getattr(args, "transaction_commits", 0),
            "verification_fanout": expected_all / max(1, getattr(args, "actual_verifier_endpoint_calls", 0)),
            "claim_boundary": "Real vLLM tenant-scoped token prefixes and physical block hashes. Scope salts enforce forbidden sharing; this is not a priority scheduler.",
        })
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def register_scopes(args: argparse.Namespace, tenants: list[dict[str, Any]], stable: str) -> list[dict[str, Any]]:
    """Register each distinct authorization scope once; failures fall back raw."""
    representatives: dict[str, dict[str, Any]] = {}
    for tenant in tenants:
        representatives.setdefault(str(tenant["scope_id"]), tenant)
    rows = []
    certificates: dict[str, bool] = {}
    for scope_id, tenant in representatives.items():
        started = time.perf_counter()
        body: dict[str, Any] = {}
        issued = args.policy != "D2-full-contractkv"
        decision = "NOT_REQUIRED" if args.policy != "D2-full-contractkv" else "INCOMPLETE"
        verification_ms = 0.0
        error_type, error_message = "none", ""
        try:
            if args.policy == "D2-full-contractkv":
                candidate_messages, _ = messages("frozen-safe-scoped", tenant, stable, 0)
                next_messages, _ = messages("frozen-safe-scoped", tenant, stable, 1)
                raw = generate_raw(args.base_url, args.model, f"{args.cell_id}-scope-canary-{scope_token(scope_id)}",
                                   candidate_messages, args.timeout, args.registration_max_tokens)
                candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
                next_ids = tokenize(args.base_url, args.model, next_messages, True, args.timeout)
                stable_end = lcp_length(candidate_ids, next_ids)
                payload = {
                    "request_id": f"{args.cell_id}-verify-{scope_token(scope_id)}",
                    "prompt_token_ids": candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]],
                    "txn_id": f"{args.cell_id}-txn-{scope_token(scope_id)}",
                    "policy_hash": args.policy_hash, "policy_version": "tsc-tenant-v0",
                    "attestation_mode": "prospective-qualified-template-exact-path-v1",
                    "stable_prefix_end_token": stable_end, "verify_start_token": len(candidate_ids),
                    "reference_answer_ids": raw["token_ids"], "reference_raw_margins": raw["margins"],
                    "terminal_stop_token_id": raw["terminal_stop_token_id"],
                    "stable_content_hash": digest(candidate_ids[:stable_end]),
                    "layout_hash": digest(candidate_ids), "dependency_graph_hash": digest(scope_id),
                    "timeout_s": args.timeout, "cache_salt": f"{args.policy_hash}:{scope_id}",
                }
                verify_started = time.perf_counter()
                body = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
                verification_ms = (time.perf_counter() - verify_started) * 1000.0
                issued = bool(body.get("certificate_issued"))
                decision = str(body.get("verify_decision", ""))
        except Exception as exc:
            issued = False; error_type = type(exc).__name__; error_message = str(exc)
        certificates[scope_id] = issued
        rows.append({
            "scope_id": scope_id, "policy": args.policy, "certificate_issued": issued,
            "verify_decision": decision, "verification_ms": verification_ms,
            "registration_ms": (time.perf_counter() - started) * 1000.0,
            "error_type": error_type, "error_message": error_message,
            "txn_state": body.get("txn_state", ""),
            "failure_reason": body.get("failure_reason", ""),
        })
    for tenant in tenants:
        tenant["registered_scope_id"] = str(tenant["scope_id"])
        if args.policy == "D0-native-apc":
            tenant["effective_policy"] = "raw-order"
        elif args.policy == "D1-frozen-safe":
            tenant["effective_policy"] = "frozen-safe-scoped"
        else:
            tenant["effective_policy"] = "frozen-safe-scoped" if certificates[str(tenant["scope_id"])] else "raw-order"
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("D0-native-apc", "D1-frozen-safe", "D2-full-contractkv"), required=True)
    parser.add_argument("--tenants", type=int, default=40)
    parser.add_argument("--sharing-ratio", type=float, required=True)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--shared-target-tokens", type=int, default=2048)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--registration-max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--registration-output", type=Path, required=True)
    parser.add_argument("--policy-hash", default="tsc-tenant-frozen-v0")
    parser.add_argument("--allow-capacity-failure", action="store_true")
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    stable = fit_shared_text(tokenizer, args.shared_target_tokens)
    tenants = tenant_specs(args.tenants, args.sharing_ratio)
    registration_rows = register_scopes(args, tenants, stable)
    args.certificate_issue_rate = sum(truth(row["certificate_issued"]) for row in registration_rows) / max(1, len(registration_rows))
    args.mean_verification_ms = statistics.mean(number(row["verification_ms"]) for row in registration_rows)
    args.mean_registration_ms = statistics.mean(number(row["registration_ms"]) for row in registration_rows)
    args.total_registration_ms = sum(number(row["registration_ms"]) for row in registration_rows)
    args.actual_verifier_endpoint_calls = sum(
        row.get("verify_decision") not in {"NOT_REQUIRED", ""} for row in registration_rows)
    args.transaction_commits = sum(truth(row.get("certificate_issued")) for row in registration_rows)
    for tenant in tenants:
        first, _ = messages(tenant["effective_policy"], tenant, stable, 0)
        second, _ = messages(tenant["effective_policy"], tenant, stable, 1)
        first_ids = tokenizer.apply_chat_template(first, tokenize=True, add_generation_prompt=True)
        second_ids = tokenizer.apply_chat_template(second, tokenize=True, add_generation_prompt=True)
        tenant["allowed_prefix_tokens"] = lcp_length(first_ids, second_ids)
    for tenant in tenants:
        warm, _ = messages(tenant["effective_policy"], tenant, stable, 0)
        result = send_chat_stream(args.base_url, args.model, warm, args.max_tokens, args.timeout,
                                  f"{args.cell_id}-{tenant['tenant_id']}-warmup",
                                  cache_salt=f"{args.policy_hash}:{tenant['scope_id']}")
        if not result.get("success"):
            raise RuntimeError(f"warmup failed for {tenant['tenant_id']}: {result.get('error_message')}")
    offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    rows = asyncio.run(replay(args, tenants, stable))
    time.sleep(1.0)
    metrics, snapshot_stats = initial_metrics(args.metrics_events, offset)
    join(rows, metrics)
    summary = summarize(args, rows, tenants, snapshot_stats)
    write_jsonl(args.raw_output, rows)
    write_jsonl(args.summary_output, summary)
    write_jsonl(args.registration_output, registration_rows)
    gate = (len(rows) == args.tenants * (args.turns - 1)
            and (args.allow_capacity_failure or all(truth(row.get("success")) for row in rows))
            and summary[0]["unauthorized_cross_tenant_reuse"] == 0
            and summary[0]["scope_invalid_admissions"] == 0
            and summary[0]["allowed_refcount_match_rate"] == 1.0)
    print(json.dumps({"rows": len(rows), "gate_pass": gate, **isolation(rows)}, indent=2))
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
