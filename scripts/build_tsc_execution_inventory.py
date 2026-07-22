#!/usr/bin/env python3
"""Build a hash-addressed inventory of non-test code used by the six tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TASKS = {
    "1": {
        "code": [
            "scripts/phase22_llama_broad_live.py",
            "scripts/run_external_llama_radix_replay.py",
            "scripts/run_llama_direct_vllm_baselines.sh",
            "scripts/run_external_llama_sglang_baseline.sh",
            "scripts/run_llama_lmcache_baselines.sh",
            "scripts/run_llama_lmcache_baselines_serial.sh",
            "scripts/run_llama_cacheblend_after_lmcache.sh",
            "scripts/run_llama_lmcache_resume_after_cacheblend.sh",
            "scripts/setup_cacheblend_legacy_env.sh",
            "scripts/check_lmcache_separator.py",
            "scripts/audit_lmcache_segment_identity.py",
            "scripts/audit_cacheblend_compatibility.py",
            "scripts/patch_flashinfer_sparse_import.py",
            "scripts/run_cacheslide_llama_smoke.py",
            "scripts/run_cacheslide_artifact_smoke.py",
            "scripts/patch_cacheblend_llama31_compat.py",
            "scripts/patch_lmcache_cacheblend_fp16.py",
            "third_party/patches/lmcache_cacheblend_v0102/sitecustomize.py",
            "scripts/summarize_lmcache_runtime_logs.py",
            "scripts/summarize_llama_sota_matrix.py",
        ],
        "evidence": [
            "results/tsc_closure/llama_sota_matrix_v1.json",
            "results/external_baseline/llama_lmcache_v1/runtime_accounting_v1.json",
            "results/external_baseline/artifact_audit/cacheblend_compatibility_v1.json",
            "results/external_baseline/artifact_audit/cacheslide_llama_smoke_v1.json",
        ],
    },
    "2": {
        "code": [
            "scripts/tsc_real_task_open_loop.py",
            "scripts/run_tsc_real_task_open_loop.sh",
            "scripts/run_tsc_real_task_open_loop_serial.sh",
            "scripts/summarize_tsc_real_task_open_loop.py",
            "scripts/run_vllm_server.sh",
            "scripts/stop_vllm_server.sh",
        ],
        "evidence": ["results/tsc_closure/real_task_open_loop_summary_v1.json"],
    },
    "3": {
        "code": [
            "scripts/run_tsc_net_benefit_heldout.sh",
            "scripts/summarize_tsc_net_benefit_gate.py",
            "scripts/phase22_llama_broad_live.py",
        ],
        "evidence": ["results/tsc_service/economics/heldout_gate_v1_summary.json"],
    },
    "4": {
        "code": [
            "scripts/contractkv_certificate_binding.py",
            "scripts/certificate_binding_stress.py",
        ],
        "evidence": ["results/tsc_closure/certificate_binding_stress_v1.json"],
    },
    "5": {
        "code": ["scripts/pstp_transaction_stress.py"],
        "evidence": [
            "results/tsc_closure/pstp_state_machine_stress_v2.json",
            "results/hard_systems/phase17_concurrency_fault_v0.csv",
        ],
    },
    "6": {
        "code": [
            "scripts/tsc_real_task_open_loop.py",
            "scripts/run_tsc_real_task_open_loop.sh",
            "scripts/run_tsc_real_task_open_loop_serial.sh",
            "scripts/summarize_tsc_real_task_open_loop.py",
        ],
        "evidence": ["results/tsc_closure/real_task_open_loop_summary_v1.json"],
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tasks = []
    for task, spec in TASKS.items():
        code = []
        for relative in spec["code"]:
            path = args.root / relative
            code.append({"path": relative, "present": path.is_file(),
                         "sha256": sha256(path) if path.is_file() else None})
        evidence = [{"path": relative, "present": (args.root / relative).is_file()}
                    for relative in spec["evidence"]]
        tasks.append({"task": int(task), "code": code, "evidence": evidence,
                      "all_code_present": all(row["present"] for row in code),
                      "all_evidence_present": all(row["present"] for row in evidence)})
    payload = {
        "schema_version": "contractkv.tsc-executed-code-inventory.v1",
        "tests_excluded": True,
        "tasks": tasks,
        "claim_boundary": "The inventory lists experiment, patch, orchestration, and summarization code that participated in the recorded artifacts; unit-test files are intentionally omitted.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all(row["all_code_present"] and row["all_evidence_present"] for row in tasks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
