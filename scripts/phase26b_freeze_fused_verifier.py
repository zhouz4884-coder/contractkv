#!/usr/bin/env python3
"""Freeze a single-pass fused Exact/Typed verifier from development data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_typed_behavior_contracts import contract_manifest, evaluate_typed_contract


CALIBRATION_MS_PER_TOKEN = .105
SERVING_FLOOR_MS = 60.0


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def exact_pass(row: dict[str, Any]) -> bool:
    return row["recoverability_class"] == "exact_pass"


def typed_pass(row: dict[str, Any], threshold: float) -> bool:
    if not row.get("raw_complete") or not row.get("candidate_complete"):
        return False
    decision = evaluate_typed_contract(
        str(row["dataset"]), str(row["task"]), str(row.get("raw_output_text", "")),
        str(row.get("candidate_output_text", "")), qa_f1_threshold=threshold).decision
    return decision == "PASS" and float(row.get("quality_drop", 1.0)) <= .03


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--raw-profile", type=Path, required=True)
    parser.add_argument("--phase25-aggregate", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-options", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--qa-f1-threshold", type=float, default=.8)
    parser.add_argument("--tool-slack-ms", type=float, default=6000.0)
    parser.add_argument("--expected-future-reuses", type=int, default=9)
    args = parser.parse_args()
    audit = load_jsonl(args.audit)
    raw_profile = {str(row["session_id"]): row for row in load_jsonl(args.raw_profile)}
    historical = {str(row["scope"]): row for row in load_csv(args.phase25_aggregate)}
    families = sorted({str(row["family"]) for row in audit})
    options: dict[str, list[dict[str, Any]]] = {}
    flat = []
    for family in families:
        raw_ttft = float(historical[family]["raw_mean_ttft_ms"])
        family_options = [{
            "family": family, "selected_level": "L0", "verifier_policy": "raw",
            "development_coverage": 0.0, "development_admitted": 0,
            "development_unsafe_admissions": 0, "expected_gain_ms": 0.0,
            "expected_saved_ms": 0.0, "effective_cost_ms": 0.0,
            "deadline_ms": args.tool_slack_ms, "positive_benefit": True,
        }]
        for level in ("L1", "L2", "L3"):
            rows = [row for row in audit if row["family"] == family and row["level"] == level]
            for verifier_policy in ("fused_exact", "fused_typed"):
                admitted = []; costs = []; savings = []; unsafe = 0; latencies = []
                for row in rows:
                    exact = exact_pass(row)
                    typed = typed_pass(row, args.qa_f1_threshold)
                    accept = exact or (verifier_policy == "fused_typed" and typed)
                    measured = float(row.get("candidate_decode_ms", 0.0) or 0.0)
                    if measured <= 0:
                        measured = float(raw_profile[str(row["session_id"])].get("latency_ms", 0.0) or 0.0)
                    latencies.append(measured)
                    within_deadline = measured <= args.tool_slack_ms
                    deploy = accept and within_deadline
                    if deploy and float(row.get("quality_drop", 1.0)) > .03:
                        unsafe += 1
                    promotion_ms = raw_ttft if deploy else 0.0
                    costs.append(max(0.0, min(measured, args.tool_slack_ms) + promotion_ms - args.tool_slack_ms))
                    saved_per_request = min(
                        max(0.0, raw_ttft - SERVING_FLOOR_MS),
                        int(row.get("tokenizer_exact_stable_prefix_tokens", 0) or 0)
                        * CALIBRATION_MS_PER_TOKEN)
                    savings.append(saved_per_request * args.expected_future_reuses if deploy else 0.0)
                    admitted.append(deploy)
                record = {
                    "family": family, "selected_level": level, "verifier_policy": verifier_policy,
                    "development_coverage": sum(admitted) / max(1, len(rows)),
                    "development_admitted": sum(admitted),
                    "development_unsafe_admissions": unsafe,
                    "expected_saved_ms": sum(savings), "effective_cost_ms": sum(costs),
                    "expected_gain_ms": sum(savings) - sum(costs),
                    "mean_candidate_decode_ms": statistics.fmean(latencies) if latencies else 0.0,
                    "max_candidate_decode_ms": max(latencies, default=0.0),
                    "deadline_ms": args.tool_slack_ms,
                }
                record["positive_benefit"] = record["expected_gain_ms"] > 0 and unsafe == 0
                family_options.append(record)
        options[family] = family_options; flat.extend(family_options)

    # Global constrained selection is frozen before held-out: choose one safe,
    # positive-benefit option per family, maximize expected gain, and require
    # the preregistered 50% aggregate development coverage and three families.
    feasible = []
    for combination in itertools.product(*(options[family] for family in families)):
        if any(not item["positive_benefit"] for item in combination):
            continue
        coverage = statistics.fmean(float(item["development_coverage"]) for item in combination)
        qualified = sum(item["selected_level"] != "L0" for item in combination)
        if coverage >= .50 and qualified >= 3:
            feasible.append((sum(float(item["expected_gain_ms"]) for item in combination), combination))
    if not feasible:
        raise RuntimeError("no safe positive-benefit development policy reaches the frozen global gate")
    _, selected_tuple = max(feasible, key=lambda item: item[0])
    selected = {item["family"]: dict(item) for item in selected_tuple}
    manifest = {
        "schema_version": "contractkv.phase26.fused-typed-qualification.v1",
        "model_key": "coder", "verifier": "single_candidate_free_decode",
        "exact_rule": "candidate token_ids and terminal_stop_token_id equal raw",
        "typed_rule": "when exact differs, evaluate frozen deterministic typed contract",
        "qa_f1_threshold": args.qa_f1_threshold, "quality_epsilon": .03,
        "tool_slack_ms": args.tool_slack_ms, "verification_deadline_ms": args.tool_slack_ms,
        "expected_future_reuses": args.expected_future_reuses,
        "family_specs": selected,
        "qualified_families": [family for family, spec in selected.items() if spec["selected_level"] != "L0"],
        "development_global_coverage": statistics.fmean(
            float(spec["development_coverage"]) for spec in selected.values()),
        "development_expected_gain_ms": sum(float(spec["expected_gain_ms"]) for spec in selected.values()),
        "heldout_opened": False,
        "benefit_gate": "positive expected amortized gain after hard verifier deadline",
        "typed_contract_manifest": contract_manifest(),
        "fallback": "single-attempt timeout/fail/unknown -> L0 raw order",
        "claim_boundary": "Development-only fused-verifier selection; no Phase 26 v0 held-out values enter the optimizer.",
    }
    manifest["qualification_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_csv(args.output_options, flat)
    summary = {
        "schema_version": "contractkv.phase26b.fused-freeze-summary.v1",
        "selected": selected, "qualified_families": manifest["qualified_families"],
        "development_global_coverage": manifest["development_global_coverage"],
        "development_expected_gain_ms": manifest["development_expected_gain_ms"],
        "heldout_gate_open": True, "qualification_hash": manifest["qualification_hash"],
    }
    args.output_summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
