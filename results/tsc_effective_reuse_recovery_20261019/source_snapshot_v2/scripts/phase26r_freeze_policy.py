#!/usr/bin/env python3
"""Freeze a safety-first observation-scoped Phase 26R policy."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26r_policy import wilson_lower, wilson_upper
from scripts.phase26r_typed_contracts import contract_manifest


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-quality", type=Path, required=True)
    parser.add_argument("--turn0-audit", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--options-output", type=Path, required=True)
    parser.add_argument("--unsafe-rate-epsilon", type=float, default=.03)
    parser.add_argument("--minimum-future-observations", type=int, default=45)
    parser.add_argument("--minimum-typed-admissions", type=int, default=125)
    parser.add_argument("--prefill-ms-per-token", type=float, default=.105)
    parser.add_argument("--decode-ms-per-token", type=float, default=12.0)
    parser.add_argument("--promotion-ms-estimate", type=float, default=70.0)
    parser.add_argument("--tool-slack-ms", type=float, default=6000.0)
    parser.add_argument("--minimum-candidate-margin", type=float, default=1.0)
    parser.add_argument("--maximum-margin-degradation", type=float, default=1.0)
    parser.add_argument("--minimum-terminal-stop-margin", type=float, default=1.0)
    args = parser.parse_args()

    quality = read_csv(args.development_quality)
    audit = read_jsonl(args.turn0_audit)
    budgets = json.loads(args.budgets.read_text(encoding="utf-8"))["budgets"]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in quality:
        grouped[(str(row["family"]), str(row["level"]))].append(row)

    options: list[dict[str, Any]] = []
    family_specs: dict[str, dict[str, Any]] = {}
    families = sorted({str(row["family"]) for row in audit})
    for family in families:
        family_options = []
        for level in ("L1", "L2", "L3"):
            rows = grouped[(family, level)]
            failures = sum(str(row.get("policy_attributable_quality_violation", "")).lower() == "true"
                           for row in rows)
            upper = wilson_upper(failures, len(rows))
            record = {
                "family": family,
                "level": level,
                "future_observations": len(rows),
                "future_quality_violations": failures,
                "unsafe_rate_wilson95_upper": upper,
                "population_layout_qualified": (
                    len(rows) >= args.minimum_future_observations
                    and upper < args.unsafe_rate_epsilon
                ),
            }
            family_options.append(record)
            options.append(record)

        audit_rows = [row for row in audit if str(row["family"]) == family]
        typed_nonexact = [row for row in audit_rows
                          if row.get("recoverability_class") == "exact_path_false_negative"]
        typed_unsafe = [row for row in audit_rows
                        if row.get("typed_contract", {}).get("decision") == "PASS"
                        and float(row.get("quality_drop", 1.0)) > .03]
        typed_trials = len(typed_nonexact) + len(typed_unsafe)
        typed_successes = len(typed_nonexact)
        typed_lcb = wilson_lower(typed_successes, typed_trials)
        deterministic_family = family == "RULER:niah_single_1" or family == "RepoBench:python_v1.1"
        typed_evidence_ok = (
            deterministic_family
            and typed_trials >= args.minimum_typed_admissions
            and wilson_upper(len(typed_unsafe), typed_trials) < args.unsafe_rate_epsilon
        )
        # Exact is checked for each observation, so it may probe L3 without a
        # population safety assumption. Tier-B cannot inherit that privilege.
        family_specs[family] = {
            "exact_probe_level": "L3",
            "certificate_scope": "observation",
            "typed_contract_enabled": typed_evidence_ok,
            "typed_disable_reason": "" if typed_evidence_ok else (
                "open_qa_not_deterministic" if not deterministic_family
                else "insufficient_confidence_bounded_admissions"
            ),
            "typed_development_admissions": typed_trials,
            "typed_development_unsafe": len(typed_unsafe),
            "typed_pass_probability_lcb": typed_lcb if typed_evidence_ok else 0.0,
            "future_quality_options": family_options,
            "candidate_budget_tokens": int(budgets[family]),
        }

    manifest = {
        "schema_version": "contractkv.phase26r.observation-policy.v1",
        "model_key": "deepseek-coder-v2-lite-instruct",
        "certificate_scope": "observation_identity+observation_epoch",
        "exact_pipeline": "raw_attestation_then_compact_teacher_forced; free_decode_only_on_exact_fail",
        "exact_robustness_thresholds": {
            "minimum_candidate_margin_q05": args.minimum_candidate_margin,
            "maximum_degradation_q95": args.maximum_margin_degradation,
            "minimum_terminal_stop_margin": args.minimum_terminal_stop_margin,
            "calibration_rule": "development-frozen answer q05>=1, degradation_q95<=1, terminal stop margin>=1, and zero observed task-quality violations",
        },
        "family_specs": family_specs,
        "quality_epsilon": .03,
        "unsafe_rate_epsilon": args.unsafe_rate_epsilon,
        "minimum_future_observations": args.minimum_future_observations,
        "minimum_typed_admissions": args.minimum_typed_admissions,
        "global_coverage_constraint": None,
        "selection_objective": "safety_first; no coverage quota",
        "economics": {
            "prefill_ms_per_token": args.prefill_ms_per_token,
            "decode_ms_per_token": args.decode_ms_per_token,
            "promotion_ms_estimate": args.promotion_ms_estimate,
            "tool_slack_ms": args.tool_slack_ms,
            "observation_scoped_expected_reuses": 1,
        },
        "typed_contract_manifest": contract_manifest(),
        "fallback": "any incomplete, unknown, stale scope, low confidence, or nonpositive gain -> raw L0",
        "heldout_opened": False,
        "claim_boundary": "No development task label is consumed by the live request gate.",
    }
    manifest["qualification_hash"] = canonical_hash(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    fields = list(options[0])
    args.options_output.parent.mkdir(parents=True, exist_ok=True)
    with args.options_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(options)
    print(json.dumps({
        "qualification_hash": manifest["qualification_hash"],
        "typed_enabled_families": [key for key, value in family_specs.items()
                                   if value["typed_contract_enabled"]],
        "all_exact_probe_level": "L3",
        "global_coverage_constraint": None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
