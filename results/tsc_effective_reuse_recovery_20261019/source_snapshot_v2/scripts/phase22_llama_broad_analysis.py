#!/usr/bin/env python3
"""Freeze development qualification and summarize sealed Llama heldout replay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_layout_ladder import family_key


LEVELS = ("L0", "L1", "L2", "L3")
EXPECTED_FAMILIES = {
    "RULER:niah_single_1", "LongBench:hotpotqa", "LongBench:narrativeqa",
    "LongBench:qasper", "RepoBench:python_v1.1",
}


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) not in {"", None}]
    return statistics.fmean(values) if values else 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def parse_cells(values: list[str]) -> dict[str, list[dict[str, Any]]]:
    return {value.split("=", 1)[0]: load(Path(value.split("=", 1)[1])) for value in values}


def score_pairs(sessions: dict[str, dict[str, Any]], raw_rows: list[dict[str, Any]],
                candidate_rows: list[dict[str, Any]], label: str, repeat: int = 0) -> list[dict[str, Any]]:
    raw = {(str(row["session_id"]), int(row["turn_id"])): row for row in raw_rows
           if row.get("row_type") == "future"}
    candidate = {(str(row["session_id"]), int(row["turn_id"])): row for row in candidate_rows
                 if row.get("row_type") == "future"}
    result = []
    for key in sorted(raw.keys() & candidate.keys()):
        sid, turn = key; sample = sessions[sid]
        raw_score, metric, source = standard_score(
            str(sample.get("dataset")), str(sample.get("task")),
            str(raw[key].get("output_text", "")), sample.get("answer", ""))
        candidate_score, _, _ = standard_score(
            str(sample.get("dataset")), str(sample.get("task")),
            str(candidate[key].get("output_text", "")), sample.get("answer", ""))
        drop = max(0.0, raw_score - candidate_score)
        effective_level = str(candidate[key].get("effective_level", "L0"))
        result.append({
            "repeat": repeat, "level": label, "session_id": sid, "turn_id": turn,
            "family": family_key(sample), "dataset": sample.get("dataset"), "task": sample.get("task"),
            "sample_id": sample.get("sample_id"), "raw_score": raw_score,
            "candidate_score": candidate_score, "quality_drop": drop,
            "quality_violation": drop > 0.03,
            "policy_attributable_quality_violation": drop > 0.03 and effective_level != "L0",
            "raw_fallback_pair_difference": drop > 0.03 and effective_level == "L0",
            "metric": metric, "metric_source": source, "effective_level": effective_level,
        })
    return result


def freeze(args: argparse.Namespace) -> int:
    sessions_list = load(args.sessions)
    sessions = {str(row["phase19b_session_id"]): row for row in sessions_list}
    cells = parse_cells(args.cell)
    if set(cells) != set(LEVELS):
        raise RuntimeError(f"development requires exactly {LEVELS}, got {sorted(cells)}")
    if {family_key(row) for row in sessions_list} != EXPECTED_FAMILIES:
        raise RuntimeError("development does not contain the frozen five-family scope")
    quality_rows = []
    for level in LEVELS[1:]:
        quality_rows.extend(score_pairs(sessions, cells["L0"], cells[level], level))

    decisions = []
    for family in sorted(EXPECTED_FAMILIES):
        family_sessions = {sid for sid, sample in sessions.items() if family_key(sample) == family}
        raw_future = [row for row in cells["L0"] if row.get("row_type") == "future"
                      and str(row.get("session_id")) in family_sessions]
        for level in LEVELS[1:]:
            rows = [row for row in cells[level] if str(row.get("session_id")) in family_sessions]
            canary = [row for row in rows if row.get("row_type") == "canary"]
            future = [row for row in rows if row.get("row_type") == "future"]
            qrows = [row for row in quality_rows if row["family"] == family and row["level"] == level]
            certified = {str(row["session_id"]) for row in canary if row.get("certificate_issued") is True}
            cert_future = [row for row in future if row.get("effective_level") != "L0"]
            prefix_gain = mean(future, "prefix_hit_tokens") - mean(raw_future, "prefix_hit_tokens")
            raw_new = mean(raw_future, "new_prefill_tokens")
            candidate_new = mean(future, "new_prefill_tokens")
            reuse = [min(1.0, float(row.get("prefix_hit_tokens", 0)) /
                         max(1.0, float(row.get("certified_stable_prefix_tokens", 0))))
                     for row in cert_future if row.get("prefix_hit_tokens") not in {"", None}]
            scope_invalid = sum(row.get("effective_level") != "L0" and
                                row.get("certificate_scope_valid") is not True for row in future)
            length_unsafe = sum(bool(row.get("length_stop")) and row.get("certificate_issued") is True
                                for row in canary)
            first = min((int(row["turn_id"]) for row in qrows if row["quality_violation"]), default=None)
            record = {
                "family": family, "level": level, "development_sessions": len(family_sessions),
                "future_requests": len(future),
                "completion_rate": sum(row.get("success") is True for row in future) / max(1, len(future)),
                "turn0_verifier_evaluated": len(canary),
                "turn0_verifier_pass_rate": len(certified) / max(1, len(family_sessions)),
                "admitted_session_coverage": len(certified) / max(1, len(family_sessions)),
                "future_quality_violations": sum(row["quality_violation"] for row in qrows),
                "policy_attributable_quality_violations": sum(
                    row["policy_attributable_quality_violation"] for row in qrows),
                "raw_fallback_pair_differences": sum(row["raw_fallback_pair_difference"] for row in qrows),
                "scope_invalid_admissions": scope_invalid,
                "length_stop_unsafe_admissions": length_unsafe,
                "retained_prefix_gain_tokens": prefix_gain,
                "new_prefill_reduction": (raw_new - candidate_new) / max(1.0, raw_new),
                "certified_prefix_reuse": statistics.fmean(reuse) if reuse else 0.0,
                "max_dynamic_suffix_reuse_tokens": max(
                    [int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in cert_future], default=0),
                "first_violating_turn": first if first is not None else "",
            }
            record["eligible"] = (
                record["development_sessions"] >= args.minimum_development_sessions
                and record["completion_rate"] == 1.0
                and record["turn0_verifier_evaluated"] == record["development_sessions"]
                and record["admitted_session_coverage"] >= args.minimum_admitted_coverage
                and record["policy_attributable_quality_violations"] == 0
                and record["scope_invalid_admissions"] == 0
                and record["length_stop_unsafe_admissions"] == 0
                and record["retained_prefix_gain_tokens"] > 0
                and record["certified_prefix_reuse"] >= 0.95
                and record["max_dynamic_suffix_reuse_tokens"] == 0
            )
            decisions.append(record)

    frozen_levels = {}
    family_eligible_levels = {}
    for family in sorted(EXPECTED_FAMILIES):
        eligible = [row for row in decisions if row["family"] == family and row["eligible"]]
        family_eligible_levels[family] = [row["level"] for row in eligible]
        selected = max(eligible, key=lambda row: (row["retained_prefix_gain_tokens"],
                                                  -LEVELS.index(row["level"]))) if eligible else None
        frozen_levels[family] = selected["level"] if selected else "L0"
    manifest = {
        "schema_version": "contractkv.llama-broad-qualification.v1",
        "model_identity": args.model_identity,
        "layout_ladder": args.layout_ladder,
        "selection_rule": "highest retained prefix gain among layouts passing every preregistered gate",
        "minimum_development_sessions": args.minimum_development_sessions,
        "minimum_admitted_coverage": args.minimum_admitted_coverage,
        "quality_drop_threshold": 0.03, "max_tokens": args.max_tokens,
        "stable_word_limit": args.stable_word_limit, "turns": 10,
        "stable_pieces": args.stable_pieces,
        "development_source_sha256": hashlib.sha256(args.sessions.read_bytes()).hexdigest(),
        "split_commitment_sha256": (
            hashlib.sha256(args.split_commitment.read_bytes()).hexdigest()
            if args.split_commitment else ""
        ),
        "heldout_opened_for_tuning": False,
        "frozen_family_levels": frozen_levels,
        "family_eligible_levels": family_eligible_levels,
        "qualified_families": [family for family, level in frozen_levels.items() if level != "L0"],
        "fallback": "certificate_guided_level_descent_then_L0_raw_order",
        "claim_boundary": "Uniform task-agnostic ladder; heldout cannot modify levels, thresholds, output budget, or family decisions.",
    }
    manifest["qualification_hash"] = canonical_hash(manifest)
    write_csv(args.development_summary, decisions)
    write_csv(args.quality_output, quality_rows)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"frozen_family_levels": frozen_levels,
                      "qualified_families": manifest["qualified_families"],
                      "qualification_hash": manifest["qualification_hash"]}, indent=2))
    return 0


def wall_seconds(rows: list[dict[str, Any]]) -> float:
    batches: dict[str, float] = {}
    for row in rows:
        key = str(row.get("batch_id") or row.get("request_id"))
        batches[key] = max(batches.get(key, 0.0), float(row.get("batch_wall_ms", 0) or 0))
    return sum(batches.values()) / 1000.0


def scope_summary(raw_rows: list[dict[str, Any]], contract_rows: list[dict[str, Any]],
                  qrows: list[dict[str, Any]], session_ids: set[str], scope: str,
                  repeat: int, slo_ms: float) -> dict[str, Any]:
    raw = [row for row in raw_rows if row.get("row_type") == "future" and str(row.get("session_id")) in session_ids]
    contract = [row for row in contract_rows if row.get("row_type") == "future" and str(row.get("session_id")) in session_ids]
    successful_raw = [row for row in raw if row.get("success") is True]
    successful = [row for row in contract if row.get("success") is True]
    canary = [row for row in contract_rows if row.get("row_type") == "canary" and str(row.get("session_id")) in session_ids]
    raw_ttft = mean(successful_raw, "ttft_ms"); contract_ttft = mean(successful, "ttft_ms")
    raw_new = mean(successful_raw, "new_prefill_tokens"); contract_new = mean(successful, "new_prefill_tokens")
    certified = {str(row["session_id"]) for row in canary if row.get("certificate_issued") is True}
    cert_future = [row for row in successful if row.get("effective_level") != "L0"]
    reuse = [min(1.0, float(row.get("prefix_hit_tokens", 0)) /
                 max(1.0, float(row.get("certified_stable_prefix_tokens", 0))))
             for row in cert_future if row.get("prefix_hit_tokens") not in {"", None}]
    raw_goodput = sum(float(row.get("ttft_ms", 1e18)) <= slo_ms for row in successful_raw) / max(1e-9, wall_seconds(successful_raw))
    contract_goodput = sum(float(row.get("ttft_ms", 1e18)) <= slo_ms for row in successful) / max(1e-9, wall_seconds(successful))
    return {
        "scope": scope, "repeat": repeat, "sessions": len(session_ids), "future_requests": len(contract),
        "completion_rate": len(successful) / max(1, len(contract)),
        "raw_mean_ttft_ms": raw_ttft, "contract_mean_ttft_ms": contract_ttft,
        "net_mean_ttft_reduction": (raw_ttft - contract_ttft) / max(1.0, raw_ttft),
        "raw_p95_ttft_ms": percentile([float(row.get("ttft_ms", 0)) for row in successful_raw], .95),
        "contract_p95_ttft_ms": percentile([float(row.get("ttft_ms", 0)) for row in successful], .95),
        "p95_ttft_reduction": (percentile([float(row.get("ttft_ms", 0)) for row in successful_raw], .95)
                                - percentile([float(row.get("ttft_ms", 0)) for row in successful], .95)) /
                               max(1.0, percentile([float(row.get("ttft_ms", 0)) for row in successful_raw], .95)),
        "raw_mean_new_prefill_tokens": raw_new, "contract_mean_new_prefill_tokens": contract_new,
        "new_prefill_reduction": (raw_new - contract_new) / max(1.0, raw_new),
        "raw_slo_goodput": raw_goodput, "contract_slo_goodput": contract_goodput,
        "slo_goodput_gain": (contract_goodput - raw_goodput) / max(1e-9, raw_goodput),
        "quality_violations": sum(row["quality_violation"] for row in qrows if row["session_id"] in session_ids),
        "policy_attributable_quality_violations": sum(
            row["policy_attributable_quality_violation"] for row in qrows if row["session_id"] in session_ids),
        "raw_fallback_pair_differences": sum(
            row["raw_fallback_pair_difference"] for row in qrows if row["session_id"] in session_ids),
        "scope_invalid_admissions": sum(row.get("effective_level") != "L0" and
                                        row.get("certificate_scope_valid") is not True for row in contract),
        "certificate_session_coverage": len(certified) / max(1, len(session_ids)),
        "certified_prefix_reuse": statistics.fmean(reuse) if reuse else 0.0,
        "max_dynamic_suffix_reuse_tokens": max(
            [int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in cert_future], default=0),
    }


def heldout(args: argparse.Namespace) -> int:
    sessions_list = load(args.sessions)
    sessions = {str(row["phase19b_session_id"]): row for row in sessions_list}
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if {family_key(row) for row in sessions_list} != EXPECTED_FAMILIES:
        raise RuntimeError("heldout does not contain the frozen five-family scope")
    pairs = []
    for spec in args.pair:
        repeat, raw_path, contract_path = spec.split(",", 2)
        pairs.append((int(repeat), load(Path(raw_path)), load(Path(contract_path))))
    quality_rows = []
    level_rows = []
    for repeat, raw_rows, contract_rows in pairs:
        quality_rows.extend(score_pairs(sessions, raw_rows, contract_rows, "frozen-adaptive", repeat))
        counts: dict[tuple[str, str, str], int] = defaultdict(int)
        for row in contract_rows:
            if row.get("row_type") != "canary":
                continue
            sid = str(row["session_id"])
            counts[(family_key(sessions[sid]), str(row.get("requested_level", "L0")),
                    str(row.get("effective_level", "L0")))] += 1
        for (family, requested, effective), count in sorted(counts.items()):
            level_rows.append({"repeat": repeat, "family": family,
                               "requested_level": requested, "effective_level": effective,
                               "session_count": count})
    rows = []
    all_ids = set(sessions)
    qualified_ids = {sid for sid, sample in sessions.items()
                     if manifest["frozen_family_levels"].get(family_key(sample), "L0") != "L0"}
    for repeat, raw_rows, contract_rows in pairs:
        qrepeat = [row for row in quality_rows if row["repeat"] == repeat]
        rows.append(scope_summary(raw_rows, contract_rows, qrepeat, all_ids, "all", repeat, args.slo_ms))
        rows.append(scope_summary(raw_rows, contract_rows, qrepeat, qualified_ids, "qualified_subset", repeat, args.slo_ms))
        for family in sorted(EXPECTED_FAMILIES):
            ids = {sid for sid, sample in sessions.items() if family_key(sample) == family}
            record = scope_summary(raw_rows, contract_rows, qrepeat, ids, family, repeat, args.slo_ms)
            record["frozen_level"] = manifest["frozen_family_levels"].get(family, "L0")
            rows.append(record)
    aggregate = []
    for scope in ["all", "qualified_subset", *sorted(EXPECTED_FAMILIES)]:
        group = [row for row in rows if row["scope"] == scope]
        record = {"scope": scope, "fresh_process_repeats": len(group)}
        for key in group[0]:
            if key in {"scope", "repeat", "frozen_level"}:
                continue
            values = [row[key] for row in group if isinstance(row.get(key), (int, float))]
            if values:
                record[key] = statistics.fmean(values)
        if scope in EXPECTED_FAMILIES:
            record["frozen_level"] = manifest["frozen_family_levels"].get(scope, "L0")
        aggregate.append(record)
    global_row = next(row for row in aggregate if row["scope"] == "all")
    qualified_family_count = sum(level != "L0" for level in manifest["frozen_family_levels"].values())
    gates = {
        "completion_100": global_row["completion_rate"] == 1.0,
        "policy_attributable_quality_violations_zero": global_row["policy_attributable_quality_violations"] == 0,
        "scope_invalid_admissions_zero": global_row["scope_invalid_admissions"] == 0,
        "dynamic_suffix_reuse_zero": global_row["max_dynamic_suffix_reuse_tokens"] == 0,
        "certified_prefix_reuse_ge_95pct": global_row["certified_prefix_reuse"] >= 0.95,
        "qualified_families_ge_3": qualified_family_count >= 3,
        "certificate_session_coverage_ge_50pct": global_row["certificate_session_coverage"] >= 0.50,
        "new_prefill_reduction_ge_30pct": global_row["new_prefill_reduction"] >= 0.30,
        "net_mean_ttft_reduction_ge_25pct": global_row["net_mean_ttft_reduction"] >= 0.25,
    }
    strong = {
        "qualified_families_ge_4": qualified_family_count >= 4,
        "global_net_mean_ttft_reduction_ge_30pct": global_row["net_mean_ttft_reduction"] >= 0.30,
        "global_new_prefill_reduction_ge_35pct": global_row["new_prefill_reduction"] >= 0.35,
    }
    gate = {
        "schema_version": "contractkv.llama-broad-heldout-gate.v1",
        "qualification_hash": manifest["qualification_hash"],
        "heldout_sessions": len(sessions), "future_requests_per_repeat": len(sessions) * 9,
        "fresh_process_repeats": len(pairs), "qualified_family_count": qualified_family_count,
        "paper_gates": gates, "paper_gate_pass": all(gates.values()),
        "strong_gates": strong, "strong_gate_pass": all(strong.values()),
        "claim_boundary": "Sealed five-family heldout with raw fallback included in global metrics.",
    }
    write_csv(args.raw_summary, rows)
    write_csv(args.aggregate_summary, aggregate)
    write_csv(args.quality_output, quality_rows)
    if args.level_output:
        write_csv(args.level_output, level_rows)
    args.gate_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"global": global_row, "gate": gate}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("--sessions", type=Path, required=True)
    freeze_parser.add_argument("--cell", action="append", required=True)
    freeze_parser.add_argument("--model-identity", required=True)
    freeze_parser.add_argument("--minimum-development-sessions", type=int, default=5)
    freeze_parser.add_argument("--minimum-admitted-coverage", type=float, default=0.6)
    freeze_parser.add_argument("--max-tokens", type=int, default=96)
    freeze_parser.add_argument("--stable-word-limit", type=int, default=1500)
    freeze_parser.add_argument("--stable-pieces", type=int, default=4)
    freeze_parser.add_argument("--layout-ladder", type=json.loads,
                               default={"L0": 0.0, "L1": 0.25, "L2": 0.50, "L3": 1.0})
    freeze_parser.add_argument("--split-commitment", type=Path)
    freeze_parser.add_argument("--development-summary", type=Path, required=True)
    freeze_parser.add_argument("--quality-output", type=Path, required=True)
    freeze_parser.add_argument("--manifest", type=Path, required=True)
    heldout_parser = sub.add_parser("heldout")
    heldout_parser.add_argument("--sessions", type=Path, required=True)
    heldout_parser.add_argument("--manifest", type=Path, required=True)
    heldout_parser.add_argument("--pair", action="append", required=True)
    heldout_parser.add_argument("--slo-ms", type=float, default=1500)
    heldout_parser.add_argument("--raw-summary", type=Path, required=True)
    heldout_parser.add_argument("--aggregate-summary", type=Path, required=True)
    heldout_parser.add_argument("--quality-output", type=Path, required=True)
    heldout_parser.add_argument("--level-output", type=Path)
    heldout_parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()
    return freeze(args) if args.command == "freeze" else heldout(args)


if __name__ == "__main__":
    raise SystemExit(main())
