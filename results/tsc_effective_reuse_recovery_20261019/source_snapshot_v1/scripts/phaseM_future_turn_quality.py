#!/usr/bin/env python3
"""Score Mistral multi-turn cells and apply preregistered development/heldout gates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))]


def average(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) not in {"", None}]
    return statistics.fmean(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=["development", "heldout"], required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--cell", action="append", required=True, help="policy=path")
    parser.add_argument("--protocol-summary", type=Path)
    parser.add_argument("--tool-slack-ms", type=float, default=2000)
    parser.add_argument("--quality-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--slo-output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()
    sessions = {str(row["phase19b_session_id"]): row for row in load(args.sessions)}
    cells = {item.split("=", 1)[0]: load(Path(item.split("=", 1)[1])) for item in args.cell}
    raw_scores: dict[tuple[str, int], float] = {}
    quality_rows: list[dict[str, Any]] = []
    for policy, rows in cells.items():
        for row in rows:
            if row.get("row_type") != "future":
                continue
            sid = str(row.get("session_id")); turn = int(row.get("turn_id", 0))
            sample = sessions[sid]
            score, metric, error = standard_score(
                str(sample.get("dataset")), str(sample.get("task")),
                str(row.get("output_text", "")), sample.get("answer", ""))
            record = {"partition": args.partition, "policy": policy,
                      "session_id": sid, "turn_id": turn,
                      "dataset": sample.get("dataset"), "task": sample.get("task"),
                      "sample_id": sample.get("sample_id"), "metric": metric,
                      "score": score, "scoring_error": error}
            quality_rows.append(record)
            if policy == "raw-order":
                raw_scores[(sid, turn)] = score
    for row in quality_rows:
        raw = raw_scores.get((row["session_id"], row["turn_id"]), row["score"])
        row["raw_score"] = raw
        row["quality_drop_vs_raw"] = max(0.0, raw - float(row["score"]))
        row["quality_violation"] = row["quality_drop_vs_raw"] > .03

    summaries = []
    for policy, rows in cells.items():
        future = [row for row in rows if row.get("row_type") == "future"]
        successful = [row for row in future if row.get("success") is True]
        canary = [row for row in rows if row.get("row_type") == "canary"]
        qrows = [row for row in quality_rows if row["policy"] == policy]
        certified = {str(row["session_id"]) for row in canary if row.get("certificate_issued") is True}
        violations = [row for row in qrows if row["quality_violation"]]
        unsafe = sorted({row["session_id"] for row in violations if row["session_id"] in certified})
        first_violation = {sid: min(row["turn_id"] for row in violations if row["session_id"] == sid)
                           for sid in {row["session_id"] for row in violations}}
        summaries.append({
            "policy": policy, "requests": len(future), "completed_requests": len(successful),
            "completion_rate": len(successful) / max(1, len(future)),
            "mean_ttft_ms": average(successful, "ttft_ms"),
            "p95_ttft_ms": percentile([float(row.get("ttft_ms", 0)) for row in successful], .95),
            "mean_tpot_ms": average(successful, "tpot_ms"),
            "p95_tpot_ms": percentile([float(row.get("tpot_ms", 0)) for row in successful], .95),
            "mean_latency_ms": average(successful, "latency_ms"),
            "mean_prefix_hit_tokens": average(successful, "prefix_hit_tokens"),
            "mean_new_prefill_tokens": average(successful, "new_prefill_tokens"),
            "certificate_count": len(certified),
            "safe_coverage": len(certified) / max(1, len(sessions)) if canary else 0.0,
            "future_quality_violation_rows": len(violations),
            "unsafe_certified_sessions": len(unsafe),
            "unsafe_certified_session_ids": unsafe,
            "first_violation_turns": first_violation,
            "max_quality_drop": max([float(row["quality_drop_vs_raw"]) for row in qrows], default=0.0),
        })
    by_policy = {row["policy"]: row for row in summaries}
    raw = by_policy["raw-order"]
    contract = by_policy["contractkv-full"]
    contract_rows = cells["contractkv-full"]
    canary = [row for row in contract_rows if row.get("row_type") == "canary"]
    cert_future = [row for row in contract_rows if row.get("row_type") == "future"
                   and row.get("certificate_issued") is True
                   and row.get("prefix_hit_tokens") not in {"", None}]
    contract["retained_prefix_gain_vs_raw"] = (
        contract["mean_prefix_hit_tokens"] - raw["mean_prefix_hit_tokens"]) / max(raw["mean_prefix_hit_tokens"], 1.0)
    contract["new_prefill_reduction_vs_raw"] = (
        raw["mean_new_prefill_tokens"] - contract["mean_new_prefill_tokens"]) / max(raw["mean_new_prefill_tokens"], 1.0)
    verifier_per_request = sum(float(row.get("unhidden_verifier_ms", 0) or 0) for row in canary) / max(1, len(cert_future))
    contract["unhidden_verifier_ms_per_request"] = verifier_per_request
    contract["net_mean_ttft_ms"] = contract["mean_ttft_ms"] + verifier_per_request
    contract["net_mean_ttft_reduction_vs_raw"] = (
        raw["mean_ttft_ms"] - contract["net_mean_ttft_ms"]) / max(raw["mean_ttft_ms"], 1.0)
    reuse = []
    for row in cert_future:
        stable = float(row.get("certified_stable_prefix_tokens", 0) or 0)
        if stable > 0:
            reuse.append(min(1.0, float(row.get("prefix_hit_tokens", 0)) / stable))
    contract["certified_stable_prefix_reuse_fraction"] = statistics.fmean(reuse) if reuse else 0.0
    contract["max_dynamic_suffix_reuse_tokens"] = max(
        [int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in cert_future], default=0)

    protocol_bug_count = 0
    if args.protocol_summary and args.protocol_summary.exists():
        protocol_bug_count = int(json.loads(args.protocol_summary.read_text(encoding="utf-8")).get("protocol_bug_count", 0))
    if args.partition == "development":
        gates = {
            "protocol_bugs_zero": protocol_bug_count == 0,
            "completion_100": contract["completion_rate"] == 1.0,
            "certified_future_violations_zero": contract["unsafe_certified_sessions"] == 0,
            "safe_coverage_ge_35pct": contract["safe_coverage"] >= .35,
        }
    else:
        gates = {
            "completion_100": contract["completion_rate"] == 1.0,
            "unsafe_certified_zero": contract["unsafe_certified_sessions"] == 0,
            "certified_future_violations_zero": contract["unsafe_certified_sessions"] == 0,
            "safe_coverage_ge_50pct": contract["safe_coverage"] >= .50,
            "retained_prefix_gain_ge_50pct": contract["retained_prefix_gain_vs_raw"] >= .50,
            "new_prefill_reduction_ge_30pct": contract["new_prefill_reduction_vs_raw"] >= .30,
            "net_mean_ttft_reduction_ge_30pct": contract["net_mean_ttft_reduction_vs_raw"] >= .30,
            "certified_reuse_ge_95pct": contract["certified_stable_prefix_reuse_fraction"] >= .95,
            "dynamic_suffix_reuse_zero": contract["max_dynamic_suffix_reuse_tokens"] == 0,
        }
    gate = {"schema_version": f"mistral.{args.partition}-gate.v1",
            "gates": gates, "gate_pass": all(gates.values()),
            "heldout_threshold_retuning_allowed": False,
            "stop_all_model_experiments_after_extension": args.partition == "heldout"}
    slo_rows = []
    for policy, rows in cells.items():
        future = [row for row in rows if row.get("row_type") == "future" and row.get("success") is True]
        batches: dict[str, float] = {}
        for row in future:
            key = str(row.get("batch_id") or row.get("request_id"))
            batches[key] = max(batches.get(key, 0.0), float(row.get("batch_wall_ms", 0) or 0))
        wall_s = sum(batches.values()) / 1000.0
        for slo in (500, 750, 1000, 1250, 1500, 2000):
            compliant = sum(float(row.get("ttft_ms", 1e18)) <= slo for row in future)
            slo_rows.append({"partition": args.partition, "policy": policy, "slo_ms": slo,
                             "completed": len(future), "slo_compliant": compliant,
                             "slo_compliant_fraction": compliant / max(1, len(future)),
                             "slo_compliant_req_per_sec": compliant / max(wall_s, 1e-9)})

    for path, rows in ((args.quality_output, quality_rows), (args.slo_output, slo_rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            fields = sorted({key for row in rows for key in row})
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    args.summary_output.write_text(json.dumps({"partition": args.partition,
                                               "policies": summaries,
                                               "contractkv": contract}, indent=2) + "\n", encoding="utf-8")
    args.gate_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contractkv": contract, "gate": gate}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
