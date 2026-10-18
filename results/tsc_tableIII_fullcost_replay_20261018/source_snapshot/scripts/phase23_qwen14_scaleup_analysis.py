#!/usr/bin/env python3
"""Summarize paired Qwen3-14B TP=2 raw/ContractKV scale-up cells."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase15d_task_bearing_certified_replay import output_contract


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[max(0, min(len(values) - 1, math.ceil(q * len(values)) - 1))]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def wall_seconds(rows: list[dict[str, Any]]) -> float:
    batches = {str(row.get("batch_id")): f(row.get("batch_wall_ms"))
               for row in rows if row.get("row_type") == "future"}
    return sum(batches.values()) / 1000.0


def summarize_cell(rows: list[dict[str, Any]], slo_ms: float) -> dict[str, Any]:
    future = [row for row in rows if row.get("row_type") == "future"]
    success = [row for row in future if row.get("success") is True]
    canary = [row for row in rows if row.get("row_type") == "canary"]
    certified = [row for row in success if row.get("certificate_issued") is True]
    stable = sum(f(row.get("certified_stable_prefix_tokens")) for row in certified)
    reused = sum(min(f(row.get("prefix_hit_tokens")), f(row.get("certified_stable_prefix_tokens"))) for row in certified)
    unhidden = sum(f(row.get("unhidden_verifier_ms")) for row in canary) / max(1, len(future))
    ttft = [f(row.get("ttft_ms")) for row in success]
    wall = wall_seconds(rows)
    return {
        "future_requests": len(future),
        "completion_rate": len(success) / max(1, len(future)),
        "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, 0.95),
        "mean_tpot_ms": statistics.fmean(f(row.get("tpot_ms")) for row in success) if success else 0.0,
        "mean_latency_ms": statistics.fmean(f(row.get("latency_ms")) for row in success) if success else 0.0,
        "mean_prompt_tokens": statistics.fmean(f(row.get("prompt_tokens")) for row in success) if success else 0.0,
        "mean_prefix_hit_tokens": statistics.fmean(f(row.get("prefix_hit_tokens")) for row in success) if success else 0.0,
        "mean_new_prefill_tokens": statistics.fmean(f(row.get("new_prefill_tokens")) for row in success) if success else 0.0,
        "certificate_coverage": sum(row.get("certificate_issued") is True for row in canary) / max(1, len(canary)) if canary else 0.0,
        "certified_prefix_physical_reuse": reused / max(1.0, stable) if certified else 0.0,
        "mean_reused_physical_blocks": statistics.fmean(f(row.get("reused_physical_blocks")) for row in certified) if certified else 0.0,
        "peak_physical_block_count": max([int(f(row.get("physical_block_count"))) for row in success], default=0),
        "max_dynamic_suffix_reuse_tokens": max([int(f(row.get("dynamic_suffix_reuse_tokens"))) for row in certified], default=0),
        "unhidden_verifier_ms_per_future": unhidden,
        "net_mean_ttft_ms": (statistics.fmean(ttft) if ttft else 0.0) + unhidden,
        "slo_compliant_req_per_sec": sum(value <= slo_ms for value in ttft) / max(0.001, wall),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--pair", action="append", required=True, help="repeat,raw.jsonl,contract.jsonl")
    parser.add_argument("--slo-ms", type=float, default=2000.0)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--repeat-output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--quality-output", type=Path, required=True)
    parser.add_argument("--family-output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()

    sessions = {str(row["phase19b_session_id"]): row for row in load(args.sessions)}
    all_rows: list[dict[str, Any]] = []
    repeat_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    family_accum: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for value in args.pair:
        repeat_s, raw_path_s, contract_path_s = value.split(",", 2)
        repeat = int(repeat_s)
        raw_rows = load(Path(raw_path_s)); contract_rows = load(Path(contract_path_s))
        for row in raw_rows:
            row["repeat"] = repeat
            row["paired_policy"] = "raw-order"
        for row in contract_rows:
            row["repeat"] = repeat
            row["paired_policy"] = "contractkv-full"
        all_rows.extend(raw_rows + contract_rows)
        raw_index = {(str(row["session_id"]), int(row["turn_id"])): row for row in raw_rows
                     if row.get("row_type") == "future"}
        contract_index = {(str(row["session_id"]), int(row["turn_id"])): row for row in contract_rows
                          if row.get("row_type") == "future"}
        for key in sorted(set(raw_index) & set(contract_index)):
            raw = raw_index[key]; contract = contract_index[key]
            sid, turn = key; sample = sessions[sid]
            raw_score = f(raw.get("task_score")); contract_score = f(contract.get("task_score"))
            drop = max(0.0, raw_score - contract_score)
            match, contract_type = output_contract(
                str(sample.get("dataset", "")), str(sample.get("task", "")),
                str(raw.get("output_text", "")), str(contract.get("output_text", "")), "",
            )
            promoted = str(contract.get("effective_policy", "")) != "raw-order"
            quality = {
                "repeat": repeat, "session_id": sid, "turn_id": turn,
                "dataset": sample.get("dataset"), "task": sample.get("task"),
                "raw_score": raw_score, "contract_score": contract_score, "quality_drop": drop,
                "output_contract_match": match, "output_contract_type": contract_type,
                "effective_policy": contract.get("effective_policy", ""),
                "certificate_issued": contract.get("certificate_issued", False),
                "policy_attributable_quality_violation": promoted and drop > 0.03,
                "raw_fallback_pair_difference": not promoted and drop > 0.03,
            }
            quality_rows.append(quality)
            family_accum[(repeat, f"{sample.get('dataset')}:{sample.get('task')}")].append(quality)
        raw_summary = summarize_cell(raw_rows, args.slo_ms)
        contract_summary = summarize_cell(contract_rows, args.slo_ms)
        repeat_rows.append({
            "repeat": repeat, "sessions": len(sessions), "concurrency": 2,
            "raw_completion_rate": raw_summary["completion_rate"],
            "contract_completion_rate": contract_summary["completion_rate"],
            "raw_mean_ttft_ms": raw_summary["mean_ttft_ms"],
            "contract_mean_ttft_ms": contract_summary["mean_ttft_ms"],
            "contract_net_mean_ttft_ms": contract_summary["net_mean_ttft_ms"],
            "raw_p95_ttft_ms": raw_summary["p95_ttft_ms"],
            "contract_p95_ttft_ms": contract_summary["p95_ttft_ms"],
            "raw_mean_tpot_ms": raw_summary["mean_tpot_ms"],
            "contract_mean_tpot_ms": contract_summary["mean_tpot_ms"],
            "raw_mean_new_prefill_tokens": raw_summary["mean_new_prefill_tokens"],
            "contract_mean_new_prefill_tokens": contract_summary["mean_new_prefill_tokens"],
            "new_prefill_reduction_vs_raw": 1 - contract_summary["mean_new_prefill_tokens"] / max(1.0, raw_summary["mean_new_prefill_tokens"]),
            "net_mean_ttft_reduction_vs_raw": 1 - contract_summary["net_mean_ttft_ms"] / max(0.001, raw_summary["mean_ttft_ms"]),
            "p95_ttft_reduction_vs_raw": 1 - contract_summary["p95_ttft_ms"] / max(0.001, raw_summary["p95_ttft_ms"]),
            "certificate_coverage": contract_summary["certificate_coverage"],
            "certified_prefix_physical_reuse": contract_summary["certified_prefix_physical_reuse"],
            "mean_reused_physical_blocks": contract_summary["mean_reused_physical_blocks"],
            "peak_physical_block_count": contract_summary["peak_physical_block_count"],
            "max_dynamic_suffix_reuse_tokens": contract_summary["max_dynamic_suffix_reuse_tokens"],
            "raw_slo_compliant_req_per_sec": raw_summary["slo_compliant_req_per_sec"],
            "contract_slo_compliant_req_per_sec": contract_summary["slo_compliant_req_per_sec"],
            "slo_goodput_gain_vs_raw": contract_summary["slo_compliant_req_per_sec"] / max(0.001, raw_summary["slo_compliant_req_per_sec"]) - 1,
            "policy_attributable_quality_violations": sum(
                row["policy_attributable_quality_violation"] for row in quality_rows if row["repeat"] == repeat
            ),
            "raw_fallback_pair_differences": sum(
                row["raw_fallback_pair_difference"] for row in quality_rows if row["repeat"] == repeat
            ),
        })

    aggregate = {"scope": "aggregate_3_fresh_pairs", "repeats": len(repeat_rows), "sessions_per_repeat": len(sessions)}
    for key in repeat_rows[0]:
        if key in {"repeat", "sessions", "concurrency"}:
            continue
        values = [f(row.get(key)) for row in repeat_rows]
        aggregate[key] = statistics.fmean(values)
        if key in {"raw_mean_ttft_ms", "contract_mean_ttft_ms", "contract_net_mean_ttft_ms",
                   "raw_p95_ttft_ms", "contract_p95_ttft_ms", "new_prefill_reduction_vs_raw",
                   "net_mean_ttft_reduction_vs_raw", "p95_ttft_reduction_vs_raw"}:
            aggregate[f"{key}_min"] = min(values)
            aggregate[f"{key}_max"] = max(values)
    family_rows = []
    for (repeat, fam), rows in sorted(family_accum.items()):
        family_rows.append({
            "repeat": repeat, "family": fam, "future_pairs": len(rows),
            "mean_raw_score": statistics.fmean(row["raw_score"] for row in rows),
            "mean_contract_score": statistics.fmean(row["contract_score"] for row in rows),
            "mean_quality_drop": statistics.fmean(row["quality_drop"] for row in rows),
            "policy_attributable_quality_violations": sum(row["policy_attributable_quality_violation"] for row in rows),
            "raw_fallback_pair_differences": sum(row["raw_fallback_pair_difference"] for row in rows),
            "promoted_fraction": sum(str(row["effective_policy"]) != "raw-order" for row in rows) / max(1, len(rows)),
        })
    gate = {
        "schema_version": "contractkv.qwen3-14b-tp2-scaleup-gate.v1",
        "fresh_pairs": len(repeat_rows),
        "sessions_per_repeat": len(sessions),
        "five_task_families_present": len({f"{row.get('dataset')}:{row.get('task')}" for row in sessions.values()}) == 5,
        "future_requests_per_policy_per_repeat": 9 * len(sessions),
        "all_repeats_complete": all(row["raw_completion_rate"] == 1.0 and row["contract_completion_rate"] == 1.0 for row in repeat_rows),
        "policy_attributable_quality_violations_zero": sum(row["policy_attributable_quality_violation"] for row in quality_rows) == 0,
        "scope_invalid_admissions_zero": all(
            not row.get("certificate_scope_errors") for row in all_rows
            if row.get("row_type") == "future" and row.get("effective_policy") != "raw-order"
        ),
        "certified_prefix_physical_reuse_ge_95pct": all(row["certified_prefix_physical_reuse"] >= 0.95 for row in repeat_rows),
        "dynamic_suffix_reuse_zero": all(row["max_dynamic_suffix_reuse_tokens"] == 0 for row in repeat_rows),
        "claim_boundary": (
            "Three fresh raw/ContractKV process pairs on Qwen3-14B TP=2, concurrency=2. "
            "Task-sanity quality scoring is not full official benchmark scoring."
        ),
    }
    gate["gate_pass"] = all(
        value for key, value in gate.items()
        if key not in {"schema_version", "fresh_pairs", "sessions_per_repeat", "future_requests_per_policy_per_repeat", "claim_boundary", "gate_pass"}
    ) and gate["fresh_pairs"] == 3 and gate["sessions_per_repeat"] in range(20, 31)
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_rows), encoding="utf-8")
    write_csv(args.repeat_output, repeat_rows)
    write_csv(args.aggregate_output, [aggregate])
    write_csv(args.quality_output, quality_rows)
    write_csv(args.family_output, family_rows)
    args.gate_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"aggregate": aggregate, "gate": gate}, indent=2))
    return 0 if gate["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
