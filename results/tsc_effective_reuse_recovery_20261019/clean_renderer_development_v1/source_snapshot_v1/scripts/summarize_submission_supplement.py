#!/usr/bin/env python3
"""Build paper-facing repeat, bootstrap, SLO, and physical-accounting supplements."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SLO_BUCKETS = (250, 500, 750, 1000, 1250, 1500, 2000, 3000)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - index) + ordered[hi] * (index - lo)


def future(rows: Iterable[dict[str, Any]], family: str | None = None) -> list[dict[str, Any]]:
    result = [row for row in rows if row.get("row_type") == "future" and row.get("success") is True]
    if family:
        dataset, task = family.split(":", 1)
        result = [row for row in result if row.get("dataset") == dataset and row.get("task") == task]
    return result


def verifier_by_session(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for row in rows:
        if row.get("row_type") == "canary":
            result[str(row.get("session_id"))] += float(row.get("unhidden_verifier_ms", 0) or 0)
    return result


def add_exposure(rows: list[dict[str, Any]]) -> None:
    batch_counts = Counter(str(row.get("batch_id") or row.get("request_id")) for row in rows)
    for row in rows:
        batch = str(row.get("batch_id") or row.get("request_id"))
        row["_exposure_ms"] = float(row.get("batch_wall_ms", row.get("latency_ms", 0)) or 0) / max(batch_counts[batch], 1)


def clusters(rows: list[dict[str, Any]], family: str | None = None) -> dict[str, list[dict[str, Any]]]:
    selected = future(rows, family)
    add_exposure(selected)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        grouped[str(row.get("session_id"))].append(row)
    return grouped


def sample_metrics(
    raw_groups: dict[str, list[dict[str, Any]]],
    contract_groups: dict[str, list[dict[str, Any]]],
    verifier: dict[str, float],
    sampled_sessions: list[str],
    slo_ms: float,
) -> dict[str, float]:
    raw_rows = [row for sid in sampled_sessions for row in raw_groups[sid]]
    contract_rows = [row for sid in sampled_sessions for row in contract_groups[sid]]
    raw_ttft = [float(row["ttft_ms"]) for row in raw_rows]
    contract_ttft = [float(row["ttft_ms"]) for row in contract_rows]
    verifier_total = sum(verifier.get(sid, 0.0) for sid in sampled_sessions)
    certified_count = sum(row.get("certificate_issued") is True for row in contract_rows)
    # Preserve the deliberately conservative accounting used by the frozen
    # submission table: unhidden verifier cost is normalized by certified
    # requests, then charged to the cell-wide mean.
    verifier_per_request = verifier_total / max(certified_count, 1)
    net_contract_mean = statistics.fmean(contract_ttft) + verifier_per_request
    raw_wall = sum(float(row["_exposure_ms"]) for row in raw_rows) / 1000.0
    contract_wall = sum(float(row["_exposure_ms"]) for row in contract_rows) / 1000.0
    raw_goodput = sum(value <= slo_ms for value in raw_ttft) / max(raw_wall, 1e-9)
    contract_goodput = sum(value + verifier_per_request <= slo_ms for value in contract_ttft) / max(contract_wall, 1e-9)
    return {
        "net_mean_ttft_reduction": (statistics.fmean(raw_ttft) - net_contract_mean) / max(statistics.fmean(raw_ttft), 1e-9),
        "slo_goodput_gain": (contract_goodput - raw_goodput) / max(raw_goodput, 1e-9),
        "raw_slo_req_per_sec": raw_goodput,
        "contract_slo_req_per_sec": contract_goodput,
    }


def hierarchical_bootstrap(
    repeat_pairs: list[tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, float]]],
    samples: int,
    seed: int,
    slo_ms: float,
) -> dict[str, Any]:
    rng = random.Random(seed)
    observed_parts = []
    for raw_groups, contract_groups, verifier in repeat_pairs:
        shared = sorted(set(raw_groups) & set(contract_groups))
        observed_parts.append(sample_metrics(raw_groups, contract_groups, verifier, shared, slo_ms))
    observed = {key: statistics.fmean(part[key] for part in observed_parts) for key in observed_parts[0]}
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(samples):
        selected_repeats = rng.choices(repeat_pairs, k=len(repeat_pairs))
        parts = []
        for raw_groups, contract_groups, verifier in selected_repeats:
            shared = sorted(set(raw_groups) & set(contract_groups))
            sampled_sessions = rng.choices(shared, k=len(shared))
            parts.append(sample_metrics(raw_groups, contract_groups, verifier, sampled_sessions, slo_ms))
        for key in observed:
            draws[key].append(statistics.fmean(part[key] for part in parts))
    output: dict[str, Any] = {"session_clusters": sum(len(set(raw) & set(contract)) for raw, contract, _ in repeat_pairs)}
    for key, value in observed.items():
        output[f"estimate_{key}"] = value
        output[f"bootstrap95_low_{key}"] = percentile(draws[key], .025)
        output[f"bootstrap95_high_{key}"] = percentile(draws[key], .975)
    return output


def load_repeat_pair(root: Path, model: str, repeat: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = root / model / f"repeat{repeat}"
    return load_jsonl(path / "raw-order.jsonl"), load_jsonl(path / "contractkv-full.jsonl")


def load_llama_pair(root: Path, repeat: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = root / f"repeat{repeat}"
    return load_jsonl(path / f"r{repeat}-raw.jsonl"), load_jsonl(path / f"r{repeat}-contract.jsonl")


def new_prefill_reduction(raw_rows: list[dict[str, Any]], contract_rows: list[dict[str, Any]], family: str | None = None) -> float:
    raw_values = [float(row.get("new_prefill_tokens", 0) or 0) for row in future(raw_rows, family)]
    contract_values = [float(row.get("new_prefill_tokens", 0) or 0) for row in future(contract_rows, family)]
    raw_mean = statistics.fmean(raw_values)
    return 1.0 - statistics.fmean(contract_values) / max(raw_mean, 1e-9)


def build_repeat_invariance(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = []
    for model, label in (("qwen", "Qwen3-8B"), ("mistral", "Mistral-7B-Instruct-v0.3")):
        values = []
        raw_total = contract_total = 0.0
        for repeat in (1, 2, 3):
            raw, contract = load_repeat_pair(args.submission_root, model, repeat)
            values.append(new_prefill_reduction(raw, contract))
            raw_total += sum(float(row.get("new_prefill_tokens", 0) or 0) for row in future(raw))
            contract_total += sum(float(row.get("new_prefill_tokens", 0) or 0) for row in future(contract))
        rows.append(invariance_row(label, "all held-out workflows", values,
                                   "Frozen inputs, manifest, runtime, and server configuration.", raw_total, contract_total))
    llama_values = []
    llama_raw_total = llama_contract_total = 0.0
    for repeat in (1, 2, 3):
        raw, contract = load_llama_pair(args.llama_root, repeat)
        llama_values.append(new_prefill_reduction(raw, contract, "RULER:niah_single_1"))
        llama_raw_total += sum(float(row.get("new_prefill_tokens", 0) or 0)
                               for row in future(raw, "RULER:niah_single_1"))
        llama_contract_total += sum(float(row.get("new_prefill_tokens", 0) or 0)
                                    for row in future(contract, "RULER:niah_single_1"))
    rows.append(invariance_row("Llama-3.1-8B-Instruct", "prospectively qualified RULER only", llama_values,
                               "Scope differs from the global Qwen/Mistral rows.",
                               llama_raw_total, llama_contract_total))
    qwen14 = load_csv(args.qwen14_repeat_csv)
    values = [float(row["new_prefill_reduction_vs_raw"]) for row in qwen14]
    qwen14_raw_total = sum(float(row["raw_mean_new_prefill_tokens"]) * 225 for row in qwen14)
    qwen14_contract_total = sum(float(row["contract_mean_new_prefill_tokens"]) * 225 for row in qwen14)
    rows.append(invariance_row("Qwen3-14B TP=2", "limited 25-session scale-up", values,
                               "Limited scale-up, not a broad scaling-law claim.",
                               qwen14_raw_total, qwen14_contract_total))
    return rows


def invariance_row(model: str, scope: str, values: list[float], note: str,
                   raw_total: float = 0.0, contract_total: float = 0.0) -> dict[str, Any]:
    return {
        "model": model,
        "scope": scope,
        "fresh_process_repeats": len(values),
        "mean_new_prefill_reduction": statistics.fmean(values),
        "min_new_prefill_reduction": min(values),
        "max_new_prefill_reduction": max(values),
        "repeat_range": max(values) - min(values),
        "exact_repeat_invariant": max(values) - min(values) <= 1e-12,
        "prefill_work_speedup": raw_total / max(contract_total, 1e-9),
        "observed_raw_new_prefill_tokens_across_repeats": raw_total,
        "observed_contract_new_prefill_tokens_across_repeats": contract_total,
        "observed_new_prefill_tokens_saved_across_repeats": raw_total - contract_total,
        "claim_boundary": "Deterministic under frozen inputs/manifest/config; not hardware-independent. " + note,
    }


def build_bootstrap(args: argparse.Namespace) -> list[dict[str, Any]]:
    output = []
    specs = [("qwen", "Qwen3-8B", None), ("mistral", "Mistral-7B-Instruct-v0.3", None)]
    for model, label, family in specs:
        pairs = []
        for repeat in (1, 2, 3):
            raw, contract = load_repeat_pair(args.submission_root, model, repeat)
            pairs.append((clusters(raw, family), clusters(contract, family), verifier_by_session(contract)))
        record = {"model": label, "scope": "all held-out workflows", "fresh_process_repeats": 3,
                  "slo_ms": args.slo_ms, **hierarchical_bootstrap(pairs, args.bootstrap_samples, args.seed, args.slo_ms),
                  "claim_boundary": "Hierarchical bootstrap over fresh-process repeats and paired session clusters."}
        record["net_ttft_speedup"] = 1.0 / max(1.0 - record["estimate_net_mean_ttft_reduction"], 1e-9)
        record["slo_goodput_multiplier"] = 1.0 + record["estimate_slo_goodput_gain"]
        output.append(record)
    pairs = []
    for repeat in (1, 2, 3):
        raw, contract = load_llama_pair(args.llama_root, repeat)
        pairs.append((clusters(raw, "RULER:niah_single_1"), clusters(contract, "RULER:niah_single_1"), verifier_by_session(contract)))
    record = {"model": "Llama-3.1-8B-Instruct", "scope": "prospectively qualified RULER only",
              "fresh_process_repeats": 3, "slo_ms": args.slo_ms,
              **hierarchical_bootstrap(pairs, args.bootstrap_samples, args.seed + 1, args.slo_ms),
              "claim_boundary": "Qualified-scope hierarchical bootstrap; not a global Llama result."}
    record["net_ttft_speedup"] = 1.0 / max(1.0 - record["estimate_net_mean_ttft_reduction"], 1e-9)
    record["slo_goodput_multiplier"] = 1.0 + record["estimate_slo_goodput_gain"]
    output.append(record)
    return output


def policy_repeat_slo(rows: list[dict[str, Any]], policy: str, slo_ms: float, accounting: str) -> tuple[float, int, int]:
    selected = future(rows)
    add_exposure(selected)
    verify = verifier_by_session(rows)
    certified_count = sum(row.get("certificate_issued") is True for row in selected)
    verifier_per_request = sum(verify.values()) / max(certified_count, 1)
    compliant = 0
    for row in selected:
        overhead = 0.0
        if accounting == "net-amortized-unhidden-verifier" and policy == "contractkv-full":
            overhead = verifier_per_request
        compliant += float(row["ttft_ms"]) + overhead <= slo_ms
    wall_s = sum(float(row["_exposure_ms"]) for row in selected) / 1000.0
    return compliant / max(wall_s, 1e-9), compliant, len(selected)


def build_slo(args: argparse.Namespace) -> list[dict[str, Any]]:
    output = []
    for model, label in (("qwen", "Qwen3-8B"), ("mistral", "Mistral-7B-Instruct-v0.3")):
        repeat_rows = {}
        for repeat in (1, 2, 3):
            repeat_rows[repeat] = load_repeat_pair(args.submission_root, model, repeat)
        for accounting in ("serving-only", "net-amortized-unhidden-verifier"):
            for slo in SLO_BUCKETS:
                rates: dict[str, list[float]] = {"raw-order": [], "contractkv-full": []}
                counts: dict[str, int] = defaultdict(int)
                requests = 0
                for repeat, (raw, contract) in repeat_rows.items():
                    for policy, rows in (("raw-order", raw), ("contractkv-full", contract)):
                        rate, compliant, current_requests = policy_repeat_slo(rows, policy, slo, accounting)
                        rates[policy].append(rate); counts[policy] += compliant; requests += current_requests if policy == "raw-order" else 0
                raw_mean, contract_mean = statistics.fmean(rates["raw-order"]), statistics.fmean(rates["contractkv-full"])
                output.append({
                    "model": label, "scope": "all held-out workflows", "accounting_mode": accounting,
                    "slo_ms": slo, "requests_per_policy": requests, "fresh_process_repeats": 3,
                    "raw_mean_slo_req_per_sec": raw_mean,
                    "contract_mean_slo_req_per_sec": contract_mean,
                    "contract_min_slo_req_per_sec": min(rates["contractkv-full"]),
                    "contract_max_slo_req_per_sec": max(rates["contractkv-full"]),
                    "multiplicative_gain_vs_raw": contract_mean / raw_mean if raw_mean else "inf",
                    "absolute_gain_vs_raw": contract_mean - raw_mean,
                    "raw_compliant_requests": counts["raw-order"],
                    "contract_compliant_requests": counts["contractkv-full"],
                    "claim_boundary": "Offline SLO re-thresholding of frozen live per-request TTFT and batch-wall records.",
                })
    return output


def build_physical_closure(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = load_csv(args.physical_memory_csv)
    row = next(item for item in rows if int(item["sessions"]) == 20 and int(item["shared_target_tokens"]) == 4096)
    closure = [{
        "model": row["model"], "agents": 20, "fresh_process_repeats": int(row["fresh_process_repeats"]),
        "same_snapshot_logical_refs": float(row["contract_peak_logical_refs"]),
        "same_snapshot_unique_physical_blocks": float(row["contract_peak_concurrent_unique_blocks"]),
        "same_snapshot_reference_blocks_avoided_net_of_raw": float(row["net_concurrent_reference_blocks_avoided"]),
        "same_snapshot_kv_gib_avoided_net_of_raw": float(row["net_concurrent_kv_gib_saved"]),
        "same_snapshot_dedup_factor": float(row["contract_peak_logical_refs"]) / max(float(row["contract_peak_concurrent_unique_blocks"]), 1e-9),
        "raw_peak_used_blocks": float(row["raw_mean_used_block_high_water"]),
        "contract_peak_used_blocks": float(row["contract_mean_used_block_high_water"]),
        "peak_used_blocks_saved": float(row["peak_used_blocks_saved"]),
        "peak_used_block_reduction": float(row["peak_used_blocks_saved"]) / max(float(row["raw_mean_used_block_high_water"]), 1e-9),
        "peak_used_kv_gib_saved": float(row["peak_used_kv_gib_saved"]),
        "raw_minimum_free_blocks": float(row["raw_mean_minimum_free_blocks"]),
        "contract_minimum_free_blocks": float(row["contract_mean_minimum_free_blocks"]),
        "minimum_free_block_multiplier": float(row["contract_mean_minimum_free_blocks"]) / max(float(row["raw_mean_minimum_free_blocks"]), 1e-9),
        "refcount_match_rate": float(row["contract_peak_refcount_match_rate"]),
        "oom_free_concurrency_lower_bound": row["oom_boundary"],
        "claim_boundary": "Same-snapshot dedup and lifecycle peak are distinct; no new-prefill-to-HBM conversion.",
    }]
    histogram: Counter[int] = Counter()
    for raw in load_csv(args.physical_raw_csv):
        if raw.get("policy") != "contractkv-caposc" or int(raw.get("sessions", 0)) != 20 or str(raw.get("primer", "")).lower() == "true":
            continue
        for value in ast.literal_eval(raw.get("physical_block_refcounts", "[]")):
            histogram[int(value)] += 1
    distribution = {
        "source": str(args.physical_raw_csv),
        "scope": "20-agent ContractKV measured request block tables across three fresh cells",
        "refcount_histogram": {str(key): value for key, value in sorted(histogram.items())},
        "claim_boundary": "Histogram counts block-table observations, not unique lifecycle allocations.",
    }
    return closure, distribution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-root", type=Path, required=True)
    parser.add_argument("--llama-root", type=Path, required=True)
    parser.add_argument("--qwen14-repeat-csv", type=Path, required=True)
    parser.add_argument("--physical-memory-csv", type=Path, required=True)
    parser.add_argument("--physical-raw-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--slo-ms", type=float, default=1500)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    invariance = build_repeat_invariance(args)
    bootstrap = build_bootstrap(args)
    slo = build_slo(args)
    physical, refcounts = build_physical_closure(args)
    write_csv(args.output_dir / "repeat_invariance_v0.csv", invariance)
    write_csv(args.output_dir / "session_cluster_bootstrap_v0.csv", bootstrap)
    write_csv(args.output_dir / "slo_sensitivity_v0.csv", slo)
    write_csv(args.output_dir / "physical_accounting_closure_v0.csv", physical)
    (args.output_dir / "physical_refcount_distribution_v0.json").write_text(
        json.dumps(refcounts, indent=2) + "\n", encoding="utf-8")
    summary = {"repeat_invariance": invariance, "cluster_bootstrap": bootstrap,
               "slo_rows": len(slo), "physical_closure": physical, "refcount_distribution": refcounts}
    (args.output_dir / "submission_supplement_summary_v0.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "outputs": 6, "bootstrap_samples": args.bootstrap_samples}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
