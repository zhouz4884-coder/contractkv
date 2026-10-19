#!/usr/bin/env python3
"""Summarize the sealed Phase 26D typed-contract held-out replay."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


FAMILY_NAMES = {
    "RULER:niah_single_1": "RULER",
    "LongBench:hotpotqa": "HotpotQA",
    "LongBench:narrativeqa": "NarrativeQA",
    "LongBench:qasper": "Qasper",
    "RepoBench:python_v1.1": "RepoBench",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position); high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def family(row: dict[str, Any]) -> str:
    return f"{row.get('dataset', '')}:{row.get('task', '')}"


def future_index(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    return {(str(row["session_id"]), int(row["turn_id"])): row
            for row in rows if row.get("row_type") == "future"}


def wall_seconds(rows: list[dict[str, Any]], extra_ms: float = 0.0) -> float:
    batches: dict[str, float] = {}
    for row in rows:
        key = str(row.get("batch_id") or row.get("request_id"))
        batches[key] = max(batches.get(key, 0.0), number(row.get("batch_wall_ms")))
    return (sum(batches.values()) + extra_ms) / 1000.0


def summarize_scope(raw_rows: list[dict[str, Any]], contract_rows: list[dict[str, Any]],
                    session_ids: set[str], repeat: int, scope: str, slo_ms: float,
                    manifest: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = [row for row in raw_rows if row.get("row_type") == "future"
           and str(row.get("session_id")) in session_ids]
    contract = [row for row in contract_rows if row.get("row_type") == "future"
                and str(row.get("session_id")) in session_ids]
    raw_map = future_index(raw); contract_map = future_index(contract)
    keys = sorted(set(raw_map) & set(contract_map))
    canaries = [row for row in contract_rows if row.get("row_type") == "canary"
                and str(row.get("session_id")) in session_ids]
    canary_map = {str(row["session_id"]): row for row in canaries}
    raw_ok = [raw_map[key] for key in keys if raw_map[key].get("success") is True]
    contract_ok = [contract_map[key] for key in keys if contract_map[key].get("success") is True]
    paired_ok = [key for key in keys if raw_map[key].get("success") is True
                 and contract_map[key].get("success") is True]

    quality_rows = []
    for key in paired_ok:
        raw_row = raw_map[key]; candidate = contract_map[key]
        drop = max(0.0, number(raw_row.get("task_score")) - number(candidate.get("task_score")))
        policy_active = str(candidate.get("effective_level", "L0")) != "L0"
        quality_rows.append({
            "repeat": repeat, "scope": scope, "session_id": key[0], "turn_id": key[1],
            "family": family(candidate), "raw_score": number(raw_row.get("task_score")),
            "contract_score": number(candidate.get("task_score")), "quality_drop": drop,
            "quality_violation": drop > .03,
            "policy_attributable_quality_violation": drop > .03 and policy_active,
            "raw_fallback_pair_difference": drop > .03 and not policy_active,
            "effective_level": candidate.get("effective_level", "L0"),
            "certificate_tier": candidate.get("certificate_tier", "RAW_FALLBACK"),
        })

    raw_ttft = [number(row.get("ttft_ms")) for row in raw_ok]
    observed_ttft = [number(row.get("ttft_ms")) for row in contract_ok]
    net_ttft = [number(row.get("ttft_ms")) + number(row.get("unhidden_verifier_ms_per_future"))
                for row in contract_ok]
    raw_new = sum(number(row.get("new_prefill_tokens")) for row in raw_ok)
    contract_new = sum(number(row.get("new_prefill_tokens")) for row in contract_ok)
    raw_scores = [number(raw_map[key].get("task_score")) for key in paired_ok]
    contract_scores = [number(contract_map[key].get("task_score")) for key in paired_ok]
    active_quality = [row for row in quality_rows if row["effective_level"] != "L0"]
    certified_sessions = {str(row["session_id"]) for row in canaries if row.get("certificate_issued") is True}
    active = [row for row in contract_ok if str(row.get("session_id")) in certified_sessions]
    physical_ratios = [min(1.0, number(row.get("reused_physical_blocks")) /
                               max(1.0, number(row.get("physical_block_count"))))
                       for row in active if row.get("physical_block_count") not in {None, ""}]
    raw_good = sum(value <= slo_ms for value in raw_ttft)
    net_good = sum(value <= slo_ms for value in net_ttft)
    unhidden_total = sum(number(row.get("unhidden_verifier_ms_per_future")) for row in contract_ok)
    raw_wall = wall_seconds(raw_ok); net_wall = wall_seconds(contract_ok, unhidden_total)
    tiers = Counter(str(row.get("certificate_tier", "RAW_FALLBACK")) for row in canaries)
    scope_invalid = sum(
        str(row.get("effective_level", "L0")) != "L0"
        and not bool(canary_map.get(str(row.get("session_id")), {}).get("certificate_issued"))
        for row in contract
    )
    record = {
        "scope": scope, "repeat": repeat, "sessions": len(session_ids),
        "paired_future_requests": len(keys),
        "completion_rate": len(contract_ok) / max(1, len(contract)),
        "raw_completion_rate": len(raw_ok) / max(1, len(raw)),
        "certificate_session_coverage": len(certified_sessions) / max(1, len(session_ids)),
        "exact_session_coverage": tiers["EXACT"] / max(1, len(session_ids)),
        "typed_session_coverage": tiers["TYPED"] / max(1, len(session_ids)),
        "raw_fallback_fraction": tiers["RAW_FALLBACK"] / max(1, len(session_ids)),
        "raw_mean_ttft_ms": statistics.fmean(raw_ttft) if raw_ttft else 0.0,
        "contract_observed_mean_ttft_ms": statistics.fmean(observed_ttft) if observed_ttft else 0.0,
        "contract_net_mean_ttft_ms": statistics.fmean(net_ttft) if net_ttft else 0.0,
        "observed_mean_ttft_reduction": ((statistics.fmean(raw_ttft) - statistics.fmean(observed_ttft)) /
                                           max(1.0, statistics.fmean(raw_ttft))) if raw_ttft and observed_ttft else 0.0,
        "net_mean_ttft_reduction": ((statistics.fmean(raw_ttft) - statistics.fmean(net_ttft)) /
                                     max(1.0, statistics.fmean(raw_ttft))) if raw_ttft and net_ttft else 0.0,
        "raw_p95_ttft_ms": percentile(raw_ttft, .95),
        "contract_net_p95_ttft_ms": percentile(net_ttft, .95),
        "net_p95_ttft_reduction": ((percentile(raw_ttft, .95) - percentile(net_ttft, .95)) /
                                    max(1.0, percentile(raw_ttft, .95))) if raw_ttft and net_ttft else 0.0,
        "raw_mean_tpot_ms": statistics.fmean(number(row.get("tpot_ms")) for row in raw_ok) if raw_ok else 0.0,
        "contract_mean_tpot_ms": statistics.fmean(number(row.get("tpot_ms")) for row in contract_ok) if contract_ok else 0.0,
        "raw_mean_task_score": statistics.fmean(raw_scores) if raw_scores else 0.0,
        "contract_mean_task_score": statistics.fmean(contract_scores) if contract_scores else 0.0,
        "mean_task_score_delta": ((statistics.fmean(contract_scores) - statistics.fmean(raw_scores))
                                  if raw_scores and contract_scores else 0.0),
        "policy_active_paired_requests": len(active_quality),
        "policy_active_mean_task_score_delta": (
            statistics.fmean(row["contract_score"] - row["raw_score"] for row in active_quality)
            if active_quality else 0.0),
        "new_prefill_reduction": (raw_new - contract_new) / max(1.0, raw_new),
        "raw_new_prefill_tokens": raw_new, "contract_new_prefill_tokens": contract_new,
        "raw_slo_goodput_req_s": raw_good / max(1e-9, raw_wall),
        "contract_net_slo_goodput_req_s": net_good / max(1e-9, net_wall),
        "slo_goodput_gain": ((net_good / max(1e-9, net_wall)) - (raw_good / max(1e-9, raw_wall))) /
                            max(1e-9, raw_good / max(1e-9, raw_wall)),
        "policy_attributable_quality_violations": sum(row["policy_attributable_quality_violation"] for row in quality_rows),
        "raw_fallback_pair_differences": sum(row["raw_fallback_pair_difference"] for row in quality_rows),
        "scope_invalid_admissions": scope_invalid,
        "max_dynamic_suffix_reuse_tokens": max(
            [int(number(row.get("dynamic_suffix_reuse_tokens"))) for row in active], default=0),
        "mean_reused_physical_block_fraction": statistics.fmean(physical_ratios) if physical_ratios else 0.0,
        "unhidden_verifier_ms_total": unhidden_total,
        "mean_canary_verification_ms": statistics.fmean(
            number(row.get("verification_ms")) for row in canaries) if canaries else 0.0,
    }
    if scope in FAMILY_NAMES:
        spec = manifest["family_specs"][scope]
        record["qualified_in_frozen_manifest"] = bool(
            spec.get("qualified", spec.get("selected_level", "L0") != "L0"))
        record["frozen_max_level"] = spec.get("frozen_max_level", spec.get("selected_level", "L0"))
    return record, quality_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--slo-ms", type=float, default=1500.0)
    args = parser.parse_args()
    sessions = load_jsonl(args.sessions)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    all_ids = {str(row["phase19b_session_id"]) for row in sessions}
    family_ids = {family_name: {str(row["phase19b_session_id"]) for row in sessions
                                if family(row) == family_name}
                  for family_name in FAMILY_NAMES}
    per_repeat = []; quality = []
    for repeat in (1, 2, 3):
        raw = load_jsonl(args.base / "heldout" / f"r{repeat}-raw.jsonl")
        contract = load_jsonl(args.base / "heldout" / f"r{repeat}-contract.jsonl")
        if len(raw) != 500 or len(contract) != 500:
            raise RuntimeError(f"repeat {repeat} is incomplete: raw={len(raw)} contract={len(contract)}")
        row, qrows = summarize_scope(raw, contract, all_ids, repeat, "all", args.slo_ms, manifest)
        per_repeat.append(row); quality.extend(qrows)
        for family_name, ids in family_ids.items():
            row, _ = summarize_scope(raw, contract, ids, repeat, family_name, args.slo_ms, manifest)
            per_repeat.append(row)

    aggregate = []
    for scope in ["all", *FAMILY_NAMES]:
        group = [row for row in per_repeat if row["scope"] == scope]
        record: dict[str, Any] = {"scope": scope, "fresh_process_repeats": len(group)}
        for key in group[0]:
            if key in {"scope", "repeat", "qualified_in_frozen_manifest", "frozen_max_level"}:
                continue
            values = [row[key] for row in group if isinstance(row.get(key), (int, float))]
            if values:
                record[key] = statistics.fmean(values)
        if scope in FAMILY_NAMES:
            record["qualified_in_frozen_manifest"] = manifest["family_specs"][scope]["qualified"]
            record["frozen_max_level"] = manifest["family_specs"][scope]["frozen_max_level"]
        aggregate.append(record)

    global_row = aggregate[0]
    gates = {
        "completion_100": global_row["completion_rate"] == 1.0,
        "policy_quality_violations_zero": global_row["policy_attributable_quality_violations"] == 0,
        "scope_invalid_admissions_zero": global_row["scope_invalid_admissions"] == 0,
        "dynamic_suffix_reuse_zero": global_row["max_dynamic_suffix_reuse_tokens"] == 0,
        "certificate_coverage_ge_50pct": global_row["certificate_session_coverage"] >= .50,
        "new_prefill_reduction_ge_30pct": global_row["new_prefill_reduction"] >= .30,
        "net_mean_ttft_reduction_ge_25pct": global_row["net_mean_ttft_reduction"] >= .25,
    }
    gate = {
        "schema_version": "contractkv.phase26d.typed-heldout-gate.v1",
        "model": "DeepSeek-Coder-V2-Lite-Instruct", "heldout_sessions": len(sessions),
        "future_requests_per_repeat": len(sessions) * 9, "fresh_process_repeats": 3,
        "qualification_hash": manifest["qualification_hash"], "global": global_row,
        "gates": gates, "paper_gate_pass": all(gates.values()),
        "claim_boundary": "Fresh vLLM TP=2 sealed held-out. Typed contracts are deterministic and reference-free; verifier work beyond tool slack is charged to net TTFT.",
    }
    write_csv(args.base / "heldout_scope_per_repeat_v0.csv", per_repeat)
    write_csv(args.base / "heldout_scope_aggregate_v0.csv", aggregate)
    write_csv(args.base / "heldout_quality_pairs_v0.csv", quality)
    (args.base / "phase26d_heldout_gate_v0.json").write_text(
        json.dumps(gate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
