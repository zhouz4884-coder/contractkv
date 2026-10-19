#!/usr/bin/env python3
"""Build the submission-facing ContractKV Why-and-When analysis tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


FAMILY_ORDER = ["RULER", "HotpotQA", "NarrativeQA", "Qasper", "RepoBench"]
FAMILY_NAMES = {
    ("RULER", "niah_single_1"): "RULER",
    ("LongBench", "hotpotqa"): "HotpotQA",
    ("LongBench", "narrativeqa"): "NarrativeQA",
    ("LongBench", "qasper"): "Qasper",
    ("RepoBench", "python_v1.1"): "RepoBench",
}


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
    fieldnames = list(rows[0])
    for row in rows[1:]:
        fieldnames.extend(key for key in row if key not in fieldnames)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def mean(rows: Iterable[dict[str, Any]], key: str) -> float:
    values = [as_float(row.get(key)) for row in rows if row.get(key) not in {None, ""}]
    return statistics.fmean(values) if values else 0.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def family_name(row: dict[str, Any]) -> str:
    return FAMILY_NAMES.get((str(row.get("dataset", "")), str(row.get("task", ""))), "Unknown")


def live_family_map(
    model: str,
    raw_rows: list[dict[str, Any]],
    contract_rows: list[dict[str, Any]],
    load_tier: str | None,
    target_unhidden_per_request: float | None = None,
) -> list[dict[str, Any]]:
    if load_tier is not None:
        raw_rows = [row for row in raw_rows if row.get("load_tier") == load_tier]
        contract_rows = [row for row in contract_rows if row.get("load_tier") == load_tier]
    raw_future = [row for row in raw_rows if row.get("row_type") == "future" and row.get("policy") == "raw-order"]
    contract_future = [
        row for row in contract_rows if row.get("row_type") == "future" and row.get("policy") == "contractkv-full"
    ]
    canaries = [
        row for row in contract_rows if row.get("row_type") == "canary" and row.get("policy") == "contractkv-full"
    ]
    observed_unhidden_per_request = sum(as_float(row.get("unhidden_verifier_ms")) for row in canaries) / max(
        len(contract_future), 1
    )
    overhead_scale = (
        target_unhidden_per_request / observed_unhidden_per_request
        if target_unhidden_per_request is not None and observed_unhidden_per_request > 0
        else 1.0
    )
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        raw = [row for row in raw_future if family_name(row) == family]
        candidate = [row for row in contract_future if family_name(row) == family]
        family_canaries = [row for row in canaries if family_name(row) == family]
        passed = sum(row.get("verify_decision") == "PASS" for row in family_canaries)
        sessions = len(family_canaries)
        verifier_per_request = (
            sum(as_float(row.get("unhidden_verifier_ms")) for row in family_canaries)
            / max(len(candidate), 1)
            * overhead_scale
        )
        raw_ttft = mean(raw, "ttft_ms")
        contract_ttft = mean(candidate, "ttft_ms")
        net_ttft = contract_ttft + verifier_per_request
        raw_prefill = mean(raw, "new_prefill_tokens")
        contract_prefill = mean(candidate, "new_prefill_tokens")
        result.append(
            {
                "model": model,
                "family": family,
                "safe_max_level": "L3*" if passed else "L0",
                "certificate_coverage": passed / sessions if sessions else 0.0,
                "new_prefill_reduction": (raw_prefill - contract_prefill) / raw_prefill if raw_prefill else 0.0,
                "raw_mean_ttft_ms": raw_ttft,
                "contract_mean_ttft_ms": contract_ttft,
                "net_mean_ttft_ms": net_ttft,
                "net_ttft_reduction": (raw_ttft - net_ttft) / raw_ttft if raw_ttft else 0.0,
                "completion_rate": sum(bool(row.get("success")) for row in candidate) / len(candidate) if candidate else 0.0,
                "quality_violation_rate": sum(as_float(row.get("quality_drop_vs_raw")) > 0.03 for row in candidate)
                / len(candidate)
                if candidate
                else 0.0,
                "sessions": sessions,
                "future_requests": len(candidate),
                "level_evidence": "L3*=full compiled candidate behind a per-session certificate; L1/L2 were not separately calibrated",
                "claim_boundary": "Fresh live vLLM held-out replay at the model's main concurrency; task-sanity quality, not official full benchmark scoring.",
            }
        )
    return result


def llama_family_map(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in load_csv(path):
        if row.get("scope") in {"all", "qualified_subset"}:
            continue
        family = FAMILY_NAMES.get(tuple(row["scope"].split(":", 1)), "Unknown")
        result.append(
            {
                "model": "Llama-3.1-8B-Instruct",
                "family": family,
                "safe_max_level": row["frozen_level"],
                "certificate_coverage": as_float(row["certificate_session_coverage"]),
                "new_prefill_reduction": as_float(row["new_prefill_reduction"]),
                "raw_mean_ttft_ms": as_float(row["raw_mean_ttft_ms"]),
                "contract_mean_ttft_ms": as_float(row["contract_mean_ttft_ms"]),
                "net_mean_ttft_ms": as_float(row["raw_mean_ttft_ms"])
                * (1.0 - as_float(row["net_mean_ttft_reduction"])),
                "net_ttft_reduction": as_float(row["net_mean_ttft_reduction"]),
                "completion_rate": as_float(row["completion_rate"]),
                "quality_violation_rate": as_float(row["policy_attributable_quality_violations"])
                / max(as_float(row["future_requests"]), 1.0),
                "sessions": int(as_float(row["sessions"])),
                "future_requests": int(as_float(row["future_requests"])),
                "level_evidence": "Prospective L0-L3 development qualification followed by three fresh-process sealed held-out repeats",
                "claim_boundary": "Fresh live vLLM held-out replay; frozen family level and per-session descent; task-sanity quality, not official full benchmark scoring.",
            }
        )
    return sorted(result, key=lambda row: FAMILY_ORDER.index(row["family"]))


def runtime_failure_rows(
    model: str,
    rows: list[dict[str, Any]],
    load_tier: str | None,
) -> list[dict[str, Any]]:
    if load_tier is not None:
        rows = [row for row in rows if row.get("load_tier") == load_tier]
    canaries = [row for row in rows if row.get("row_type") == "canary" and row.get("policy") == "contractkv-full"]
    future = [row for row in rows if row.get("row_type") == "future" and row.get("policy") == "contractkv-full"]
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        family_canaries = [row for row in canaries if family_name(row) == family]
        family_future = [row for row in future if family_name(row) == family]
        passes = sum(row.get("verify_decision") == "PASS" for row in family_canaries)
        incomplete = sum(
            row.get("verify_decision") == "INCOMPLETE" or "finish_reason=length" in str(row.get("error_message", ""))
            for row in family_canaries
        )
        generic_fail = sum(row.get("verify_decision") == "FAIL" for row in family_canaries)
        unsafe_sessions = {
            str(row.get("session_id"))
            for row in family_future
            if as_float(row.get("quality_drop_vs_raw")) > 0.03
        }
        result.append(
            {
                "model": model,
                "family": family,
                "evidence_scope": "final_heldout_runtime_canary",
                "evaluated_sessions": len(family_canaries),
                "certificate_pass": passes,
                "top1_path_mismatch": "",
                "target_absent": "",
                "length_stop": incomplete,
                "quality_gate_failure": len(unsafe_sessions),
                "scope_mismatch": sum(bool(row.get("certificate_scope_errors")) for row in family_future),
                "raw_fallback": len(family_canaries) - passes,
                "unclassified_verifier_fail": generic_fail,
                "detail_availability": "Historical compact rows retained PASS/FAIL but not the FAIL subreason; no exact top1/target split is claimed.",
            }
        )
    return result


def llama_runtime_failure_rows(path: Path) -> list[dict[str, Any]]:
    canaries = [row for row in load_jsonl(path) if row.get("row_type") == "canary"]
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        rows = [row for row in canaries if family_name(row) == family]
        passes = sum(row.get("verify_decision") == "PASS" for row in rows)
        not_required = sum(row.get("verify_decision") == "NOT_REQUIRED" for row in rows)
        rejected = sum(row.get("verify_decision") == "REJECTED_ALL_LEVELS" for row in rows)
        result.append(
            {
                "model": "Llama-3.1-8B-Instruct",
                "family": family,
                "evidence_scope": "final_heldout_runtime_canary_repeat1",
                "evaluated_sessions": len(rows),
                "certificate_pass": passes,
                "top1_path_mismatch": "",
                "target_absent": "",
                "length_stop": sum(bool(row.get("length_stop")) for row in rows),
                "quality_gate_failure": 0,
                "scope_mismatch": 0,
                "raw_fallback": not_required + rejected,
                "unclassified_verifier_fail": rejected,
                "detail_availability": "L0 families require no verifier; rejected descent attempts retained decisions but not token-path subreasons.",
            }
        )
    return result


def qwen_diagnostic_failures(path: Path) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv(path):
        grouped[family_name(row)].append(row)
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        rows = grouped.get(family, [])
        result.append(
            {
                "model": "Qwen3-8B",
                "family": family,
                "evidence_scope": "phase17_candidate_token_path_diagnostic",
                "evaluated_sessions": len(rows),
                "certificate_pass": sum(row.get("verification_status") == "PASS" for row in rows),
                "top1_path_mismatch": sum("top1_path_mismatch" in row.get("failure_reason", "") for row in rows),
                "target_absent": sum("target token" in row.get("failure_reason", "") for row in rows),
                "length_stop": sum(row.get("verification_status") == "INCOMPLETE" for row in rows),
                "quality_gate_failure": "",
                "scope_mismatch": "",
                "raw_fallback": "",
                "unclassified_verifier_fail": sum(
                    row.get("verification_status") == "FAIL" and not row.get("failure_reason") for row in rows
                ),
                "detail_availability": "Exact candidate-token diagnostic; not the Phase19 held-out runtime canary population.",
            }
        )
    return result


def token_audit_failures(model: str, path: Path, scope: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_jsonl(path):
        grouped[family_name(row)].append(row)
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        rows = grouped.get(family, [])
        mismatch_flags = [any(int(rank) != 1 for rank in row.get("target_ranks", [])) for row in rows]
        top1 = sum(mismatch_flags)
        absent = sum(as_float(row.get("target_absent_position", -1)) >= 0 for row in rows)
        result.append(
            {
                "model": model,
                "family": family,
                "evidence_scope": scope,
                "evaluated_sessions": len(rows),
                "certificate_pass": sum(not mismatch for mismatch in mismatch_flags),
                "top1_path_mismatch": top1,
                "target_absent": absent,
                "length_stop": sum(row.get("taxonomy") == "LENGTH_STOP" for row in rows),
                "quality_gate_failure": "",
                "scope_mismatch": "",
                "raw_fallback": "",
                "unclassified_verifier_fail": 0,
                "detail_availability": "Exact diagnostic subset; kept separate from final held-out runtime counts.",
            }
        )
    return result


def quality_gate_diagnostic_rows(
    model: str,
    rows: list[dict[str, Any]],
    evidence_scope: str,
    violation_key: str,
    row_filter: Any,
) -> list[dict[str, Any]]:
    selected = [row for row in rows if row_filter(row)]
    result: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        family_rows = [row for row in selected if family_name(row) == family]
        sessions = {str(row.get("session_id")) for row in family_rows}
        unsafe = {
            str(row.get("session_id"))
            for row in family_rows
            if is_true(row.get(violation_key))
            or (violation_key == "quality_drop_vs_raw" and as_float(row.get(violation_key)) > 0.03)
        }
        result.append(
            {
                "model": model,
                "family": family,
                "evidence_scope": evidence_scope,
                "evaluated_sessions": len(sessions),
                "certificate_pass": "",
                "top1_path_mismatch": "",
                "target_absent": "",
                "length_stop": "",
                "quality_gate_failure": len(unsafe),
                "scope_mismatch": "",
                "raw_fallback": "",
                "unclassified_verifier_fail": "",
                "detail_availability": "Candidate-quality diagnostic only; failures are not admitted by the final ContractKV policy.",
            }
        )
    return result


def ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = (cursor + end - 1) / 2.0 + 1.0
        for index, _ in indexed[cursor:end]:
            result[index] = average_rank
        cursor = end
    return result


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else 0.0


def margin_analysis(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = [row for row in load_csv(path) if row.get("verification_status") in {"PASS", "FAIL", "INCOMPLETE"}]
    rows: list[dict[str, Any]] = []
    for status in ["PASS", "FAIL", "INCOMPLETE"]:
        selected = [row for row in source if row.get("verification_status") == status]
        rows.append(
            {
                "group_type": "verification_status",
                "group": status,
                "samples": len(selected),
                "pass_rate": sum(row.get("verification_status") == "PASS" for row in selected) / max(len(selected), 1),
                "mean_raw_margin_q05": mean(selected, "raw_margin_q05"),
                "mean_candidate_margin_q05": mean(selected, "candidate_margin_q05"),
                "mean_margin_degradation_q95": mean(selected, "degradation_q95"),
                "mean_expected_prefix_gain": mean(selected, "expected_prefix_gain"),
                "claim_boundary": "Phase17 Qwen candidate diagnostic correlation; not a model-architecture causal explanation.",
            }
        )
    ordered = sorted(source, key=lambda row: as_float(row.get("expected_prefix_gain")))
    for index, label in enumerate(["low_aggressiveness", "medium_aggressiveness", "high_aggressiveness"]):
        start = round(index * len(ordered) / 3)
        end = round((index + 1) * len(ordered) / 3)
        selected = ordered[start:end]
        rows.append(
            {
                "group_type": "expected_prefix_gain_tertile",
                "group": label,
                "samples": len(selected),
                "pass_rate": sum(row.get("verification_status") == "PASS" for row in selected) / max(len(selected), 1),
                "mean_raw_margin_q05": mean(selected, "raw_margin_q05"),
                "mean_candidate_margin_q05": mean(selected, "candidate_margin_q05"),
                "mean_margin_degradation_q95": mean(selected, "degradation_q95"),
                "mean_expected_prefix_gain": mean(selected, "expected_prefix_gain"),
                "claim_boundary": "Phase17 Qwen candidate diagnostic correlation; not a model-architecture causal explanation.",
            }
        )
    pass_vector = [1.0 if row.get("verification_status") == "PASS" else 0.0 for row in source]
    candidate_margin = [as_float(row.get("candidate_margin_q05")) for row in source]
    raw_margin = [as_float(row.get("raw_margin_q05")) for row in source]
    degradation = [as_float(row.get("degradation_q95")) for row in source]
    gain = [as_float(row.get("expected_prefix_gain")) for row in source]
    summary = {
        "model": "Qwen3-8B",
        "samples": len(source),
        "candidate_margin_vs_pass_pearson": pearson(candidate_margin, pass_vector),
        "candidate_margin_vs_pass_spearman": pearson(ranks(candidate_margin), ranks(pass_vector)),
        "raw_margin_vs_pass_pearson": pearson(raw_margin, pass_vector),
        "margin_degradation_vs_pass_pearson": pearson(degradation, pass_vector),
        "expected_prefix_gain_vs_pass_pearson": pearson(gain, pass_vector),
        "wording": "Lower token-path robustness is associated with lower safe layout aggressiveness.",
        "claim_boundary": "Correlation only. These diagnostics do not establish a model-architecture root cause.",
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/cross_model"))
    parser.add_argument("--llama-compact", type=Path, default=None)
    args = parser.parse_args()

    qwen_live = Path("results/end_to_end/phase19b_task_replay_raw_v0.jsonl")
    mistral_raw = Path("results/mistral/heldout_raw_order_v0.jsonl")
    mistral_contract = Path("results/mistral/heldout_contractkv_v0.jsonl")
    llama_scope = Path("results/cross_model/llama_broad_generalization_r3/heldout_scope_aggregate_v0.csv")
    qwen_margin = Path("results/hard_systems/phase17_calibration_candidate_margins_v2.csv")
    llama_audit = Path("results/cross_model/phase20b_llama_rejection_audit_v0.jsonl")
    mistral_audit = Path(".artifacts/phase24/mistral-protocol-audit.jsonl")
    llama_compact = args.llama_compact or Path(".artifacts/phase24/llama-r1-contract.jsonl")
    external_snapshot = args.output_dir / "phase24_external_failure_evidence_v0.csv"
    frozen_external = load_csv(external_snapshot) if external_snapshot.exists() else []

    qwen_rows = load_jsonl(qwen_live)
    qwen_summary_rows = load_csv(Path("results/end_to_end/phase19b_task_replay_summary_v0.csv"))
    qwen_target_overhead = next(
        as_float(row["unhidden_verifier_ms_per_future_request"])
        for row in qwen_summary_rows
        if row.get("policy") == "contractkv-full" and row.get("load_tier") == "transition"
    )
    qualification_map = live_family_map(
        "Qwen3-8B", qwen_rows, qwen_rows, "transition", qwen_target_overhead
    )
    mistral_summary = json.loads(Path("results/mistral/heldout_summary_v0.json").read_text(encoding="utf-8"))
    qualification_map.extend(
        live_family_map(
            "Mistral-7B-Instruct-v0.3",
            load_jsonl(mistral_raw),
            load_jsonl(mistral_contract),
            None,
            as_float(mistral_summary["contractkv"]["unhidden_verifier_ms_per_request"]),
        )
    )
    qualification_map.extend(llama_family_map(llama_scope))
    qualification_map.sort(key=lambda row: (["Qwen3-8B", "Mistral-7B-Instruct-v0.3", "Llama-3.1-8B-Instruct"].index(row["model"]), FAMILY_ORDER.index(row["family"])))
    write_csv(args.output_dir / "phase24_cross_model_qualification_map_v0.csv", qualification_map)

    ablation_dev = load_csv(Path("results/cross_model/llama_broad_generalization_r3/layout_ladder_ablation_v0.csv"))
    ablation_heldout = load_csv(Path("results/cross_model/llama_broad_generalization_r3/layout_ladder_heldout_descent_ablation_v0.csv"))
    ablation_rows: list[dict[str, Any]] = []
    for row in ablation_dev:
        ablation_rows.append({"partition": "development", **row})
    for row in ablation_heldout:
        if row.get("repeat") == "aggregate":
            ablation_rows.append({"partition": "sealed_heldout", **row})
    write_csv(args.output_dir / "phase24_layout_aggressiveness_ablation_v0.csv", ablation_rows)

    cost = load_csv(Path("results/cross_model/llama_broad_generalization_r3/qualification_cost_v0.csv"))
    write_csv(args.output_dir / "phase24_qualification_cost_v0.csv", cost)
    stability = [
        row
        for row in load_csv(Path("results/cross_model/llama_broad_generalization_r3/qualification_sample_stability_v0.csv"))
        if int(row["samples_per_family"]) in {1, 2, 3, 5}
    ]
    write_csv(args.output_dir / "phase24_qualification_stability_1_2_3_5_v0.csv", stability)

    failure_rows = runtime_failure_rows("Qwen3-8B", qwen_rows, "transition")
    failure_rows.extend(runtime_failure_rows("Mistral-7B-Instruct-v0.3", load_jsonl(mistral_contract), None))
    external_rows: list[dict[str, Any]] = []
    if llama_compact.exists():
        external_rows.extend(llama_runtime_failure_rows(llama_compact))
    else:
        external_rows.extend(
            row
            for row in frozen_external
            if row.get("model") == "Llama-3.1-8B-Instruct"
            and row.get("evidence_scope") == "final_heldout_runtime_canary_repeat1"
        )
    failure_rows.extend(external_rows)
    failure_rows.extend(qwen_diagnostic_failures(qwen_margin))
    failure_rows.extend(token_audit_failures("Llama-3.1-8B-Instruct", llama_audit, "phase20b_rejected_safe_diagnostic"))
    if mistral_audit.exists():
        mistral_external = token_audit_failures(
            "Mistral-7B-Instruct-v0.3", mistral_audit, "phase21_protocol_smoke_diagnostic"
        )
    else:
        mistral_external = [
            row
            for row in frozen_external
            if row.get("model") == "Mistral-7B-Instruct-v0.3"
            and row.get("evidence_scope") == "phase21_protocol_smoke_diagnostic"
        ]
    external_rows.extend(mistral_external)
    failure_rows.extend(mistral_external)
    failure_rows.extend(
        quality_gate_diagnostic_rows(
            "Qwen3-8B",
            qwen_rows,
            "phase19_unguarded_physical_candidate_quality",
            "quality_drop_vs_raw",
            lambda row: row.get("row_type") == "future"
            and row.get("load_tier") == "transition"
            and row.get("policy") == "physical-cache-aware",
        )
    )
    failure_rows.extend(
        quality_gate_diagnostic_rows(
            "Mistral-7B-Instruct-v0.3",
            load_csv(Path("results/mistral/development_quality_v0.csv")),
            "development_unguarded_physical_candidate_quality",
            "quality_violation",
            lambda row: row.get("policy") == "physical-cache-aware",
        )
    )
    failure_rows.extend(
        quality_gate_diagnostic_rows(
            "Llama-3.1-8B-Instruct",
            load_csv(Path("results/cross_model/llama_broad_generalization_r3/development_quality_v0.csv")),
            "development_L3_candidate_quality",
            "policy_attributable_quality_violation",
            lambda row: row.get("level") == "L3",
        )
    )
    write_csv(external_snapshot, external_rows)
    write_csv(args.output_dir / "phase24_certificate_failure_reasons_v0.csv", failure_rows)

    margin_rows, margin_summary = margin_analysis(qwen_margin)
    write_csv(args.output_dir / "phase24_margin_correlation_v0.csv", margin_rows)
    write_json(args.output_dir / "phase24_margin_correlation_summary_v0.json", margin_summary)

    tracked_inputs = [
        qwen_live,
        mistral_raw,
        mistral_contract,
        Path("results/mistral/heldout_summary_v0.json"),
        Path("results/end_to_end/phase19b_task_replay_summary_v0.csv"),
        llama_scope,
        qwen_margin,
        llama_audit,
        external_snapshot,
    ]
    external_inputs = [path for path in [llama_compact, mistral_audit] if path.exists()]
    summary_path = args.output_dir / "phase24_why_when_summary_v0.json"
    previous_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    external_hashes = {str(path): sha256(path) for path in external_inputs}
    if not external_hashes:
        external_hashes = previous_summary.get("external_raw_source_sha256", {})
    summary = {
        "schema_version": "contractkv.phase24.why_when.v1",
        "qualification_map_rows": len(qualification_map),
        "models": sorted({row["model"] for row in qualification_map}),
        "families": FAMILY_ORDER,
        "ablation_rows": len(ablation_rows),
        "failure_reason_rows": len(failure_rows),
        "margin_samples": margin_summary["samples"],
        "source_sha256": {str(path): sha256(path) for path in tracked_inputs},
        "external_raw_source_sha256": external_hashes,
        "claim_boundary": [
            "Qualification-map performance comes from fresh live vLLM held-out replays.",
            "Qwen and Mistral L3* denote the full compiled candidate; unlike Llama, L1/L2 were not separately calibrated.",
            "Failure subreasons from diagnostic subsets are not merged into final-runtime canary counts.",
            "Margin analysis is correlational and does not establish a model-architecture root cause.",
        ],
    }
    write_json(summary_path, summary)


if __name__ == "__main__":
    main()
