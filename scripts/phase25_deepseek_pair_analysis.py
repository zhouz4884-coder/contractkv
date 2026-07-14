#!/usr/bin/env python3
"""Validate and summarize the frozen DeepSeek-V2-Lite paired experiment."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


FAMILY_NAMES = {
    "RULER:niah_single_1": "RULER",
    "LongBench:hotpotqa": "HotpotQA",
    "LongBench:narrativeqa": "NarrativeQA",
    "LongBench:qasper": "Qasper",
    "RepoBench:python_v1.1": "RepoBench",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    for row in rows[1:]:
        fields.extend(key for key in row if key not in fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def family(row: dict[str, Any]) -> str:
    return f"{row.get('dataset', '')}:{row.get('task', '')}"


def validate_cell(path: Path, sessions: int, turns: int) -> dict[str, Any]:
    rows = load_jsonl(path)
    canaries = [row for row in rows if row.get("row_type") == "canary"]
    future = [row for row in rows if row.get("row_type") == "future"]
    expected_future = sessions * (turns - 1)
    checks = {
        "row_count": len(rows) == sessions * turns,
        "canary_count": len(canaries) == sessions,
        "future_count": len(future) == expected_future,
        "future_completion": len(future) == expected_future and all(row.get("success") is True for row in future),
        "scope_invalid_admissions_zero": all(
            row.get("effective_level") == "L0" or row.get("certificate_scope_valid") is True for row in future
        ),
        "dynamic_suffix_reuse_zero": all(int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) == 0 for row in future),
        "prefix_metrics_present": bool(future)
        and all(row.get("prefix_hit_tokens") not in {None, ""} for row in future),
        "physical_block_metrics_present": bool(future)
        and all(row.get("physical_block_count") not in {None, ""} for row in future),
    }
    return {
        "path": str(path),
        "sessions": sessions,
        "turns": turns,
        "rows": len(rows),
        "canaries": len(canaries),
        "future_requests": len(future),
        "checks": checks,
        "pass": all(checks.values()),
    }


def preflight(args: argparse.Namespace) -> int:
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    config = json.loads(args.model_config.read_text(encoding="utf-8"))
    cell = validate_cell(args.cell, args.sessions, args.turns)
    rows = load_jsonl(args.cell)
    canaries = [row for row in rows if row.get("row_type") == "canary"]
    future = [row for row in rows if row.get("row_type") == "future"]
    fault_rows = load_csv(args.fault_probe)
    evaluated = [row for row in canaries if row.get("verify_decision") not in {"", "INCOMPLETE", "NOT_REQUIRED"}]
    aborted = [row for row in fault_rows if row.get("txn_state") == "ABORTED"]
    checks = {
        "architecture_is_deepseek_v2": config.get("architectures") == ["DeepseekV2ForCausalLM"],
        "mla_kv_rank_present": int(config.get("kv_lora_rank", 0) or 0) > 0,
        "tp2_frozen": int(protocol["runtime"]["tensor_parallel_size"]) == 2,
        "cell_valid": cell["pass"],
        "compact_verifier_transport_ok": len(evaluated) == len(canaries),
        "pstp_stable_prefix_observed": any(int(row.get("certified_stable_prefix_tokens", 0) or 0) > 0 for row in canaries),
        "real_prefix_block_metrics_readable": bool(future)
        and all(int(row.get("physical_block_count", 0) or 0) > 0 for row in future),
        "dynamic_suffix_reuse_zero": all(int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) == 0 for row in future),
        "fault_probe_complete": bool(fault_rows) and all(as_bool(row.get("gate_pass")) for row in fault_rows),
        "abort_paths_publish_zero": bool(aborted)
        and all(
            int(row.get("cache_entries_delta", 0) or 0) == 0
            and not as_bool(row.get("certificate_issued"))
            for row in aborted
        ),
        "mla_bytes_not_inferred": protocol["mla_measurement_boundary"]["memory_gib_claim_allowed"] is False,
    }
    payload = {
        "schema_version": "contractkv.phase25.deepseek-preflight.v1",
        "model_key": args.model_key,
        "model_path": str(args.model_config.parent),
        "architecture": config.get("architectures", []),
        "kv_lora_rank": config.get("kv_lora_rank"),
        "tensor_parallel_size": 2,
        "sessions": args.sessions,
        "future_requests": len(future),
        "verifier_decisions": dict(Counter(str(row.get("verify_decision", "")) for row in canaries)),
        "mean_physical_block_count": statistics.fmean(
            int(row.get("physical_block_count", 0) or 0) for row in future
        ) if future else 0.0,
        "max_physical_block_count": max((int(row.get("physical_block_count", 0) or 0) for row in future), default=0),
        "max_dynamic_suffix_reuse_tokens": max(
            (int(row.get("dynamic_suffix_reuse_tokens", 0) or 0) for row in future), default=0
        ),
        "fault_cases": len(fault_rows),
        "aborted_fault_cases": len(aborted),
        "kv_bytes_per_block": "unavailable_MLA_geometry_not_validated",
        "checks": checks,
        "pass": all(checks.values()),
        "claim_boundary": "Real vLLM V1 TP=2 compatibility and block telemetry; no GQA-to-MLA byte conversion.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


def model_summary(model_key: str, model_dir: Path, protocol: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((model_dir / "qualification_manifest_v0.json").read_text(encoding="utf-8"))
    gate = json.loads((model_dir / "heldout_gate_v0.json").read_text(encoding="utf-8"))
    aggregate = load_csv(model_dir / "heldout_scope_aggregate_v0.csv")
    all_row = next(row for row in aggregate if row["scope"] == "all")
    repo_row = next(row for row in aggregate if row["scope"] == "RepoBench:python_v1.1")
    paths = [model_dir / f"repeat{repeat}" / f"r{repeat}-contract.jsonl" for repeat in (1, 2, 3)]
    future = [row for path in paths for row in load_jsonl(path) if row.get("row_type") == "future"]
    primary = protocol["primary_gates"]
    primary_checks = {
        "completion_100": as_float(all_row["completion_rate"]) == as_float(primary["completion_rate"]),
        "quality_violations_zero": as_float(all_row["policy_attributable_quality_violations"]) == 0,
        "scope_invalid_zero": as_float(all_row["scope_invalid_admissions"]) == 0,
        "dynamic_suffix_zero": as_float(all_row["max_dynamic_suffix_reuse_tokens"]) == 0,
        "certificate_coverage": as_float(all_row["certificate_session_coverage"])
        >= as_float(primary["minimum_certificate_coverage"]),
        "new_prefill_reduction": as_float(all_row["new_prefill_reduction"])
        >= as_float(primary["minimum_new_prefill_reduction"]),
        "net_mean_ttft_reduction": as_float(all_row["net_mean_ttft_reduction"])
        >= as_float(primary["minimum_net_mean_ttft_reduction"]),
    }
    repo_level = str(manifest["frozen_family_levels"].get("RepoBench:python_v1.1", "L0"))
    repo_checks = {
        "frozen_level_gt_L0": repo_level != "L0",
        "certificate_coverage_ge_50pct": as_float(repo_row["certificate_session_coverage"]) >= 0.5,
        "quality_violations_zero": as_float(repo_row["policy_attributable_quality_violations"]) == 0,
        "net_ttft_benefit_positive": as_float(repo_row["net_mean_ttft_reduction"]) > 0,
    }
    summary = {
        "model_key": model_key,
        "model_id": protocol["models"][model_key]["model_id"],
        "specialization": protocol["models"][model_key]["specialization"],
        "qualified_family_count": sum(level != "L0" for level in manifest["frozen_family_levels"].values()),
        "frozen_levels": json.dumps(manifest["frozen_family_levels"], sort_keys=True),
        "completion_rate": as_float(all_row["completion_rate"]),
        "certificate_coverage": as_float(all_row["certificate_session_coverage"]),
        "new_prefill_reduction": as_float(all_row["new_prefill_reduction"]),
        "net_mean_ttft_reduction": as_float(all_row["net_mean_ttft_reduction"]),
        "p95_ttft_reduction": as_float(all_row["p95_ttft_reduction"]),
        "slo_goodput_gain": as_float(all_row["slo_goodput_gain"]),
        "policy_quality_violations": as_float(all_row["policy_attributable_quality_violations"]),
        "scope_invalid_admissions": as_float(all_row["scope_invalid_admissions"]),
        "max_dynamic_suffix_reuse_tokens": as_float(all_row["max_dynamic_suffix_reuse_tokens"]),
        "certified_prefix_reuse": as_float(all_row["certified_prefix_reuse"]),
        "mean_physical_block_count": statistics.fmean(
            as_float(row.get("physical_block_count")) for row in future
        ) if future else 0.0,
        "max_physical_block_count": max((as_float(row.get("physical_block_count")) for row in future), default=0.0),
        "kv_bytes_per_block": "unavailable_MLA_geometry_not_validated",
        "primary_gate_pass": all(primary_checks.values()),
        "primary_checks": json.dumps(primary_checks, sort_keys=True),
        "repobench_frozen_level": repo_level,
        "repobench_certificate_coverage": as_float(repo_row["certificate_session_coverage"]),
        "repobench_net_ttft_reduction": as_float(repo_row["net_mean_ttft_reduction"]),
        "repobench_quality_violations": as_float(repo_row["policy_attributable_quality_violations"]),
        "repobench_secondary_pass": all(repo_checks.values()),
        "repobench_checks": json.dumps(repo_checks, sort_keys=True),
    }
    family_rows = []
    for row in aggregate:
        if row["scope"] not in FAMILY_NAMES:
            continue
        family_rows.append({
            "model_key": model_key,
            "model_id": summary["model_id"],
            "family": FAMILY_NAMES[row["scope"]],
            "frozen_level": manifest["frozen_family_levels"].get(row["scope"], "L0"),
            "certificate_coverage": as_float(row["certificate_session_coverage"]),
            "completion_rate": as_float(row["completion_rate"]),
            "new_prefill_reduction": as_float(row["new_prefill_reduction"]),
            "net_mean_ttft_reduction": as_float(row["net_mean_ttft_reduction"]),
            "p95_ttft_reduction": as_float(row["p95_ttft_reduction"]),
            "slo_goodput_gain": as_float(row["slo_goodput_gain"]),
            "policy_quality_violations": as_float(row["policy_attributable_quality_violations"]),
            "max_dynamic_suffix_reuse_tokens": as_float(row["max_dynamic_suffix_reuse_tokens"]),
        })
    return summary, family_rows


def summarize(args: argparse.Namespace) -> int:
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    summaries = []
    families = []
    for key, path in (("chat", args.chat_dir), ("coder", args.coder_dir)):
        summary, rows = model_summary(key, path, protocol)
        summaries.append(summary)
        families.extend(rows)
    chat = next(row for row in summaries if row["model_key"] == "chat")
    coder = next(row for row in summaries if row["model_key"] == "coder")
    interpretation = {
        "both_global_primary_gate_pass": bool(chat["primary_gate_pass"] and coder["primary_gate_pass"]),
        "moe_mla_architecture_generalization_supported": bool(chat["primary_gate_pass"] and coder["primary_gate_pass"]),
        "coder_repobench_secondary_pass": bool(coder["repobench_secondary_pass"]),
        "chat_repobench_secondary_pass": bool(chat["repobench_secondary_pass"]),
        "code_specialization_expands_repobench_scope": (
            coder["repobench_frozen_level"] != "L0"
            and (
                chat["repobench_frozen_level"] == "L0"
                or coder["repobench_certificate_coverage"] > chat["repobench_certificate_coverage"]
            )
        ),
        "mla_memory_bytes_claim": "not_made",
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.summary_output, summaries)
    write_csv(args.family_output, families)
    payload = {
        "schema_version": "contractkv.phase25.deepseek-pair-gate.v1",
        "models": summaries,
        "interpretation": interpretation,
        "pass": interpretation["both_global_primary_gate_pass"],
        "claim_boundary": "Fresh vLLM TP=2 paired-model results. MLA memory bytes remain unavailable; token/block and serving metrics are real.",
    }
    args.gate_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-cell")
    validate.add_argument("--cell", type=Path, required=True)
    validate.add_argument("--sessions", type=int, required=True)
    validate.add_argument("--turns", type=int, default=10)
    compat = sub.add_parser("preflight")
    compat.add_argument("--protocol", type=Path, required=True)
    compat.add_argument("--model-key", choices=["chat", "coder"], required=True)
    compat.add_argument("--model-config", type=Path, required=True)
    compat.add_argument("--cell", type=Path, required=True)
    compat.add_argument("--fault-probe", type=Path, required=True)
    compat.add_argument("--sessions", type=int, default=10)
    compat.add_argument("--turns", type=int, default=10)
    compat.add_argument("--output", type=Path, required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("--protocol", type=Path, required=True)
    summary.add_argument("--chat-dir", type=Path, required=True)
    summary.add_argument("--coder-dir", type=Path, required=True)
    summary.add_argument("--summary-output", type=Path, required=True)
    summary.add_argument("--family-output", type=Path, required=True)
    summary.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-cell":
        payload = validate_cell(args.cell, args.sessions, args.turns)
        print(json.dumps(payload, indent=2))
        return 0 if payload["pass"] else 1
    if args.command == "preflight":
        return preflight(args)
    return summarize(args)


if __name__ == "__main__":
    raise SystemExit(main())
