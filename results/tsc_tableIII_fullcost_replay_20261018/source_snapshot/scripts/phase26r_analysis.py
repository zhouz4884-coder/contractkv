#!/usr/bin/env python3
"""Aggregate Phase 26R observation-scoped fresh-process results."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
import sys
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import percentile


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def numeric(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) not in {"", None}]


def family(row: dict[str, Any]) -> str:
    return f"{row['dataset']}:{row['task']}"


def summarize(rows: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw_ttft = numeric(raw_rows, "ttft_ms")
    ttft = numeric(rows, "ttft_ms")
    net = numeric(rows, "net_ttft_ms")
    raw_new = sum(numeric(raw_rows, "new_prefill_tokens"))
    new = sum(numeric(rows, "new_prefill_tokens"))
    denominator = max(1.0, raw_new)
    prep = numeric(rows, "preparation_ms")
    unhidden = numeric(rows, "unhidden_verifier_ms")
    attempts = [attempt for row in rows for attempt in row.get("attempts", [])]
    exact_attempts = [attempt for attempt in attempts
                      if attempt.get("stage") == "tier_e_compact_teacher_forced"]
    gate_attempts = [attempt for attempt in attempts
                     if attempt.get("stage") == "tier_b_session_gate"]
    admission_attempts = [attempt for attempt in attempts
                          if attempt.get("stage") == "observation_verification_admission"]
    stop_margins = numeric(exact_attempts, "terminal_stop_margin")
    return {
        "requests": len(rows),
        "completed_requests": sum(bool(row.get("success")) for row in rows),
        "completion_rate": sum(bool(row.get("success")) for row in rows) / max(1, len(rows)),
        "observation_certificate_coverage": sum(row.get("effective_level") != "L0" for row in rows) / max(1, len(rows)),
        "exact_coverage": sum(row.get("certificate_tier") == "EXACT" for row in rows) / max(1, len(rows)),
        "typed_coverage": sum(row.get("certificate_tier") == "TYPED" for row in rows) / max(1, len(rows)),
        "mean_ttft_ms": mean(ttft),
        "p95_ttft_ms": percentile(ttft, .95),
        "mean_net_ttft_ms": mean(net),
        "p95_net_ttft_ms": percentile(net, .95),
        "raw_mean_ttft_ms": mean(raw_ttft),
        "raw_p95_ttft_ms": percentile(raw_ttft, .95),
        "net_mean_ttft_reduction": (mean(raw_ttft) - mean(net)) / max(1.0, mean(raw_ttft)),
        "net_p95_ttft_reduction": (percentile(raw_ttft, .95) - percentile(net, .95)) / max(1.0, percentile(raw_ttft, .95)),
        "new_prefill_reduction": (raw_new - new) / denominator,
        "mean_preparation_ms": mean(prep),
        "mean_unhidden_verifier_ms": mean(unhidden),
        "p95_unhidden_verifier_ms": percentile(unhidden, .95),
        "raw_attestation_count": sum(
            any(attempt.get("stage") == "tier_e_compact_teacher_forced"
                for attempt in row.get("attempts", [])) for row in rows),
        "exact_attempt_count": len(exact_attempts),
        "exact_pass_count": sum(bool(attempt.get("certificate_issued"))
                                for attempt in exact_attempts),
        "mean_terminal_stop_margin": mean(stop_margins),
        "p05_terminal_stop_margin": percentile(stop_margins, .05),
        "minimum_terminal_stop_margin": min(stop_margins, default=0.0),
        "tier_b_gate_count": len(gate_attempts),
        "tier_b_gate_admitted_count": sum(
            attempt.get("decision") == "PASS" for attempt in gate_attempts),
        "typed_free_decode_count": sum("contract" in attempt for attempt in gate_attempts),
        "verification_admission_count": len(admission_attempts),
        "verification_admitted_count": sum(
            attempt.get("decision") == "PASS" for attempt in admission_attempts),
        "policy_quality_violations": sum(bool(row.get("policy_quality_violation")) for row in rows),
        "scope_invalid_rows": sum(
            row.get("certificate_scope") != "observation"
            or int(row.get("observation_epoch", -1)) != int(row.get("turn_id", -2))
            for row in rows),
        "dynamic_suffix_reuse_max": max(numeric(rows, "dynamic_suffix_reuse_tokens"), default=0.0),
        "physical_reuse_fraction": (
            sum(numeric(rows, "reused_physical_blocks"))
            / max(1.0, sum(numeric(rows, "physical_block_count")))
        ),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(key for key in row if key not in fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--per-family", type=Path, required=True)
    parser.add_argument("--failure-taxonomy", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()

    cells: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for repeat in (1, 2, 3):
        for mode in ("raw", "exact", "contract"):
            path = args.input_dir / f"r{repeat}-{mode}.jsonl"
            rows = read_jsonl(path)
            if len(rows) != 500:
                raise RuntimeError(f"incomplete cell {path}: {len(rows)}/500")
            cells[(repeat, mode)] = rows

    summary_rows = []
    family_rows = []
    for repeat in (1, 2, 3):
        raw = cells[(repeat, "raw")]
        for mode in ("raw", "exact", "contract"):
            row = {"repeat": repeat, "mode": mode, **summarize(cells[(repeat, mode)], raw)}
            summary_rows.append(row)
            for key in sorted({family(item) for item in raw}):
                selected = [item for item in cells[(repeat, mode)] if family(item) == key]
                raw_family = [item for item in raw if family(item) == key]
                family_rows.append({"repeat": repeat, "mode": mode, "family": key,
                                    **summarize(selected, raw_family)})

    for mode in ("raw", "exact", "contract"):
        aggregate = [item for repeat in (1, 2, 3) for item in cells[(repeat, mode)]]
        raw = [item for repeat in (1, 2, 3) for item in cells[(repeat, "raw")]]
        summary_rows.append({"repeat": "aggregate", "mode": mode,
                             **summarize(aggregate, raw)})
        for key in sorted({family(item) for item in raw}):
            selected = [item for item in aggregate if family(item) == key]
            raw_family = [item for item in raw if family(item) == key]
            family_rows.append({"repeat": "aggregate", "mode": mode, "family": key,
                                **summarize(selected, raw_family)})

    failures = []
    for mode in ("exact", "contract"):
        rows = [item for repeat in (1, 2, 3) for item in cells[(repeat, mode)]]
        counter: Counter[tuple[str, str, str]] = Counter()
        for row in rows:
            for attempt in row.get("attempts", []):
                decision = str(attempt.get("decision", ""))
                if decision in {"PASS", "COMMITTED"} or attempt.get("certificate_issued"):
                    continue
                counter[(family(row), str(attempt.get("stage", "")),
                         str(attempt.get("failure_reason") or attempt.get("typed_disable_reason") or decision))] += 1
        failures.extend({"mode": mode, "family": key[0], "stage": key[1],
                         "reason": key[2], "count": count}
                        for key, count in sorted(counter.items()))

    write_csv(args.summary, summary_rows)
    write_csv(args.per_family, family_rows)
    write_csv(args.failure_taxonomy, failures or [{"mode": "none", "family": "none",
                                                   "stage": "none", "reason": "none", "count": 0}])
    aggregate = {row["mode"]: row for row in summary_rows if row["repeat"] == "aggregate"}
    contract = aggregate["contract"]
    exact = aggregate["exact"]
    contract_families = {
        row["family"]: row for row in family_rows
        if row["repeat"] == "aggregate" and row["mode"] == "contract"
    }
    ruler = contract_families.get("RULER:niah_single_1", {})
    gate = {
        "schema_version": "contractkv.phase26s.heldout-gate.v2",
        "cells_complete": True,
        "requests_per_policy": 1500,
        "completion_100_percent": contract["completion_rate"] == 1.0,
        "policy_quality_violations_zero": contract["policy_quality_violations"] == 0,
        "scope_invalid_zero": contract["scope_invalid_rows"] == 0,
        "dynamic_suffix_reuse_zero": contract["dynamic_suffix_reuse_max"] == 0,
        "net_mean_ttft_reduction": contract["net_mean_ttft_reduction"],
        "new_prefill_reduction": contract["new_prefill_reduction"],
        "observation_certificate_coverage": contract["observation_certificate_coverage"],
        "typed_coverage": contract["typed_coverage"],
        "exact_pass_count": contract["exact_pass_count"],
        "tier_b_gate_admitted_count": contract["tier_b_gate_admitted_count"],
        "minimum_terminal_stop_margin": contract["minimum_terminal_stop_margin"],
        "exact_diagnostic": {
            "requests": exact["requests"],
            "certificate_coverage": exact["observation_certificate_coverage"],
            "new_prefill_reduction": exact["new_prefill_reduction"],
            "net_mean_ttft_reduction": exact["net_mean_ttft_reduction"],
            "policy_quality_violations": exact["policy_quality_violations"],
        },
        "ruler_qualified_scope": {
            "certificate_coverage": ruler.get("observation_certificate_coverage", 0.0),
            "new_prefill_reduction": ruler.get("new_prefill_reduction", 0.0),
            "net_mean_ttft_reduction": ruler.get("net_mean_ttft_reduction", 0.0),
            "policy_quality_violations": ruler.get("policy_quality_violations", 0),
        },
        "safety_gate_pass": all([
            contract["completion_rate"] == 1.0,
            contract["policy_quality_violations"] == 0,
            contract["scope_invalid_rows"] == 0,
            contract["dynamic_suffix_reuse_max"] == 0,
        ]),
        "broad_performance_gate_pass": (
            contract["net_mean_ttft_reduction"] >= .25
            and contract["new_prefill_reduction"] >= .30
            and contract["observation_certificate_coverage"] >= .50
        ),
        "bounded_deployment_gate_pass": all([
            contract["completion_rate"] == 1.0,
            contract["policy_quality_violations"] == 0,
            contract["scope_invalid_rows"] == 0,
            contract["dynamic_suffix_reuse_max"] == 0,
            contract["net_mean_ttft_reduction"] > 0,
            contract["new_prefill_reduction"] > 0,
        ]),
        "claim_boundary": "Fresh live vLLM observation-scoped evaluation; no lexical-F1 safety PASS and no future-turn certificate reuse.",
    }
    args.gate.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
