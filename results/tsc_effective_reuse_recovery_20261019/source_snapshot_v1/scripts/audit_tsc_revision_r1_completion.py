"""Requirement-level completion audit for the complete R1 experiment batch."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def live_cell(root: Path, name: str, expected: int) -> dict:
    directory = root / "cells" / name
    raw_path, summary_path = directory / "raw.jsonl", directory / "summary.json"
    if not raw_path.is_file() or not summary_path.is_file():
        return {"cell": name, "execution_complete": False, "reason": "missing_raw_or_summary"}
    summary = json.loads(summary_path.read_text())
    rows = read_jsonl(raw_path); futures = [r for r in rows if r.get("row_type") == "future"]
    ids = {(r.get("session_id"), r.get("turn_id")) for r in futures}
    canaries = [r for r in rows if r.get("row_type") == "canary"]
    rejected = [r for r in canaries if not r.get("certificate_issued")]
    findings = []
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != summary.get("source_sha256"):
        findings.append("raw_hash_mismatch")
    if len(futures) != expected or len(ids) != expected: findings.append("request_count_or_identity_mismatch")
    if len(canaries) != expected // 9 or len({r.get("session_id") for r in canaries}) != expected // 9:
        findings.append("canary_count_or_identity_mismatch")
    if any(not isinstance(r.get("registration_ms"), (int, float)) or
           not math.isfinite(r["registration_ms"]) or r["registration_ms"] < 0 for r in canaries):
        findings.append("full_registration_clock_missing_or_invalid")
    if sum(r.get("metric_join_success") is True for r in futures) != expected: findings.append("metric_join_incomplete")
    if sum(r.get("token_ids_available") is True for r in futures) != expected: findings.append("token_evidence_incomplete")
    if any(r.get("scope_invalid_admission") for r in futures): findings.append("scope_invalid_admission")
    if any(int(r.get("committed_tokens", 0) or 0) != 0 for r in rejected): findings.append("rejected_publication_nonzero")
    if any(r.get("certificate_issued") and r.get("raw_finish_reason") == "length" for r in canaries):
        findings.append("length_stop_admitted")
    return {"cell": name, "execution_complete": not findings, "findings": findings,
            "future_requests": len(futures), "successful_future_requests": sum(r.get("success") is True for r in futures),
            "generation_success_rate": sum(r.get("success") is True for r in futures) / max(len(futures), 1),
            "full_registration_records": len(canaries),
            "all_registration_clocks_present": all("registration_ms" in r for r in canaries),
            "source_sha256": summary.get("source_sha256")}


def service_cell(root: Path, name: str) -> dict:
    directory = root / "service" / name
    required = [directory / filename for filename in ("raw.jsonl", "summary.jsonl", "registration.jsonl", "metrics.jsonl")]
    if any(not path.is_file() for path in required):
        return {"cell": name, "execution_complete": False, "reason": "missing_service_file"}
    rows, summaries, registrations = read_jsonl(required[0]), read_jsonl(required[1]), read_jsonl(required[2])
    findings = []
    if len(rows) != 180 or len({(r["session_id"], r["turn_id"]) for r in rows}) != 180:
        findings.append("service_count_or_identity_mismatch")
    if {float(r["slo_ttft_ms"]) for r in summaries} != {500, 1000, 1500, 3000}:
        findings.append("missing_slo_bucket")
    if len(registrations) != 5: findings.append("registration_count_mismatch")
    if any(r.get("scope_invalid_admission") for r in rows): findings.append("scope_invalid_admission")
    if any(r.get("certificate_binding_valid") is not True for r in rows): findings.append("binding_failure")
    if any(r.get("metric_join_success") is not True for r in rows): findings.append("metric_join_incomplete")
    if any("registration_ms" not in r for r in registrations): findings.append("registration_clock_missing")
    return {"cell": name, "execution_complete": not findings, "findings": findings,
            "future_requests": len(rows), "successful_future_requests": sum(r.get("success") is True for r in rows),
            "registration_total_ms": sum(float(r.get("registration_ms", 0)) for r in registrations),
            "scope_invalid_admissions": sum(bool(r.get("scope_invalid_admission")) for r in rows),
            "source_sha256": hashlib.sha256(required[0].read_bytes()).hexdigest()}


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args(); entries = []
    for model in ("qwen", "mistral", "llama"):
        for repeat in (1, 2, 3):
            for policy in ("raw-order", "contractkv"):
                entries.append(live_cell(a.root, f"common-hotpot_{model}_r{repeat}_{policy}_b0", 270))
                for budget in (0, 512):
                    entries.append(live_cell(a.root, f"free-generation_{model}_r{repeat}_{policy}_b{budget}", 450))
    for repeat in (1, 2, 3):
        for policy in ("raw-order", "contractkv"):
            entries.append(live_cell(a.root, f"qwen14-full-cost_qwen14_r{repeat}_{policy}_b96", 225))
        for model in ("qwen", "mistral"):
            for policy in ("D0-native-apc", "D1-frozen-safe", "D2-template-contractkv"):
                entries.append(service_cell(a.root, f"zero-slack_{model}_r{repeat}_{policy}"))
    gate_path = a.root / "guard_probe_qwen_v1.jsonl"
    guard = {"execution_complete": False, "reason": "missing_live_guard_probe"}
    if gate_path.exists():
        rows = read_jsonl(gate_path)
        bad = [r for r in rows if r.get("raw_score", 0) > r.get("layout_only_score", 0)]
        guard = {"cases": len(rows), "execution_complete": len(rows) == 20,
                 "genuine_bad_layout_cases": len(bad),
                 "bad_layouts_rejected": sum(not r.get("certificate_issued") for r in bad),
                 "rejected_published_tokens": sum(int(r.get("committed_tokens", 0) or 0) for r in rows if not r.get("certificate_issued")),
                 "guard_safety_demonstrated": bool(bad) and all(not r.get("certificate_issued") and r["certified_effective_score"] == r["raw_score"] for r in bad)}
    compact_required = [
        "historical_audit_manifest_v1.json", "historical_full_cost_by_repeat_v1.csv",
        "historical_free_text_summary_v1.csv", "matched_baseline_audit_manifest_v1.json",
        "matched_baseline_quality_thresholds_v1.csv", "registration_manifest_summary_v1.json",
        "registration_manifest_cases_v1.csv", "segment_token_displacement_v1.csv",
        "segment_token_displacement_summary_v1.csv", "fresh_summary_manifest_v1.json",
        "fresh_paired_performance_v1.csv", "fresh_token_quality_pairs_v1.csv",
        "fresh_token_quality_summary_v1.csv", "common_hotpot_shared_cluster_ci_v1.csv",
    ]
    actual_guard_path = a.root / "guard_probe_qwen14_actual_v2.jsonl"
    actual_guard = {"execution_complete": False, "reason": "missing_fresh_post_decision_guard"}
    if actual_guard_path.exists():
        rows = read_jsonl(actual_guard_path)
        bad = [r for r in rows if r.get("raw_score", 0) > r.get("layout_only_score", 0)]
        actual_guard = {"cases": len(rows),
                        "execution_complete": len(rows) == 20 and all(r.get("effective_output_source") == "fresh_post_decision_request"
                                                                     and r.get("effective_success") is True
                                                                     and bool(r.get("effective_output_token_ids")) for r in rows),
                        "model": rows[0].get("model") if rows else "unavailable",
                        "genuine_bad_layout_cases": len(bad),
                        "bad_layouts_rejected": sum(not r.get("certificate_issued") for r in bad),
                        "fresh_protected_scores_equal_raw": all(r["certified_effective_score"] == r["raw_score"] for r in rows),
                        "rejected_published_tokens": sum(int(r.get("committed_tokens", 0) or 0) for r in rows if not r.get("certificate_issued"))}
    missing = [name for name in compact_required if not (a.root / name).is_file()]
    report = {"schema_version": "tsc-revision-completion-audit.v1", "data_root": str(a.root.resolve()),
              "no_remote_status_inferred_from_local_missing_files": True, "expected_live_cells": 78,
              "cells": entries, "complete_live_cells": sum(r["execution_complete"] for r in entries),
              "expected_measured_future_requests": 25650,
              "observed_measured_future_requests": sum(r.get("future_requests", 0) for r in entries),
              "live_guard": guard, "fresh_post_decision_guard": actual_guard, "missing_compact_artifacts": missing,
              "experimental_execution_complete": all(r["execution_complete"] for r in entries) and guard["execution_complete"] and actual_guard["execution_complete"] and not missing,
              "scientific_success_must_be_reported_separately": True,
              "full_goal_complete": False,
              "remaining_after_execution": ["quality/root-cause analysis", "complete reports", "source/code inventory", "remote cleanup", "tests/schema audit", "verified GitHub publication"],
              "boundary": "File presence alone does not prove execution. Completed experiments do not imply all desired performance or quality gates passed."}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cells"}))
    return 0 if report["experimental_execution_complete"] else 2

if __name__ == "__main__": raise SystemExit(main())
