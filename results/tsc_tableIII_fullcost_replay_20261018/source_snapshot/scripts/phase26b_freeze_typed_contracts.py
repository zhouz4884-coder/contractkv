#!/usr/bin/env python3
"""Freeze development-only Phase 26 typed contracts and benefit gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import benefit_utility
from scripts.phase26_typed_behavior_contracts import contract_manifest, evaluate_typed_contract
from scripts.phase26a_recoverability_analysis import (
    CALIBRATION_MS_PER_TOKEN, SERVING_FLOOR_MS, load_csv, load_jsonl, mean,
)


def online_pass(row: dict[str, Any], threshold: float) -> bool:
    if row["recoverability_class"] == "exact_pass":
        return True
    if not row.get("raw_complete") or not row.get("candidate_complete"):
        return False
    contract = evaluate_typed_contract(
        str(row["dataset"]), str(row["task"]), str(row.get("raw_output_text", "")),
        str(row.get("candidate_output_text", "")), qa_f1_threshold=threshold)
    return contract.decision == "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--phase25", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--qa-f1-threshold", type=float, default=.8)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    benefit_cfg = protocol["benefit_gate"]
    output = {}
    for model_key in ("chat", "coder"):
        rows = load_jsonl(args.base / model_key / "strict_failure_recoverability_v0.jsonl")
        diagnostics = {(str(row["session_id"]), str(row["level"])): row for row in
                       load_jsonl(args.phase25 / model_key / "certificate_diagnostic_v0.jsonl")}
        heldout = {str(row["scope"]): row for row in
                   load_csv(args.phase25 / model_key / "heldout_scope_aggregate_v0.csv")}
        raw_ttft = {scope: float(row["raw_mean_ttft_ms"]) for scope, row in heldout.items()
                    if scope not in {"all", "qualified_subset"}}
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            diag = diagnostics[(str(row["session_id"]), str(row["level"]))]
            row["stable_prefix_tokens"] = int(row.get("tokenizer_exact_stable_prefix_tokens")
                                              or diag.get("stable_prefix_tokens", 0) or 0)
            groups[(str(row["family"]), str(row["level"]))].append(row)
        family_specs = {}
        for family in sorted({key[0] for key in groups}):
            level_specs = {}
            for level in ("L1", "L2", "L3"):
                current = groups[(family, level)]
                strict = [row for row in current if row["recoverability_class"] != "exact_pass"
                          and row.get("raw_complete") and row.get("candidate_complete")]
                admitted = [row for row in current if online_pass(row, args.qa_f1_threshold)]
                typed = [row for row in admitted if row["recoverability_class"] != "exact_pass"]
                unsafe = sum(float(row.get("quality_drop", 1.0)) > .03 for row in admitted)
                family_raw = raw_ttft.get(family, mean(list(raw_ttft.values())))
                maximum_saving = max(0.0, family_raw - SERVING_FLOOR_MS[model_key])
                p_b = len(typed) / max(1, len(strict))
                verification_cost = mean([float(row.get("candidate_decode_ms", 0.0) or 0.0)
                                          + float((row.get("typed_contract") or {}).get("runtime_ms", 0.0) or 0.0)
                                          for row in strict])
                saved = mean([min(maximum_saving, int(row["stable_prefix_tokens"])
                                  * CALIBRATION_MS_PER_TOKEN[model_key]) for row in strict])
                benefit = benefit_utility(
                    pass_probability=p_b, expected_reuses=int(benefit_cfg["expected_future_reuses"]),
                    saved_ms_per_request=saved, verify_ms=verification_cost,
                    slack_ms=float(benefit_cfg["tool_slack_ms"]),
                )
                exact_count = sum(row["recoverability_class"] == "exact_pass" for row in current)
                tier_b_enabled = unsafe == 0 and bool(benefit["admit"])
                deployable = [row for row in current if row["recoverability_class"] == "exact_pass"
                              or (tier_b_enabled and online_pass(row, args.qa_f1_threshold))]
                level_specs[level] = {
                    "exact_count": exact_count, "typed_count": len(typed),
                    "unsafe_admissions": unsafe, "tier_b_enabled": tier_b_enabled,
                    "benefit_expected_gain_ms": benefit["expected_gain_ms"],
                    "mean_verification_ms": verification_cost,
                    "development_deployable_sessions": sorted({str(row["session_id"]) for row in deployable}),
                    "development_coverage": len(deployable) / len(current),
                }
            eligible = [level for level in ("L1", "L2", "L3")
                        if level_specs[level]["exact_count"] > 0 or level_specs[level]["tier_b_enabled"]]
            maximum = eligible[-1] if eligible else "L0"
            descent = [level for level in ("L3", "L2", "L1")
                       if level in eligible and int(level[1:]) <= int(maximum[1:])]
            session_ids = sorted({str(row["session_id"]) for level in ("L1", "L2", "L3")
                                  for row in groups[(family, level)]})
            recovered = set()
            for session_id in session_ids:
                for level in descent:
                    row = next(row for row in groups[(family, level)] if row["session_id"] == session_id)
                    spec = level_specs[level]
                    if row["recoverability_class"] == "exact_pass" or (
                            spec["tier_b_enabled"] and online_pass(row, args.qa_f1_threshold)):
                        recovered.add(session_id); break
            coverage = len(recovered) / max(1, len(session_ids))
            family_specs[family] = {
                "frozen_max_level": maximum, "eligible_descent_levels": descent,
                "development_session_coverage": coverage,
                "qualified": coverage >= .4,
                "level_specs": level_specs,
            }
        qualified = [family for family, spec in family_specs.items() if spec["qualified"]]
        global_coverage = sum(spec["development_session_coverage"] for spec in family_specs.values()) / len(family_specs)
        gate = len(qualified) >= 3 and global_coverage >= .5
        manifest = {
            "schema_version": "contractkv.phase26.typed-qualification.v1",
            "model_key": model_key, "qa_f1_threshold": args.qa_f1_threshold,
            "quality_epsilon": .03, "family_specs": family_specs,
            "qualified_families": qualified, "development_global_coverage": global_coverage,
            "development_unsafe_admissions": sum(
                level["unsafe_admissions"] for family in family_specs.values()
                for level in family["level_specs"].values()),
            "heldout_opened": False, "heldout_gate_open": gate,
            "benefit_gate": benefit_cfg, "typed_contract_manifest": contract_manifest(),
            "claim_boundary": "Frozen on Phase 25 development plus Phase 26A outputs; references are excluded from runtime contracts.",
        }
        manifest["qualification_hash"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        path = args.base / model_key / "typed_qualification_manifest_v0.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        output[model_key] = {"qualified_families": qualified,
                             "development_global_coverage": global_coverage,
                             "heldout_gate_open": gate,
                             "qualification_hash": manifest["qualification_hash"]}
    summary = {"schema_version": "contractkv.phase26b.freeze-summary.v0", "models": output,
               "heldout_models": [key for key, value in output.items() if value["heldout_gate_open"]]}
    (args.base / "phase26b_freeze_summary_v0.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
