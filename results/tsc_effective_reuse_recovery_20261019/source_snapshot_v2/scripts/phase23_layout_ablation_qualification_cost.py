#!/usr/bin/env python3
"""Build the Phase 23 layout-ladder ablation and qualification-cost tables."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


LEVELS = ["L0", "L1", "L2", "L3"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def family(row: dict[str, Any]) -> str:
    return f"{row.get('dataset', '')}:{row.get('task', '')}"


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [as_float(row.get(key)) for row in rows if row.get(key) not in {"", None}]
    return statistics.fmean(values) if values else 0.0


def canary_by_session(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["session_id"]): row for row in rows if row.get("row_type") == "canary"}


def future_by_session(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("row_type") == "future":
            result[str(row["session_id"])].append(row)
    return result


def quality_index(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    result: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        result[(row["level"], row["session_id"])].append(row)
    return result


def quality_violations(rows: list[dict[str, str]]) -> int:
    return sum(str(row.get("policy_attributable_quality_violation", "")).lower() == "true" for row in rows)


def select_strategy_levels(
    strategy: str,
    sessions: list[dict[str, Any]],
    manifest: dict[str, Any],
    canaries: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for sample in sessions:
        sid = str(sample["phase19b_session_id"])
        fam = family(sample)
        if strategy == "raw_fallback":
            selected[sid] = "L0"
        elif strategy == "fixed_L3":
            selected[sid] = "L3"
        elif strategy == "family_fixed_maximum":
            selected[sid] = str(manifest["frozen_family_levels"].get(fam, "L0"))
        elif strategy == "certificate_guided_descent":
            maximum = str(manifest["frozen_family_levels"].get(fam, "L0"))
            eligible = set(manifest["family_eligible_levels"].get(fam, []))
            candidates = [level for level in reversed(LEVELS[1:LEVELS.index(maximum) + 1]) if level in eligible]
            selected[sid] = next(
                (level for level in candidates if canaries[level].get(sid, {}).get("certificate_issued") is True),
                "L0",
            )
        else:
            raise ValueError(strategy)
    return selected


def summarize_strategy(
    strategy: str,
    sessions: list[dict[str, Any]],
    selected: dict[str, str],
    cells: dict[str, list[dict[str, Any]]],
    futures: dict[str, dict[str, list[dict[str, Any]]]],
    canaries: dict[str, dict[str, dict[str, Any]]],
    quality: dict[tuple[str, str], list[dict[str, str]]],
) -> dict[str, Any]:
    chosen_future: list[dict[str, Any]] = []
    promoted_sessions: set[str] = set()
    safe_promoted_sessions: set[str] = set()
    completed_safe_sessions: set[str] = set()
    unsafe_sessions: set[str] = set()
    policy_quality_violations = 0
    scope_invalid = 0
    length_unsafe = 0
    level_counts = defaultdict(int)
    for sample in sessions:
        sid = str(sample["phase19b_session_id"])
        level = selected[sid]
        level_counts[level] += 1
        rows = futures[level].get(sid, [])
        chosen_future.extend(rows)
        qrows = quality.get((level, sid), []) if level != "L0" else []
        violations = quality_violations(qrows)
        policy_quality_violations += violations
        effective = any(row.get("effective_level") != "L0" for row in rows)
        if level != "L0" and canaries[level].get(sid, {}).get("certificate_issued") is True and effective:
            promoted_sessions.add(sid)
            if violations == 0:
                safe_promoted_sessions.add(sid)
                if rows and all(row.get("success") is True for row in rows):
                    completed_safe_sessions.add(sid)
            else:
                unsafe_sessions.add(sid)
        scope_invalid += sum(
            row.get("effective_level") != "L0" and row.get("certificate_scope_valid") is not True for row in rows
        )
        length_unsafe += int(
            bool(canaries[level].get(sid, {}).get("length_stop"))
            and canaries[level].get(sid, {}).get("certificate_issued") is True
        ) if level != "L0" else 0

    raw_future = [row for row in cells["L0"] if row.get("row_type") == "future"]
    raw_prefix = mean(raw_future, "prefix_hit_tokens")
    raw_new = mean(raw_future, "new_prefill_tokens")
    certified_rows = [
        row for row in chosen_future
        if str(row.get("session_id")) in promoted_sessions and row.get("prefix_hit_tokens") not in {"", None}
    ]
    stable_total = sum(as_float(row.get("certified_stable_prefix_tokens")) for row in certified_rows)
    reused_total = sum(
        min(as_float(row.get("prefix_hit_tokens")), as_float(row.get("certified_stable_prefix_tokens")))
        for row in certified_rows
    )
    return {
        "strategy": strategy,
        "sessions": len(sessions),
        "future_requests": len(chosen_future),
        "completion_rate": sum(row.get("success") is True for row in chosen_future) / max(1, len(chosen_future)),
        "promoted_session_coverage": len(promoted_sessions) / max(1, len(sessions)),
        "safe_promoted_session_coverage": len(safe_promoted_sessions) / max(1, len(sessions)),
        "safe_completed_session_coverage": len(completed_safe_sessions) / max(1, len(sessions)),
        "unsafe_promoted_sessions": len(unsafe_sessions),
        "policy_attributable_quality_violations": policy_quality_violations,
        "quality_violation_rate": policy_quality_violations / max(1, len(chosen_future)),
        "scope_invalid_admissions": scope_invalid,
        "length_stop_unsafe_admissions": length_unsafe,
        "mean_prefix_hit_tokens": mean(chosen_future, "prefix_hit_tokens"),
        "retained_prefix_gain_tokens_vs_raw": mean(chosen_future, "prefix_hit_tokens") - raw_prefix,
        "mean_new_prefill_tokens": mean(chosen_future, "new_prefill_tokens"),
        "new_prefill_reduction_vs_raw": (raw_new - mean(chosen_future, "new_prefill_tokens")) / max(1.0, raw_new),
        "certified_prefix_physical_reuse": reused_total / max(1.0, stable_total) if certified_rows else 0.0,
        "max_dynamic_suffix_reuse_tokens": max(
            [int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in certified_rows], default=0
        ),
        "L0_sessions": level_counts["L0"],
        "L1_sessions": level_counts["L1"],
        "L2_sessions": level_counts["L2"],
        "L3_sessions": level_counts["L3"],
        "claim_boundary": (
            "Composed from real Llama development cells. Strategy selection uses Turn-0 certificates only; "
            "future quality is used only for retrospective safety measurement."
        ),
    }


def subset_level_decision(
    family_name: str,
    session_ids: tuple[str, ...],
    cells: dict[str, list[dict[str, Any]]],
    futures: dict[str, dict[str, list[dict[str, Any]]]],
    canaries: dict[str, dict[str, dict[str, Any]]],
    quality: dict[tuple[str, str], list[dict[str, str]]],
) -> str:
    raw_rows = [row for sid in session_ids for row in futures["L0"].get(sid, [])]
    raw_prefix = mean(raw_rows, "prefix_hit_tokens")
    eligible: list[tuple[float, int, str]] = []
    for level in LEVELS[1:]:
        rows = [row for sid in session_ids for row in futures[level].get(sid, [])]
        cert = [sid for sid in session_ids if canaries[level].get(sid, {}).get("certificate_issued") is True]
        qrows = [row for sid in session_ids for row in quality.get((level, sid), [])]
        admitted = len(cert) / max(1, len(session_ids))
        certified_rows = [row for row in rows if str(row.get("session_id")) in cert and row.get("effective_level") != "L0"]
        stable_total = sum(as_float(row.get("certified_stable_prefix_tokens")) for row in certified_rows)
        reused_total = sum(
            min(as_float(row.get("prefix_hit_tokens")), as_float(row.get("certified_stable_prefix_tokens")))
            for row in certified_rows
        )
        reuse = reused_total / max(1.0, stable_total) if certified_rows else 0.0
        valid = (
            rows and all(row.get("success") is True for row in rows)
            and admitted >= 0.4
            and quality_violations(qrows) == 0
            and all(row.get("effective_level") == "L0" or row.get("certificate_scope_valid") is True for row in rows)
            and not any(
                bool(canaries[level].get(sid, {}).get("length_stop"))
                and canaries[level].get(sid, {}).get("certificate_issued") is True
                for sid in session_ids
            )
            and mean(rows, "prefix_hit_tokens") - raw_prefix > 0
            and reuse >= 0.95
            and max([int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in certified_rows], default=0) == 0
        )
        if valid:
            eligible.append((mean(rows, "prefix_hit_tokens") - raw_prefix, -LEVELS.index(level), level))
    return max(eligible)[2] if eligible else "L0"


def build_stability(
    sessions: list[dict[str, Any]],
    manifest: dict[str, Any],
    cells: dict[str, list[dict[str, Any]]],
    futures: dict[str, dict[str, list[dict[str, Any]]]],
    canaries: dict[str, dict[str, dict[str, Any]]],
    quality: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    families: dict[str, list[str]] = defaultdict(list)
    for sample in sessions:
        families[family(sample)].append(str(sample["phase19b_session_id"]))
    rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for fam, sids in sorted(families.items()):
        frozen = str(manifest["frozen_family_levels"].get(fam, "L0"))
        by_n = {}
        for n in range(1, len(sids) + 1):
            decisions = [subset_level_decision(fam, subset, cells, futures, canaries, quality)
                         for subset in itertools.combinations(sorted(sids), n)]
            agreement = sum(value == frozen for value in decisions) / len(decisions)
            by_n[n] = agreement
            counts = {level: decisions.count(level) for level in LEVELS}
            rows.append({
                "family": fam, "samples_per_family": n, "subsets_evaluated": len(decisions),
                "full_five_session_level": frozen, "selection_agreement_fraction": agreement,
                **{f"selected_{level}_count": counts[level] for level in LEVELS},
                "claim_boundary": "Retrospective exact-subset stability diagnostic; held-out data are not used.",
            })
        n80 = next((n for n in by_n if all(by_n[m] >= 0.8 for m in range(n, len(sids) + 1))), len(sids))
        n100 = next((n for n in by_n if all(by_n[m] == 1.0 for m in range(n, len(sids) + 1))), len(sids))
        summary.append({
            "family": fam, "frozen_level": frozen,
            "minimum_samples_for_80pct_stability": n80,
            "minimum_samples_for_100pct_stability": n100,
            "five_session_selection_stable": by_n[len(sids)] == 1.0,
        })
    return rows, summary


def lookup_benchmark(manifest: dict[str, Any], families: list[str], iterations: int) -> tuple[float, float]:
    samples: list[int] = []
    levels = manifest["frozen_family_levels"]
    eligible = manifest["family_eligible_levels"]
    for index in range(iterations):
        fam = families[index % len(families)]
        started = time.perf_counter_ns()
        _ = (levels.get(fam, "L0"), eligible.get(fam, []))
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    return statistics.fmean(samples) / 1000.0, ordered[int(0.95 * (len(ordered) - 1))] / 1000.0


def build_heldout_descent_ablation(
    pairs: list[str], quality_path: Path, output: Path,
) -> list[dict[str, Any]]:
    quality_rows = load_csv(quality_path)
    violation = {
        (int(row["repeat"]), row["session_id"], int(row["turn_id"])):
        str(row.get("policy_attributable_quality_violation", "")).lower() == "true"
        for row in quality_rows
    }
    per_repeat: list[dict[str, Any]] = []
    for value in pairs:
        repeat_s, raw_path_s, contract_path_s = value.split(",", 2)
        repeat = int(repeat_s)
        raw_rows = load_jsonl(Path(raw_path_s)); contract_rows = load_jsonl(Path(contract_path_s))
        raw_future = {(str(row["session_id"]), int(row["turn_id"])): row for row in raw_rows
                      if row.get("row_type") == "future"}
        contract_future = {(str(row["session_id"]), int(row["turn_id"])): row for row in contract_rows
                           if row.get("row_type") == "future"}
        canary = {str(row["session_id"]): row for row in contract_rows if row.get("row_type") == "canary"}
        for strategy in ["family_fixed_maximum", "certificate_guided_descent", "raw_fallback"]:
            chosen = []
            promoted = set()
            violations = 0
            for key, raw in raw_future.items():
                candidate = contract_future[key]
                info = canary[key[0]]
                exact_family_max = (
                    str(info.get("effective_level")) == str(info.get("requested_level"))
                    and str(info.get("effective_level")) != "L0"
                )
                if strategy == "raw_fallback":
                    row = raw
                elif strategy == "family_fixed_maximum":
                    row = candidate if exact_family_max else raw
                    if exact_family_max:
                        promoted.add(key[0])
                else:
                    row = candidate
                    if str(info.get("effective_level")) != "L0":
                        promoted.add(key[0])
                    violations += int(violation.get((repeat, key[0], key[1]), False))
                chosen.append(row)
            raw_values = list(raw_future.values())
            stable_total = sum(
                as_float(row.get("certified_stable_prefix_tokens")) for row in chosen
                if str(row.get("session_id")) in promoted
            )
            reused_total = sum(
                min(as_float(row.get("prefix_hit_tokens")), as_float(row.get("certified_stable_prefix_tokens")))
                for row in chosen if str(row.get("session_id")) in promoted
            )
            per_repeat.append({
                "repeat": repeat, "strategy": strategy, "sessions": len(canary),
                "future_requests": len(chosen),
                "completion_rate": sum(row.get("success") is True for row in chosen) / max(1, len(chosen)),
                "safe_completed_session_coverage": len(promoted) / max(1, len(canary)),
                "policy_attributable_quality_violations": violations,
                "retained_prefix_gain_tokens_vs_raw": mean(chosen, "prefix_hit_tokens") - mean(raw_values, "prefix_hit_tokens"),
                "new_prefill_reduction_vs_raw": (
                    mean(raw_values, "new_prefill_tokens") - mean(chosen, "new_prefill_tokens")
                ) / max(1.0, mean(raw_values, "new_prefill_tokens")),
                "certified_prefix_physical_reuse": reused_total / max(1.0, stable_total) if promoted else 0.0,
                "max_dynamic_suffix_reuse_tokens": max([
                    int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in chosen
                    if str(row.get("session_id")) in promoted
                ], default=0),
            })
    aggregate = []
    for strategy in ["family_fixed_maximum", "certificate_guided_descent", "raw_fallback"]:
        rows = [row for row in per_repeat if row["strategy"] == strategy]
        aggregate.append({
            "repeat": "aggregate", "strategy": strategy, "sessions": rows[0]["sessions"],
            "future_requests": rows[0]["future_requests"],
            **{key: statistics.fmean(as_float(row[key]) for row in rows) for key in [
                "completion_rate", "safe_completed_session_coverage",
                "policy_attributable_quality_violations", "retained_prefix_gain_tokens_vs_raw",
                "new_prefill_reduction_vs_raw", "certified_prefix_physical_reuse",
                "max_dynamic_suffix_reuse_tokens",
            ]},
        })
    write_csv(output, per_repeat + aggregate)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--cell", action="append", required=True, help="LEVEL=path")
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--development-wall-seconds", type=float, required=True)
    parser.add_argument("--development-gpus", type=int, default=2)
    parser.add_argument("--lookup-iterations", type=int, default=100000)
    parser.add_argument("--ablation-output", type=Path, required=True)
    parser.add_argument("--cost-output", type=Path, required=True)
    parser.add_argument("--stability-output", type=Path, required=True)
    parser.add_argument("--stability-summary-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--heldout-pair", action="append", default=[])
    parser.add_argument("--heldout-quality", type=Path)
    parser.add_argument("--heldout-output", type=Path)
    args = parser.parse_args()

    sessions = load_jsonl(args.sessions)
    cells = {value.split("=", 1)[0]: load_jsonl(Path(value.split("=", 1)[1])) for value in args.cell}
    if set(cells) != set(LEVELS):
        raise RuntimeError(f"expected cells {LEVELS}, got {sorted(cells)}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    quality = quality_index(load_csv(args.quality))
    canaries = {level: canary_by_session(rows) for level, rows in cells.items()}
    futures = {level: future_by_session(rows) for level, rows in cells.items()}
    strategies = ["fixed_L3", "family_fixed_maximum", "certificate_guided_descent", "raw_fallback"]
    ablation = []
    for strategy in strategies:
        selected = select_strategy_levels(strategy, sessions, manifest, canaries)
        ablation.append(summarize_strategy(strategy, sessions, selected, cells, futures, canaries, quality))
    stability, stability_summary = build_stability(sessions, manifest, cells, futures, canaries, quality)
    heldout = []
    if args.heldout_pair:
        if not args.heldout_quality or not args.heldout_output:
            parser.error("--heldout-quality and --heldout-output are required with --heldout-pair")
        heldout = build_heldout_descent_ablation(args.heldout_pair, args.heldout_quality, args.heldout_output)
    families = sorted({family(row) for row in sessions})
    lookup_mean_us, lookup_p95_us = lookup_benchmark(manifest, families, args.lookup_iterations)
    gpu_hours = args.development_wall_seconds * args.development_gpus / 3600.0
    cost = [{
        "development_sessions": len(sessions),
        "families": len(families),
        "layout_cells": len(cells),
        "development_wall_seconds": args.development_wall_seconds,
        "development_gpus": args.development_gpus,
        "development_gpu_hours": gpu_hours,
        "qualification_manifest_bytes": args.manifest.stat().st_size,
        "runtime_lookup_iterations": args.lookup_iterations,
        "runtime_lookup_mean_us": lookup_mean_us,
        "runtime_lookup_p95_us": lookup_p95_us,
        "mean_samples_for_80pct_stability": statistics.fmean(
            row["minimum_samples_for_80pct_stability"] for row in stability_summary
        ),
        "max_samples_for_80pct_stability": max(row["minimum_samples_for_80pct_stability"] for row in stability_summary),
        "claim_boundary": (
            "GPU-hours use measured development wall time times two concurrently occupied RTX 3090 GPUs; "
            "sample stability is retrospective on development only."
        ),
    }]
    write_csv(args.ablation_output, ablation)
    write_csv(args.cost_output, cost)
    write_csv(args.stability_output, stability)
    write_csv(args.stability_summary_output, stability_summary)
    guided = next(row for row in ablation if row["strategy"] == "certificate_guided_descent")
    family_fixed = next(row for row in ablation if row["strategy"] == "family_fixed_maximum")
    fixed_l3 = next(row for row in ablation if row["strategy"] == "fixed_L3")
    summary = {
        "schema_version": "contractkv.phase23.layout-ablation-cost.v1",
        "development_sessions": len(sessions),
        "gpu_hours": gpu_hours,
        "manifest_bytes": args.manifest.stat().st_size,
        "runtime_lookup_mean_us": lookup_mean_us,
        "runtime_lookup_p95_us": lookup_p95_us,
        "descent_vs_family_fixed": {
            "completion_rate_delta": guided["completion_rate"] - family_fixed["completion_rate"],
            "safe_completed_coverage_delta": guided["safe_completed_session_coverage"] - family_fixed["safe_completed_session_coverage"],
            "retained_prefix_gain_delta_tokens": guided["retained_prefix_gain_tokens_vs_raw"] - family_fixed["retained_prefix_gain_tokens_vs_raw"],
        },
        "descent_vs_fixed_L3": {
            "policy_quality_violations_removed": fixed_l3["policy_attributable_quality_violations"] - guided["policy_attributable_quality_violations"],
            "unsafe_promoted_sessions_removed": fixed_l3["unsafe_promoted_sessions"] - guided["unsafe_promoted_sessions"],
        },
        "stability_by_family": stability_summary,
        "sealed_heldout_descent_ablation": heldout,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
