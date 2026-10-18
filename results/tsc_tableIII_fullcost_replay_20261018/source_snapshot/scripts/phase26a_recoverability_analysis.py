#!/usr/bin/env python3
"""Summarize Phase 26A and apply its frozen continuation gate."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import benefit_utility, percentile


CALIBRATION_MS_PER_TOKEN = {
    "chat": (255.20962368888888 - 223.22111934074073) / (1247.5 - 1067.2333333333333),
    "coder": (254.7883136 - 126.14124541111111) / (1247.5 - 48.74444444444445),
}
SERVING_FLOOR_MS = {
    "chat": 223.22111934074073,
    "coder": 126.14124541111111,
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--phase25", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    gate_cfg = protocol["continuation_gate"]
    benefit_cfg = protocol["benefit_gate"]
    all_class_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    regret_rows: list[dict[str, Any]] = []
    model_summaries: list[dict[str, Any]] = []

    for model_key in ("chat", "coder"):
        audit = load_jsonl(args.base / model_key / "strict_failure_recoverability_v0.jsonl")
        diagnostic = {(str(row["session_id"]), str(row["level"])): row for row in
                      load_jsonl(args.phase25 / model_key / "certificate_diagnostic_v0.jsonl")}
        heldout = {str(row["scope"]): row for row in
                   load_csv(args.phase25 / model_key / "heldout_scope_aggregate_v0.csv")}
        family_raw_ttft = {scope: float(row["raw_mean_ttft_ms"]) for scope, row in heldout.items()
                           if scope not in {"all", "qualified_subset"}}
        by_family_level: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in audit:
            diag = diagnostic[(str(row["session_id"]), str(row["level"]))]
            row["stable_prefix_tokens"] = int(
                row.get("tokenizer_exact_stable_prefix_tokens")
                or diag.get("stable_prefix_tokens", 0) or 0)
            row["candidate_prompt_tokens"] = int(
                row.get("tokenizer_exact_candidate_prompt_tokens")
                or row.get("candidate_prompt_tokens", 0) or 0)
            by_family_level[(str(row["family"]), str(row["level"]))].append(row)
        counts = Counter(str(row["recoverability_class"]) for row in audit)
        all_class_rows.extend({"model_key": model_key, "class": key, "count": value,
                               "fraction": value / len(audit)} for key, value in sorted(counts.items()))

        strict_non_length = [row for row in audit if row.get("exact_decision") == "FAIL"
                             and row.get("raw_complete") and row.get("candidate_complete")]
        task_safe = [row for row in strict_non_length if float(row.get("quality_drop", 1.0)) <= .03]
        task_safe_fraction = len(task_safe) / max(1, len(strict_non_length))
        selected: dict[str, dict[str, Any]] = {}
        for (family, level), rows in sorted(by_family_level.items()):
            raw_ttft = family_raw_ttft.get(family, mean(list(family_raw_ttft.values())))
            maximum_prefill_saving = max(0.0, raw_ttft - SERVING_FLOOR_MS[model_key])
            strict_attempts = [row for row in rows if row.get("recoverability_class") != "exact_pass"
                               and row.get("raw_complete") and row.get("candidate_complete")]
            typed_passes = [row for row in strict_attempts
                            if (row.get("typed_contract") or {}).get("decision") == "PASS"
                            and float(row.get("quality_drop", 1.0)) <= .03]
            offline_recoverable = [row for row in strict_attempts
                                   if float(row.get("quality_drop", 1.0)) <= .03]
            p_b = len(offline_recoverable) / max(1, len(strict_attempts))
            candidate_costs = [float(row.get("candidate_decode_ms", 0.0) or 0.0)
                               + float((row.get("typed_contract") or {}).get("runtime_ms", 0.0) or 0.0)
                               for row in strict_attempts]
            saved_ms_candidates = [min(maximum_prefill_saving,
                                       int(row["stable_prefix_tokens"]) * CALIBRATION_MS_PER_TOKEN[model_key])
                                   for row in strict_attempts]
            benefit = benefit_utility(
                pass_probability=p_b,
                expected_reuses=int(benefit_cfg["expected_future_reuses"]),
                saved_ms_per_request=mean(saved_ms_candidates),
                verify_ms=mean(candidate_costs),
                slack_ms=float(benefit_cfg["tool_slack_ms"]),
            )
            exact = [row for row in rows if row["recoverability_class"] == "exact_pass"]
            recoverable = exact + (offline_recoverable if benefit["admit"] else [])
            deployable_v1 = exact + (typed_passes if benefit["admit"] else [])
            offline_safe = [row for row in rows if row["recoverability_class"] in {
                "exact_pass", "exact_path_false_negative", "bounded_task_safe_but_not_online_certified"}]
            recoverable_ids = {(row["session_id"], row["level"]) for row in recoverable}
            stable_tokens = sum(int(row["stable_prefix_tokens"]) for row in rows
                                if (row["session_id"], row["level"]) in recoverable_ids)
            total_prompt = sum(int(row["candidate_prompt_tokens"]) for row in rows)
            gross_saved = sum(min(maximum_prefill_saving,
                                  int(row["stable_prefix_tokens"]) * CALIBRATION_MS_PER_TOKEN[model_key])
                              * int(benefit_cfg["expected_future_reuses"])
                              for row in recoverable)
            incremental_cost = sum(max(0.0, float(row.get("candidate_decode_ms", 0.0) or 0.0)
                                       - float(benefit_cfg["tool_slack_ms"]))
                                   for row in offline_recoverable) if benefit["admit"] else 0.0
            net_saved = max(0.0, gross_saved - incremental_cost)
            summary = {
                "model_key": model_key, "family": family, "level": level,
                "sessions": len(rows), "exact_passes": len(exact),
                "strict_attempts": len(strict_attempts), "typed_passes": len(typed_passes),
                "offline_task_safe_probability": p_b,
                "offline_task_safe_upper_bound": len(offline_safe) / len(rows),
                "benefit_gate_admit": bool(benefit["admit"]),
                "benefit_expected_gain_ms": benefit["expected_gain_ms"],
                "mean_candidate_verify_ms": mean(candidate_costs),
                "recoverable_upper_coverage": len(recoverable) / len(rows),
                "typed_v1_deployable_coverage": len(deployable_v1) / len(rows),
                "theoretical_new_prefill_reduction": stable_tokens / max(1, total_prompt),
                "theoretical_net_ttft_reduction": net_saved / max(
                    1.0, len(rows) * int(benefit_cfg["expected_future_reuses"]) * raw_ttft),
                "repo_complete_safe_sessions": sum(
                    bool(row.get("raw_complete")) and bool(row.get("candidate_complete"))
                    and float(row.get("quality_drop", 1.0)) <= .03 for row in rows),
            }
            family_rows.append(summary)
            current = selected.get(family)
            score = (summary["theoretical_net_ttft_reduction"],
                     summary["theoretical_new_prefill_reduction"], level)
            if current is None or score > (current["theoretical_net_ttft_reduction"],
                                           current["theoretical_new_prefill_reduction"], current["level"]):
                selected[family] = summary

        for classification in sorted(set(str(row["recoverability_class"]) for row in audit)):
            subset = [row for row in audit if row["recoverability_class"] == classification
                      and (row.get("teacher_forced_regret") or {}).get("available")]
            regret_rows.append({
                "model_key": model_key, "recoverability_class": classification,
                "rows": len(subset),
                "mean_regret_max": mean([float(row["teacher_forced_regret"].get("regret_max", 0.0)) for row in subset]),
                "mean_regret_q95": mean([float(row["teacher_forced_regret"].get("regret_q95", 0.0)) for row in subset]),
                "mean_positive_fraction": mean([float(row["teacher_forced_regret"].get("regret_positive_fraction", 0.0)) for row in subset]),
                "mean_top1_match_fraction": mean([float(row["teacher_forced_regret"].get("top1_match_fraction", 1.0)) for row in subset]),
            })

        choices = list(selected.values())
        families_over_50 = sum(float(row["recoverable_upper_coverage"]) >= float(gate_cfg["workflow_recoverable_coverage_threshold"])
                               for row in choices)
        global_new_prefill = mean([float(row["theoretical_new_prefill_reduction"]) for row in choices])
        global_net_ttft = mean([float(row["theoretical_net_ttft_reduction"]) for row in choices])
        repo_levels = [row for row in family_rows if row["model_key"] == model_key
                       and row["family"] == "RepoBench:python_v1.1"]
        repo_complete_safe = max((int(row["repo_complete_safe_sessions"])
                                  for row in repo_levels), default=0)
        checks = {
            "non_length_strict_fail_task_safe_fraction": task_safe_fraction >= float(gate_cfg["minimum_non_length_strict_fail_task_safe_fraction"]),
            "workflow_family_count": families_over_50 >= int(gate_cfg["minimum_workflow_families_with_recoverable_coverage"]),
            "global_theoretical_new_prefill": global_new_prefill >= float(gate_cfg["minimum_global_theoretical_new_prefill_reduction"]),
            "global_theoretical_net_ttft": global_net_ttft >= float(gate_cfg["minimum_global_theoretical_net_ttft_reduction"]),
            "repobench_complete_safe_sessions": repo_complete_safe >= int(gate_cfg["minimum_repobench_complete_safe_sessions"]),
        }
        model_summaries.append({
            "model_key": model_key, "audit_rows": len(audit),
            "non_length_strict_fail_rows": len(strict_non_length),
            "non_length_strict_fail_task_safe": len(task_safe),
            "non_length_strict_fail_task_safe_fraction": task_safe_fraction,
            "families_with_deployable_coverage_ge_50pct": families_over_50,
            "selected_levels": json.dumps({family: row["level"] for family, row in selected.items()}, sort_keys=True),
            "global_theoretical_new_prefill_reduction": global_new_prefill,
            "global_theoretical_net_ttft_reduction": global_net_ttft,
            "repobench_complete_safe_sessions": repo_complete_safe,
            "continuation_checks": json.dumps(checks, sort_keys=True),
            "continuation_gate_pass": all(checks.values()),
        })

    write_csv(args.base / "recoverability_class_summary_v0.csv", all_class_rows)
    write_csv(args.base / "family_recoverability_gate_v0.csv", family_rows)
    write_csv(args.base / "token_regret_summary_v0.csv", regret_rows)
    write_csv(args.base / "model_continuation_gate_v0.csv", model_summaries)
    gate = {
        "schema_version": "contractkv.phase26a.continuation-gate.v0",
        "models": model_summaries,
        "continue_phase26b_d": any(bool(row["continuation_gate_pass"]) for row in model_summaries),
        "continue_models": [row["model_key"] for row in model_summaries if row["continuation_gate_pass"]],
        "heldout_opened": False,
        "claim_boundary": "Development-only upper-bound and deployable typed-contract analysis; no new held-out run was authorized unless the frozen gate passes.",
    }
    (args.base / "phase26a_continuation_gate_v0.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
