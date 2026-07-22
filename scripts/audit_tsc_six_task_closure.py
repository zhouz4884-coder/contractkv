#!/usr/bin/env python3
"""Audit the six frozen TSC experiment requirements from machine-readable evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "pass"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root

    sota = read_json(root / "results/tsc_closure/llama_sota_matrix_v1.json")
    cells = {row["cell"]: row for row in sota["cells"]}
    required_sota = ("vllm_apc", "manual_oracle", "contractkv", "sglang_raw",
                     "sglang_certified", "lmcache", "cacheblend_raw", "cacheblend",
                     "cacheslide")
    complete_sota = all(cells.get(name, {}).get("status") == "complete" and
                        int(cells[name].get("fresh_process_repeats", 0)) == 5 and
                        int(cells[name].get("completed_requests_per_repeat", 0)) == 450
                        for name in required_sota)
    cacheslide_blocked = cells.get("cacheslide", {}).get("status") == "external_artifact_blocked"

    service = read_json(root / "results/tsc_closure/real_task_open_loop_summary_v1.json")
    policies = {row["policy"]: row for row in service["rows"] if float(row["slo_ttft_ms"]) == 1500.0}
    service_complete = all(int(policies.get(name, {}).get("fresh_process_repeats", 0)) == 5 and
                           float(policies[name].get("completion_rate", 0)) == 1.0 and
                           float(policies[name].get("metric_join_rate", 0)) == 1.0
                           for name in ("D0-native-apc", "D1-frozen-safe", "D2-template-contractkv"))
    d2 = policies.get("D2-template-contractkv", {})
    in_engine_verify = (float(d2.get("actual_verifier_endpoint_calls", 0)) > 0 and
                        float(d2.get("registration_failures", 1)) == 0)
    service_safety = (float(d2.get("drop_rate", 1)) == 0 and
                      float(d2.get("scope_invalid_admissions", 1)) == 0 and
                      float(d2.get("certificate_binding_failures", 1)) == 0 and
                      float(d2.get("quality_drop_gt_0_03_rate", 1)) == 0)

    gate = read_json(root / "results/tsc_service/economics/heldout_gate_v1_summary.json")
    binding = read_json(root / "results/tsc_closure/certificate_binding_stress_v1.json")
    lifecycle = read_json(root / "results/tsc_service/lifecycle/lifecycle_summary_v0.json")
    pstp = read_json(root / "results/tsc_closure/pstp_state_machine_stress_v2.json")
    live = read_csv(root / "results/hard_systems/phase17_integrated_live_v0.csv")
    faults = read_csv(root / "results/hard_systems/phase17_concurrency_fault_v0.csv")
    pstp_pass = (all(bool(row["pass"]) and int(row["invariant_failures"]) == 0 and
                     int(row["aborted_with_published_blocks"]) == 0 for row in pstp["rows"]) and
                 all(truth(row.get("gate_pass")) for row in faults) and
                 all(int(float(row.get("commit_tokens", 0))) == 0 for row in faults
                     if row.get("txn_state") == "ABORTED") and
                 all(int(float(row.get("commit_tokens", 0))) == 0 for row in live
                     if row.get("txn_state") == "ABORTED"))

    tasks = [
        {"task": 1, "name": "Llama SOTA direct comparison", "pass": complete_sota,
         "external_blocker": cacheslide_blocked, "blocked_cell": "CacheSlide" if cacheslide_blocked else ""},
        {"task": 2, "name": "same-serving-path D0/D1/D2", "pass": service_complete and in_engine_verify},
        {"task": 3, "name": "frozen net-benefit admission", "pass": bool(gate["all_accepted_observed_net_positive"])},
        {"task": 4, "name": "certificate binding and lifecycle", "pass": bool(binding["all_cases_pass"]) and
         bool(binding["malicious_metadata_fail_closed"]) and bool(binding["unseen_private_suffix_admitted"]) and
         bool(lifecycle["gate_pass"])},
        {"task": 5, "name": "PSTP state machine and concurrent faults", "pass": pstp_pass},
        {"task": 6, "name": "five-repeat real-task open-loop matrix", "pass": service_complete and service_safety},
    ]
    payload = {
        "schema_version": "contractkv.tsc-six-task-closure.v1", "tasks": tasks,
        "all_required_gates_pass": all(row["pass"] for row in tasks),
        "external_artifact_blockers": [row["blocked_cell"] for row in tasks if row.get("external_blocker")],
        "claim_boundary": "A source-artifact blocker is not converted into a performance number or counted as a reproduced baseline.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_required_gates_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
