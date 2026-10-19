#!/usr/bin/env python3
"""Summarize all four policies in the Phase 26 fused-verifier held-out."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26d_typed_analysis import (
    FAMILY_NAMES, family, load_jsonl, summarize_scope, write_csv,
)


POLICIES = ("raw", "exact", "typed", "contract")


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
    family_ids = {name: {str(row["phase19b_session_id"]) for row in sessions if family(row) == name}
                  for name in FAMILY_NAMES}
    per_repeat: list[dict[str, Any]] = []; quality = []
    for repeat in (1, 2, 3):
        cells = {policy: load_jsonl(args.base / f"r{repeat}-{policy}.jsonl") for policy in POLICIES}
        if any(len(rows) != 500 for rows in cells.values()):
            raise RuntimeError(f"repeat {repeat} incomplete: " +
                               ", ".join(f"{policy}={len(rows)}" for policy, rows in cells.items()))
        raw = cells["raw"]
        for policy in POLICIES:
            row, qrows = summarize_scope(raw, cells[policy], all_ids, repeat, "all",
                                         args.slo_ms, manifest)
            row["policy"] = policy; per_repeat.append(row)
            if policy != "raw":
                quality.extend({**qrow, "policy": policy} for qrow in qrows)
            for name, ids in family_ids.items():
                row, _ = summarize_scope(raw, cells[policy], ids, repeat, name,
                                         args.slo_ms, manifest)
                row["policy"] = policy; per_repeat.append(row)

    aggregate = []
    for policy in POLICIES:
        for scope in ["all", *FAMILY_NAMES]:
            group = [row for row in per_repeat if row["policy"] == policy and row["scope"] == scope]
            record: dict[str, Any] = {"policy": policy, "scope": scope,
                                      "fresh_process_repeats": len(group)}
            for key in group[0]:
                if key in {"policy", "scope", "repeat", "qualified_in_frozen_manifest", "frozen_max_level"}:
                    continue
                values = [row[key] for row in group if isinstance(row.get(key), (int, float))]
                if values:
                    record[key] = statistics.fmean(values)
            if scope in FAMILY_NAMES:
                spec = manifest["family_specs"][scope]
                record["qualified_in_frozen_manifest"] = spec["selected_level"] != "L0"
                record["frozen_max_level"] = spec["selected_level"]
            aggregate.append(record)

    global_row = next(row for row in aggregate if row["policy"] == "contract" and row["scope"] == "all")
    contract_quality = [row for row in quality if row["policy"] == "contract" and row["scope"] == "all"]
    strict_policy_quality_violations = sum(
        bool(row["policy_attributable_quality_violation"]) for row in contract_quality)
    raw_fallback_pair_differences = sum(
        bool(row["raw_fallback_pair_difference"]) for row in contract_quality)
    gates = {
        "completion_100": global_row["completion_rate"] == 1.0,
        "policy_quality_violations_zero": strict_policy_quality_violations == 0,
        "scope_invalid_admissions_zero": global_row["scope_invalid_admissions"] == 0,
        "dynamic_suffix_reuse_zero": global_row["max_dynamic_suffix_reuse_tokens"] == 0,
        "certificate_coverage_ge_50pct": global_row["certificate_session_coverage"] >= .50,
        "new_prefill_reduction_ge_30pct": global_row["new_prefill_reduction"] >= .30,
        "net_mean_ttft_reduction_ge_25pct": global_row["net_mean_ttft_reduction"] >= .25,
    }
    gate = {
        "schema_version": "contractkv.phase26d.fused-heldout-gate.v1",
        "model": "DeepSeek-Coder-V2-Lite-Instruct", "heldout_sessions": len(sessions),
        "future_requests_per_policy_per_repeat": len(sessions) * 9,
        "fresh_process_repeats": 3, "policies": list(POLICIES),
        "qualification_hash": manifest["qualification_hash"], "global_contract": global_row,
        "strict_policy_quality_violation_rows": strict_policy_quality_violations,
        "raw_fallback_cross_process_difference_rows": raw_fallback_pair_differences,
        "gates": gates, "paper_gate_pass": all(gates.values()),
        "claim_boundary": "Fresh vLLM TP=2 sealed held-out after invalidating the v0 cumulative-cost estimator. The fused verifier uses one greedy candidate, a hard deadline, and no benchmark reference online.",
    }
    write_csv(args.base.parent / "heldout_v1_scope_per_repeat.csv", per_repeat)
    write_csv(args.base.parent / "heldout_v1_scope_aggregate.csv", aggregate)
    write_csv(args.base.parent / "heldout_v1_quality_pairs.csv", quality)
    (args.base.parent / "phase26d_fused_heldout_gate_v1.json").write_text(
        json.dumps(gate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
