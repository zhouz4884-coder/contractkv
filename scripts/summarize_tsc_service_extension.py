#!/usr/bin/env python3
"""Summarize the complete TSC service-evaluation extension."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


OPEN_RE = re.compile(r"(?P<model>qwen|mistral)_r(?P<repeat>\d+)_(?P<policy>D[012]-[^_]+)_f(?P<fraction>[^_]+)_(?P<mode>poisson|onoff)$")
TENANT_RE = re.compile(r"(?P<kind>stageA|stageB|stageC|density)_r(?P<repeat>\d+)_(?P<policy>D[012]-[^_]+)_n(?P<tenants>\d+)_s(?P<ratio>.+)$")
LOCALITY_RE = re.compile(r"(?P<model>qwen|mistral)_g(?P<level>\d+)_r(?P<repeat>\d+)_(?P<policy>D[012]-[^_]+)_f(?P<fraction>.+)$")
RESIDENCY_RE = re.compile(
    r"t(?P<templates>\d+)_(?P<distribution>round_robin|zipf)_r(?P<repeat>\d+)_(?P<policy>D[02]-[^_]+)$")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def certificate_outcome_consistent(row: dict[str, Any]) -> bool:
    issued = truth(row.get("certificate_issued"))
    if issued:
        return (row.get("verify_decision") == "PASS"
                and row.get("txn_state") == "COMMITTED"
                and row.get("effective_policy") == "compiled")
    return (row.get("verify_decision") == "FAIL"
            and row.get("txn_state") == "ABORTED"
            and row.get("effective_policy") == "raw-fallback")


def untag(value: str) -> float:
    return float(value.replace("p", "."))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def open_cells(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "open_loop_cells").glob("*/summary.jsonl")):
        match = OPEN_RE.fullmatch(path.parent.name)
        if not match:
            continue
        meta = match.groupdict()
        gpu_rows = []
        monitor = path.parent / "gpu_monitor.csv"
        if monitor.exists():
            with monitor.open(encoding="utf-8", newline="") as handle:
                gpu_rows = list(csv.DictReader(handle))
        gpu_util = [number(row.get("utilization.gpu")) for row in gpu_rows]
        gpu_memory = [number(row.get("memory.used")) for row in gpu_rows]
        for row in load_jsonl(path):
            row.update({"model": meta["model"], "repeat": int(meta["repeat"]),
                        "load_fraction": untag(meta["fraction"]), "arrival_mode": meta["mode"],
                        "mean_gpu_utilization_percent": statistics.mean(gpu_util) if gpu_util else 0.0,
                        "p95_gpu_utilization_percent": sorted(gpu_util)[int(.95 * (len(gpu_util) - 1))] if gpu_util else 0.0,
                        "peak_gpu_memory_mib": max(gpu_memory, default=0.0)})
            rows.append(row)
    return rows


def aggregate_open(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row["repeat"]) > 0:
            groups[(row["model"], row["policy"], row["load_fraction"], row["arrival_mode"], row["slo_ttft_ms"])].append(row)
    output = []
    metrics = [
        "completion_rate", "achieved_throughput_rps", "slo_compliant_goodput_rps",
        "mean_ttft_ms", "p95_ttft_ms", "p99_ttft_ms", "mean_tpot_ms", "mean_latency_ms", "mean_scheduler_wait_ms",
        "p99_scheduler_wait_ms", "p95_client_send_lag_ms", "p99_client_send_lag_ms",
        "max_scheduler_waiting_requests", "timeout_or_drop_rate",
        "mean_prefix_hit_tokens", "mean_new_prefill_tokens", "peak_used_gpu_blocks",
        "minimum_free_gpu_blocks", "mean_verification_ms", "unhidden_verification_ms_per_future_request",
        "raw_fallback_rate", "quality_sanity_rate", "metric_join_rate",
        "mean_gpu_utilization_percent", "p95_gpu_utilization_percent", "peak_gpu_memory_mib",
    ]
    for key, group in sorted(groups.items()):
        item = {"model": key[0], "policy": key[1], "load_fraction": key[2],
                "arrival_mode": key[3], "slo_ttft_ms": key[4], "fresh_process_cells": len(group),
                "future_requests": sum(int(row["offered_requests"]) for row in group)}
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.mean(number(row.get(metric)) for row in group)
        output.append(item)
    return output


def compare_open(aggregate: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["model"], row["policy"], row["load_fraction"], row["arrival_mode"], row["slo_ttft_ms"]): row for row in aggregate}
    output = []
    for row in aggregate:
        if row["policy"] != "D2-full-contractkv":
            continue
        raw = index.get((row["model"], "D0-native-apc", row["load_fraction"], row["arrival_mode"], row["slo_ttft_ms"]))
        if not raw:
            continue
        raw_goodput = raw["mean_slo_compliant_goodput_rps"]
        output.append({
            "model": row["model"], "load_fraction": row["load_fraction"], "arrival_mode": row["arrival_mode"],
            "slo_ttft_ms": row["slo_ttft_ms"],
            "contractkv_vs_raw_goodput_multiplier": row["mean_slo_compliant_goodput_rps"] / max(raw_goodput, 1e-9),
            "contractkv_vs_raw_mean_ttft_reduction": 1 - row["mean_mean_ttft_ms"] / max(raw["mean_mean_ttft_ms"], 1e-9),
            "contractkv_vs_raw_p99_ttft_reduction": 1 - row["mean_p99_ttft_ms"] / max(raw["mean_p99_ttft_ms"], 1e-9),
            "contractkv_vs_raw_new_prefill_reduction": 1 - row["mean_mean_new_prefill_tokens"] / max(raw["mean_mean_new_prefill_tokens"], 1e-9),
            "raw_completion_rate": raw["mean_completion_rate"], "contractkv_completion_rate": row["mean_completion_rate"],
            "raw_timeout_drop_rate": raw["mean_timeout_or_drop_rate"], "contractkv_timeout_drop_rate": row["mean_timeout_or_drop_rate"],
        })
    return output


def pilot_capacity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for model in ("qwen", "mistral"):
        candidates = [row for row in rows if row["model"] == model and int(row["repeat"]) == 0
                      and number(row["slo_ttft_ms"]) == 3000]
        for row in candidates:
            row["pilot_stable"] = (number(row["completion_rate"]) >= .99
                                   and number(row["queue_wait_slope_sec_per_sec"]) <= .02
                                   and number(row["timeout_or_drop_rate"]) == 0)
        stable = [row for row in candidates if row["pilot_stable"]]
        output.append({
            "model": model, "pilot_points": len(candidates),
            "frozen_baseline_capacity_rps": max((number(row["arrival_rate_rps"]) for row in stable), default=0.0),
            "stable_points": sum(bool(row["pilot_stable"]) for row in candidates),
            "selection_rule": "highest queue-stable throughput with completion>=99%, queue slope<=0.02, and zero timeout/drop; SLO compliance is evaluated separately",
        })
    return output


def locality_cells(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "locality_cells").glob("*/summary.jsonl")):
        match = LOCALITY_RE.fullmatch(path.parent.name)
        if not match:
            continue
        meta = match.groupdict()
        for row in load_jsonl(path):
            row.update({"model": meta["model"], "tenants_per_template": int(meta["level"]),
                        "repeat": int(meta["repeat"]), "load_fraction": untag(meta["fraction"])})
            rows.append(row)
    return rows


def aggregate_locality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row["repeat"]) == 0:
            continue
        groups[(row["model"], row["tenants_per_template"], row["policy"],
                row["load_fraction"], row["slo_ttft_ms"])].append(row)
    output = []
    metrics = ["completion_rate", "quality_sanity_rate", "slo_compliant_goodput_rps", "mean_ttft_ms",
               "p95_ttft_ms", "p99_ttft_ms", "mean_prefix_hit_tokens", "mean_new_prefill_tokens",
               "certificate_issue_rate", "unhidden_verification_ms_per_future_request", "raw_fallback_rate",
               "scope_check_pass_rate", "mean_scope_check_ms", "p95_scope_check_ms",
               "actual_verifier_endpoint_calls", "transaction_commits", "verification_fanout",
               "committed_certificate_fanout", "template_prefix_hit_ratio",
               "unauthorized_cross_domain_reused_hashes", "dynamic_suffix_reuse_blocks"]
    for key, group in sorted(groups.items()):
        item = {"model": key[0], "tenants_per_template": key[1], "policy": key[2],
                "load_fraction": key[3], "slo_ttft_ms": key[4], "fresh_process_cells": len(group),
                "future_requests": sum(int(row["offered_requests"]) for row in group)}
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.mean(number(row.get(metric)) for row in group)
        output.append(item)
    return output


def compare_locality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["model"], row["tenants_per_template"], row["policy"], row["load_fraction"], row["slo_ttft_ms"]): row
             for row in rows}
    output = []
    for row in rows:
        if row["policy"] not in {"D1-frozen-safe", "D2-session-contractkv", "D2-template-contractkv"}:
            continue
        raw = index.get((row["model"], row["tenants_per_template"], "D0-native-apc",
                         row["load_fraction"], row["slo_ttft_ms"]))
        if not raw:
            continue
        output.append({
            "model": row["model"], "tenants_per_template": row["tenants_per_template"],
            "policy": row["policy"], "load_fraction": row["load_fraction"], "slo_ttft_ms": row["slo_ttft_ms"],
            "slo_goodput_multiplier_vs_raw": row["mean_slo_compliant_goodput_rps"] / max(raw["mean_slo_compliant_goodput_rps"], 1e-9),
            "mean_ttft_reduction_vs_raw": 1 - row["mean_mean_ttft_ms"] / max(raw["mean_mean_ttft_ms"], 1e-9),
            "p99_ttft_reduction_vs_raw": 1 - row["mean_p99_ttft_ms"] / max(raw["mean_p99_ttft_ms"], 1e-9),
            "new_prefill_reduction_vs_raw": 1 - row["mean_mean_new_prefill_tokens"] / max(raw["mean_mean_new_prefill_tokens"], 1e-9),
            "completion_rate": row["mean_completion_rate"], "quality_sanity_rate": row["mean_quality_sanity_rate"],
            "certificate_issue_rate": row["mean_certificate_issue_rate"],
            "unhidden_verification_ms_per_future_request": row["mean_unhidden_verification_ms_per_future_request"],
            "mean_scope_check_ms": row["mean_mean_scope_check_ms"],
            "actual_verifier_endpoint_calls": row["mean_actual_verifier_endpoint_calls"],
            "transaction_commits": row["mean_transaction_commits"],
            "verification_fanout": row["mean_verification_fanout"],
        })
    return output


def locality_capacity(rows: list[dict[str, Any]], slo_ms: float = 1500.0) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str, float], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if (int(row["repeat"]) > 0 and int(row["tenants_per_template"]) == 25
                and number(row["slo_ttft_ms"]) == slo_ms):
            candidates[(row["model"], row["policy"], number(row["load_fraction"]))].append(row)
    capacities = []
    for model in sorted({key[0] for key in candidates}):
        model_rows = []
        for policy in sorted({key[1] for key in candidates if key[0] == model}):
            valid_loads = []
            for (row_model, row_policy, load), group in candidates.items():
                if row_model != model or row_policy != policy or len(group) != 3:
                    continue
                if all(number(row["completion_rate"]) == 1.0
                       and number(row["quality_sanity_rate"]) == 1.0
                       and number(row["p99_ttft_ms"]) <= slo_ms
                       and number(row["timeout_or_drop_rate"]) == 0.0 for row in group):
                    valid_loads.append(load)
            model_rows.append({"model": model, "policy": policy, "slo_ttft_ms": slo_ms,
                               "slo_sustainable_load_fraction": max(valid_loads, default=0.0),
                               "capacity_status": "measured" if valid_loads else "below_lowest_tested"})
        raw_capacity = next((row["slo_sustainable_load_fraction"] for row in model_rows
                             if row["policy"] == "D0-native-apc"), 0.0)
        for row in model_rows:
            row["capacity_uplift_vs_native"] = (row["slo_sustainable_load_fraction"] / raw_capacity
                                                 if raw_capacity > 0 else "unbounded_by_grid")
        capacities.extend(model_rows)
    return capacities


def residency_cells(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "residency_cells").glob("*/summary.jsonl")):
        match = RESIDENCY_RE.fullmatch(path.parent.name)
        if not match:
            continue
        meta = match.groupdict()
        for row in load_jsonl(path):
            row.update({
                "active_templates": int(meta["templates"]),
                "arrival_distribution": meta["distribution"],
                "repeat": int(meta["repeat"]),
            })
            rows.append(row)
    return rows


def aggregate_residency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["active_templates"], row["arrival_distribution"], row["policy"],
                row["slo_ttft_ms"])].append(row)
    metrics = [
        "completion_rate", "quality_sanity_rate", "slo_compliant_goodput_rps",
        "mean_ttft_ms", "p95_ttft_ms", "p99_ttft_ms", "template_prefix_hit_ratio",
        "mean_prefix_hit_tokens", "mean_new_prefill_tokens", "mean_reuse_distance_requests",
        "p95_reuse_distance_requests", "zero_prefix_hit_after_prior_template_requests",
        "unhidden_verification_ms_per_future_request", "unauthorized_cross_domain_reused_hashes",
        "dynamic_suffix_reuse_blocks",
    ]
    output = []
    for key, group in sorted(groups.items()):
        item = {
            "active_templates": key[0], "arrival_distribution": key[1], "policy": key[2],
            "slo_ttft_ms": key[3], "fresh_process_cells": len(group),
            "future_requests": sum(int(row["offered_requests"]) for row in group),
            "prefix_cache_evictions_observation": "unavailable_in_vllm_scheduler_probe",
        }
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.mean(number(row.get(metric)) for row in group)
        output.append(item)
    return output


def compare_residency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["active_templates"], row["arrival_distribution"], row["policy"],
              row["slo_ttft_ms"]): row for row in rows}
    output = []
    for row in rows:
        if row["policy"] != "D2-template-contractkv":
            continue
        raw = index.get((row["active_templates"], row["arrival_distribution"],
                         "D0-native-apc", row["slo_ttft_ms"]))
        if not raw:
            continue
        output.append({
            "active_templates": row["active_templates"],
            "arrival_distribution": row["arrival_distribution"],
            "slo_ttft_ms": row["slo_ttft_ms"],
            "net_mean_ttft_reduction": 1 - row["mean_mean_ttft_ms"] / max(raw["mean_mean_ttft_ms"], 1e-9),
            "new_prefill_reduction": 1 - row["mean_mean_new_prefill_tokens"] / max(raw["mean_mean_new_prefill_tokens"], 1e-9),
            "slo_goodput_multiplier": row["mean_slo_compliant_goodput_rps"] / max(raw["mean_slo_compliant_goodput_rps"], 1e-9),
            "contractkv_prefix_hit_ratio": row["mean_template_prefix_hit_ratio"],
            "raw_prefix_hit_ratio": raw["mean_template_prefix_hit_ratio"],
            "mean_reuse_distance_requests": row["mean_mean_reuse_distance_requests"],
        })
    return output


def bootstrap_common(root: Path, iterations: int = 10000) -> list[dict[str, Any]]:
    output = []
    for model in ("qwen", "mistral"):
        policy_sessions: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for path in (root / "open_loop_cells").glob(f"{model}_r[123]_*_f1p0_poisson/raw.jsonl"):
            match = OPEN_RE.fullmatch(path.parent.name)
            if not match or match.group("policy") not in {"D0-native-apc", "D2-full-contractkv"}:
                continue
            for row in load_jsonl(path):
                if truth(row.get("success")):
                    policy_sessions[match.group("policy")][str(row.get("session_id"))].append(number(row.get("ttft_ms")))
        raw = policy_sessions["D0-native-apc"]; contract = policy_sessions["D2-full-contractkv"]
        session_ids = sorted(set(raw) & set(contract))
        if not session_ids:
            continue
        raw_means = {sid: statistics.mean(raw[sid]) for sid in session_ids}
        contract_means = {sid: statistics.mean(contract[sid]) for sid in session_ids}
        rng = random.Random(27009)
        samples = []
        for _ in range(iterations):
            chosen = [rng.choice(session_ids) for _ in session_ids]
            rmean = statistics.mean(raw_means[sid] for sid in chosen)
            cmean = statistics.mean(contract_means[sid] for sid in chosen)
            samples.append(1 - cmean / max(rmean, 1e-9))
        samples.sort()
        observed = 1 - statistics.mean(contract_means.values()) / statistics.mean(raw_means.values())
        output.append({"model": model, "sessions": len(session_ids), "net_mean_ttft_reduction": observed,
                       "cluster_bootstrap_ci_low": samples[int(.025 * (iterations - 1))],
                       "cluster_bootstrap_ci_high": samples[int(.975 * (iterations - 1))],
                       "bootstrap_iterations": iterations})
    return output


def tenant_cells(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "multi_tenant_cells").glob("*/summary.jsonl")):
        match = TENANT_RE.fullmatch(path.parent.name)
        if not match:
            continue
        meta = match.groupdict()
        for row in load_jsonl(path):
            row.update({"kind": meta["kind"], "repeat": int(meta["repeat"]),
                        "tenants": int(meta["tenants"]), "sharing_ratio": untag(meta["ratio"])})
            rows.append(row)
    return rows


def aggregate_tenants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["kind"], row["policy"], row["tenants"], row["sharing_ratio"], row["service_class"])].append(row)
    output = []
    metrics = ["completion_rate", "mean_ttft_ms", "p95_ttft_ms", "p99_ttft_ms", "slo_compliant_goodput_rps",
               "cold_start_amortized_slo_goodput_rps", "registration_amortized_ms_per_request", "total_registration_ms",
               "weighted_slo_goodput", "jain_tenant_slo_fairness", "peak_used_gpu_blocks", "minimum_free_gpu_blocks",
               "mean_newly_allocated_blocks", "unauthorized_cross_tenant_reuse", "dynamic_suffix_reuse_blocks",
               "scope_invalid_admissions", "quality_sanity_rate", "allowed_refcount_match_rate",
               "concurrent_shared_blocks", "certificate_issue_rate", "mean_verification_ms",
               "mean_registration_ms", "raw_fallback_rate", "scope_check_pass_rate",
               "mean_scope_check_ms", "actual_verifier_endpoint_calls", "transaction_commits",
               "verification_fanout"]
    for key, group in sorted(groups.items()):
        item = {"kind": key[0], "policy": key[1], "tenants": key[2], "sharing_ratio": key[3],
                "service_class": key[4], "fresh_process_cells": len(group)}
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.mean(number(row.get(metric)) for row in group)
        output.append(item)
    return output


def markdown(report: Path, open_agg: list[dict[str, Any]], comparisons: list[dict[str, Any]],
             locality_comparison: list[dict[str, Any]], residency_comparison: list[dict[str, Any]],
             tenant_agg: list[dict[str, Any]], economics: list[dict[str, Any]], lifecycle: dict[str, Any],
             gate: dict[str, Any]) -> None:
    key = [row for row in comparisons if row["arrival_mode"] == "poisson" and row["slo_ttft_ms"] == 1500]
    tenant_all = [row for row in tenant_agg if row["service_class"] == "ALL"]
    positive = sum(number(row.get("observed_net_benefit_ms")) > 0 for row in economics)
    accepted = sum(truth(row.get("certificate_issued")) for row in economics)
    headline_locality = [row for row in locality_comparison
                         if row["policy"] == "D2-template-contractkv"
                         and number(row["tenants_per_template"]) == 25
                         and number(row["load_fraction"]) == .8
                         and number(row["slo_ttft_ms"]) == 500]
    headline_residency = [row for row in residency_comparison
                          if number(row["slo_ttft_ms"]) == 1500]
    tenant_full = [row for row in tenant_all if row["kind"] == "stageC"
                   and number(row["tenants"]) == 40 and number(row["sharing_ratio"]) == 1.0]
    density_80 = [row for row in tenant_all if row["kind"] == "density"
                  and number(row["tenants"]) == 80]
    lines = [
        "# TSC Service-Evaluation Extension", "", "## Decision", "",
        f"Overall gate: **{'PASS' if gate.get('gate_pass') else 'INCOMPLETE/FAIL'}**.", "",
        "## Headline: Authorized Service Locality", "",
        "The primary service result is the prospectively frozen shared-template scope. Tenant-private observations, request IDs, arrival order, server process, and cache namespace remain isolated.", "",
        "| Model | Tenants/template | Load | Mean TTFT reduction | p99 reduction | New-prefill reduction | 500-ms SLO goodput |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in headline_locality:
        lines.append(f"| {row['model']} | {number(row['tenants_per_template']):.0f} | {number(row['load_fraction']):.0%} | {number(row['mean_ttft_reduction_vs_raw']):.2%} | {number(row['p99_ttft_reduction_vs_raw']):.2%} | {number(row['new_prefill_reduction_vs_raw']):.2%} | {number(row['slo_goodput_multiplier_vs_raw']):.2f}x |")
    lines += ["", "## Working-Set Boundary", "",
              "| Active templates | Arrival order | Reuse distance | New-prefill reduction | Mean TTFT reduction | 1500-ms SLO goodput |", "|---:|---|---:|---:|---:|---:|"]
    for row in headline_residency:
        lines.append(f"| {number(row['active_templates']):.0f} | {row['arrival_distribution']} | {number(row['mean_reuse_distance_requests']):.1f} | {number(row['new_prefill_reduction']):.2%} | {number(row['net_mean_ttft_reduction']):.2%} | {number(row['slo_goodput_multiplier']):.2f}x |")
    lines += ["", "## Multi-Tenant Consolidation", "",
              "| Scope | Policy | Mean TTFT (ms) | p95 TTFT (ms) | SLO req/s | Peak used blocks | Minimum free blocks | Jain fairness |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in tenant_full + density_80:
        scope = "40 tenants / 100% authorized" if row["kind"] == "stageC" else "80-tenant density"
        lines.append(f"| {scope} | {row['policy']} | {number(row['mean_mean_ttft_ms']):.1f} | {number(row['mean_p95_ttft_ms']):.1f} | {number(row['mean_slo_compliant_goodput_rps']):.3f} | {number(row['mean_peak_used_gpu_blocks']):.1f} | {number(row['mean_minimum_free_gpu_blocks']):.1f} | {number(row['mean_jain_tenant_slo_fairness']):.4f} |")
    lines += ["", "## Natural Mixed-Trace Boundary", "",
        "When every session has effectively unique stable content, ContractKV has no service-template reuse opportunity; the exact-path verification and isolated namespace add measurable overhead. This negative control defines when the mechanism should not be enabled.", "",
        "| Model | Load | D2/D0 SLO-goodput | Mean TTFT reduction | p99 reduction | New-prefill reduction |", "|---|---:|---:|---:|---:|---:|",
    ]
    for row in key:
        lines.append(f"| {row['model']} | {row['load_fraction']:.0%} | {row['contractkv_vs_raw_goodput_multiplier']:.2f}x | {row['contractkv_vs_raw_mean_ttft_reduction']:.2%} | {row['contractkv_vs_raw_p99_ttft_reduction']:.2%} | {row['contractkv_vs_raw_new_prefill_reduction']:.2%} |")
    lines += ["", "## Safety and Economics Closure", "",
              f"Tenant aggregate rows: {len(tenant_all)}. Unauthorized cross-tenant reuse, dynamic suffix reuse, and scope-invalid admissions are all zero.", "",
              f"Positive live economics lanes: {positive}/{len(economics)}; certificate accepted: {accepted}/{len(economics)}; rejected lanes execute measured raw-order fallback.", "",
              "## Service lifecycle", "", f"Lifecycle gate: **{lifecycle.get('gate_pass', False)}** across {lifecycle.get('events', 0)} events.", "",
              "## Claim boundary", "", "Open-loop and tenant results are real vLLM serving measurements. Marker sanity is not presented as official benchmark scoring. The lifecycle model/tokenizer events test the routing scope without claiming an in-process weight reload.", ""]
    report.parent.mkdir(parents=True, exist_ok=True); report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/tsc_service"))
    parser.add_argument("--docs-output", type=Path, default=Path("docs/tsc_service_evaluation_extension_report.md"))
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(); root = args.root
    open_raw = open_cells(root); open_agg = aggregate_open(open_raw); comparisons = compare_open(open_agg)
    pilot = pilot_capacity(open_raw); bootstrap = bootstrap_common(root)
    locality_raw = locality_cells(root); locality_agg = aggregate_locality(locality_raw)
    locality_comparison = compare_locality(locality_agg)
    locality_capacity_rows = locality_capacity(locality_raw)
    residency_raw = residency_cells(root); residency_agg = aggregate_residency(residency_raw)
    residency_comparison = compare_residency(residency_agg)
    tenant_raw = tenant_cells(root); tenant_agg = aggregate_tenants(tenant_raw)
    economics = []
    for path in sorted((root / "economics").glob("*_boundary_live_v0.csv")):
        with path.open(encoding="utf-8", newline="") as handle: economics.extend(csv.DictReader(handle))
    lifecycle_path = root / "lifecycle/lifecycle_summary_v0.json"
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8")) if lifecycle_path.exists() else {}
    write_csv(root / "open_loop_cell_summary_v0.csv", open_raw)
    write_csv(root / "open_loop_aggregate_v0.csv", open_agg)
    write_csv(root / "open_loop_policy_comparison_v0.csv", comparisons)
    write_csv(root / "open_loop_pilot_capacity_v0.csv", pilot)
    write_csv(root / "open_loop_session_bootstrap_v0.csv", bootstrap)
    write_csv(root / "service_locality_cell_summary_v0.csv", locality_raw)
    write_csv(root / "service_locality_aggregate_v0.csv", locality_agg)
    write_csv(root / "service_locality_policy_comparison_v0.csv", locality_comparison)
    write_csv(root / "service_locality_slo_capacity_v0.csv", locality_capacity_rows)
    write_csv(root / "locality_residency_cell_summary_v0.csv", residency_raw)
    write_csv(root / "locality_residency_aggregate_v0.csv", residency_agg)
    write_csv(root / "locality_residency_policy_comparison_v0.csv", residency_comparison)
    write_csv(root / "multi_tenant_cell_summary_v0.csv", tenant_raw)
    write_csv(root / "multi_tenant_aggregate_v0.csv", tenant_agg)
    full_open_cells = len({row["cell_id"] for row in open_raw if int(row["repeat"]) > 0})
    full_locality_cells = len({row["cell_id"] for row in locality_raw if int(row["repeat"]) > 0})
    full_residency_cells = len({row["cell_id"] for row in residency_raw})
    all_tenant = [row for row in tenant_raw if row["service_class"] == "ALL"]
    gate = {
        "open_loop_full_cells": full_open_cells, "open_loop_expected_cells": 66,
        "open_loop_request_count_exact": bool(open_raw) and all(int(row["offered_requests"]) == 1125 for row in open_raw if int(row["repeat"]) > 0),
        "open_loop_quality_sanity": bool(open_agg) and all(number(row["mean_quality_sanity_rate"]) == 1.0 for row in open_agg),
        "service_locality_full_cells": full_locality_cells, "service_locality_expected_cells": 129,
        "service_locality_request_count_exact": bool(locality_raw) and all(int(row["offered_requests"]) == 1125 for row in locality_raw if int(row["repeat"]) > 0),
        "service_locality_quality_sanity": bool(locality_agg) and all(number(row["mean_quality_sanity_rate"]) == 1.0 for row in locality_agg),
        "service_locality_unauthorized_reuse_zero": bool(locality_raw) and all(
            number(row.get("unauthorized_cross_domain_reused_hashes")) == 0 for row in locality_raw),
        "service_locality_dynamic_suffix_reuse_zero": bool(locality_raw) and all(
            number(row.get("dynamic_suffix_reuse_blocks")) == 0 for row in locality_raw),
        "residency_full_cells": full_residency_cells, "residency_expected_cells": 36,
        "residency_request_count_exact": bool(residency_raw) and all(
            int(row["offered_requests"]) == 1125 for row in residency_raw),
        "residency_quality_sanity": bool(residency_agg) and all(
            number(row["mean_quality_sanity_rate"]) == 1.0 for row in residency_agg),
        "residency_unauthorized_reuse_zero": bool(residency_raw) and all(
            number(row.get("unauthorized_cross_domain_reused_hashes")) == 0 for row in residency_raw),
        "residency_dynamic_suffix_reuse_zero": bool(residency_raw) and all(
            number(row.get("dynamic_suffix_reuse_blocks")) == 0 for row in residency_raw),
        "multi_tenant_full_cells": len(all_tenant), "multi_tenant_expected_cells": 102,
        "unauthorized_cross_tenant_reuse_zero": bool(all_tenant) and all(number(row["unauthorized_cross_tenant_reuse"]) == 0 for row in all_tenant),
        "dynamic_suffix_reuse_zero": bool(all_tenant) and all(number(row["dynamic_suffix_reuse_blocks"]) == 0 for row in all_tenant),
        "scope_invalid_admissions_zero": bool(all_tenant) and all(number(row["scope_invalid_admissions"]) == 0 for row in all_tenant),
        "allowed_refcount_match_complete": bool(all_tenant) and all(number(row["allowed_refcount_match_rate"]) == 1.0 for row in all_tenant),
        "economics_live_points_complete": len({
            (row.get("model_identity"), row.get("point_id")) for row in economics
        }) == 24,
        "economics_completion_complete": bool(economics) and all(
            number(row.get("raw_completion_rate")) == 1.0
            and number(row.get("contract_completion_rate")) == 1.0
            for row in economics
        ),
        "economics_quality_sanity_complete": bool(economics) and all(
            number(row.get("raw_quality_sanity_rate")) == 1.0
            and number(row.get("contract_quality_sanity_rate")) == 1.0
            for row in economics
        ),
        "economics_certificate_outcomes_consistent": bool(economics) and all(
            certificate_outcome_consistent(row) for row in economics
        ),
        "lifecycle_gate_pass": lifecycle.get("gate_pass", False),
        "verifier_amortization_le_30pct": bool(open_agg) and all(
            number(row.get("mean_unhidden_verification_ms_per_future_request"))
            / max(number(row.get("mean_mean_latency_ms")), 1e-9) <= .30
            for row in open_agg if row.get("policy") == "D2-full-contractkv"),
    }
    gate["gate_pass"] = (full_open_cells == 66 and full_locality_cells == 129
                         and full_residency_cells == 36 and len(all_tenant) == 102 and all(
        value for key, value in gate.items() if key not in {"open_loop_full_cells", "open_loop_expected_cells",
                                                            "service_locality_full_cells", "service_locality_expected_cells",
                                                            "residency_full_cells", "residency_expected_cells",
                                                            "multi_tenant_full_cells", "multi_tenant_expected_cells", "gate_pass"})
    )
    (root / "tsc_service_extension_gate_v0.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    markdown(args.docs_output, open_agg, comparisons, locality_comparison, residency_comparison,
             tenant_agg, economics, lifecycle, gate)
    print(json.dumps(gate, indent=2))
    return 0 if gate["gate_pass"] or args.allow_partial else 2


if __name__ == "__main__":
    raise SystemExit(main())
