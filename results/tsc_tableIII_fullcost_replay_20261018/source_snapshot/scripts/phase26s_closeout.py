#!/usr/bin/env python3
"""Build the compact, hash-bound Phase 26S paper evidence manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


EXECUTED_FILES = [
    "scripts/run_phase26r_observation_scoped.sh",
    "scripts/phase26r_observation_live.py",
    "scripts/phase26r_policy.py",
    "scripts/phase26r_typed_contracts.py",
    "scripts/phase26r_analysis.py",
    "scripts/phase26r_freeze_policy.py",
    "scripts/contractkv_verifier.py",
    "scripts/install_vllm_v1_compact_stop_margin.py",
    "scripts/install_vllm_v1_ephemeral_shadow_hook.py",
    "scripts/install_vllm_v1_prefix_metrics_probe.py",
    "scripts/run_vllm_server.sh",
    "scripts/stop_vllm_server.sh",
    "scripts/phase12_prefix_cache_ab.py",
    "scripts/phase19b_end_to_end_live.py",
    "scripts/phase26a_recoverability_audit.py",
    "scripts/phase17_live_common.py",
    "scripts/phase20a_official_quality.py",
    "scripts/phase22_llama_layout_ladder.py",
    "scripts/phase26r_prepare_fresh_heldout.py",
    "scripts/run_phase26r_observation_salt_smoke.sh",
    "scripts/phase26s_freeze_pilot_calibration.py",
    "scripts/phase26s_pilot_diagnosis.py",
    "scripts/phase26s_closeout.py",
]


def sha(path: Path) -> str:
    # Git normalizes tracked text artifacts to LF. Hash the canonical blob so
    # a fresh clone can reproduce the manifest on Windows or Linux.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary_path = args.result_dir / "heldout_scope_summary_v6.csv"
    gate_path = args.result_dir / "heldout_gate_v6.json"
    policy_path = args.result_dir / "frozen_observation_policy_v2.json"
    split_path = args.result_dir / "sealed" / "split_commitment_v6.json"
    summary = list(csv.DictReader(summary_path.open(encoding="utf-8")))
    aggregate = {row["mode"]: row for row in summary if row["repeat"] == "aggregate"}
    repeats = [row for row in summary if row["mode"] == "contract" and row["repeat"] != "aggregate"]
    tracked = [
        summary_path,
        args.result_dir / "heldout_family_summary_v6.csv",
        args.result_dir / "certificate_failure_taxonomy_v6.csv",
        gate_path, policy_path, split_path,
        args.result_dir / "pilot_failure_diagnosis_v5.json",
    ]
    payload: dict[str, Any] = {
        "schema_version": "contractkv.phase26s.result-manifest.v1",
        "status": "complete_bounded_deployment_region",
        "model": "DeepSeek-Coder-V2-Lite-Instruct",
        "runtime": {"vllm": "0.10.2-source-hook", "dtype": "bfloat16",
                    "tensor_parallel_size": 2, "gpu": "2 x RTX 3090",
                    "concurrency": 2, "fresh_process_pairs": 3},
        "formal_requests_per_policy": int(aggregate["contract"]["requests"]),
        "gate": json.loads(gate_path.read_text(encoding="utf-8")),
        "contract_repeat_metrics": [{
            "repeat": int(row["repeat"]),
            "net_mean_ttft_reduction": float(row["net_mean_ttft_reduction"]),
            "net_p95_ttft_reduction": float(row["net_p95_ttft_reduction"]),
            "new_prefill_reduction": float(row["new_prefill_reduction"]),
            "certificate_coverage": float(row["observation_certificate_coverage"]),
            "quality_violations": int(row["policy_quality_violations"]),
        } for row in repeats],
        "raw_evidence": {
            "location": "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/cross_model/deepseek_phase26r_scope_closure/heldout_v6",
            "request_traces": 4500,
            "git_policy": "large request traces and server logs remain on the 8T disk",
        },
        "executed_code_files_excluding_tests": EXECUTED_FILES,
        "artifact_sha256": {str(path.relative_to(args.result_dir.parent.parent.parent)): sha(path)
                            for path in tracked},
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["gate"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
