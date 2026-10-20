"""Audit reviewer experiment coverage without launching new inference."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.tsc_revision_summarize import read, shared_macro_bootstrap

OUT = ROOT / "results/tsc_reviewer_priority_audit_20261020"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert not OUT.exists(), "Preserve previous audit output"
    r1 = ROOT / "results/tsc_revision_r1"
    manifest = json.loads((r1 / "fresh_summary_manifest_v1.json").read_text())
    committed = {r["path"]: r["sha256"] for r in manifest["source_files"]}
    cells = {}
    hashes = []
    for model in ("qwen", "mistral", "llama"):
        for repeat in (1, 2, 3):
            sides = []
            for arm in ("raw-order", "contractkv"):
                p = r1 / "cells" / f"common-hotpot_{model}_r{repeat}_{arm}_b0" / "raw.jsonl"
                assert sha(p) == committed[p.relative_to(ROOT).as_posix()]
                rows = read(p)
                future = [r for r in rows if r["row_type"] == "future"]
                assert len(future) == 270 and all(r["success"] for r in future)
                assert set(Counter(r["session_id"] for r in future).values()) == {9}
                sides.append(rows)
                hashes.append({"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)})
            rk = {(r["session_id"], r["turn_id"]) for r in sides[0] if r["row_type"] == "future"}
            ck = {(r["session_id"], r["turn_id"]) for r in sides[1] if r["row_type"] == "future"}
            assert rk == ck and len(rk) == 270
            cells[("common-hotpot", model, repeat, 0)] = (*sides, None, None)
    replay = shared_macro_bootstrap(cells, 10000, 10672026)
    with (r1 / "common_hotpot_shared_cluster_ci_v1.csv").open(newline="", encoding="utf-8") as f:
        old = list(csv.DictReader(f))
    for new, saved in zip(replay, old):
        for key in ("net_mean_ttft_reduction_macro", "ci95_low", "ci95_high"):
            assert abs(new[key] - float(saved[key])) < 1e-12
    table3 = json.loads((ROOT / "results/tsc_tableIII_fullcost_replay_20261018/analysis_v3/summary_v1.json").read_text())
    assert table3["fresh_server_cells"] == 24 and table3["future_pairs"] == 4725
    assert table3["full_controllers"] == 525 and table3["all_controller_and_RPC_durations_actual"]
    required = {
        "R1.2a": ["docs/tsc_major_revision_phase1_summary_zh.md", "results/tsc_revision_r1/common_hotpot_shared_cluster_ci_v1.csv"],
        "R1.2b": ["docs/ContractKV_Original_RULER_CI_Closure_20261020.md", "results/tsc_ruler_ci_recheck_20261020/recheck_receipt_v1.json"],
        "R1.3": ["docs/tsc_revision_reviewer_experiment_response_zh.md"],
        "R1.4_free_running": ["docs/ContractKV_Behavior_Scope_Repair_Report_20261020.md", "results/tsc_behavior_scope_repair_20261020/all_local_independent_recompute_v1.json"],
        "R1.4_horizon": ["results/tsc_revision_r2/post_long_extent_v4_original_freeze_audit_v1.json", "docs/tsc_revision_reviewer_experiment_response_zh.md"],
        "R1.5_and_isolation": ["docs/ContractKV_Authorization_Task_Repair_Report_20261019.md", "results/tsc_authorization_task_repair_20261019/local_independent_recompute_v1.json"],
        "R1.6_limit_option": ["docs/ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md"],
        "R2.3_reproducibility": ["results/tsc_behavior_scope_repair_20261020/validation_preflight_v4.json", "results/tsc_behavior_scope_repair_20261020/validation_conformance_v1.json"],
        "R2.6_displacement": ["docs/ContractKV_Reviewer_Experimental_Closure_Matrix.md", "docs/ContractKV_Five_Family_Raw_Order_Evidence_20261018.md"],
        "R3.1_input_order": ["docs/tsc_TableI_independent_measurement_completed_20261018_zh.md", "docs/ContractKV_Five_Family_Raw_Order_Evidence_20261018.md"],
        "R3.2_full_cost": ["docs/tsc_TableIII_fullcost_replay_completed_20261018_zh.md", "results/tsc_tableIII_fullcost_replay_20261018/analysis_v3/summary_v1.json"],
        "R3.3_D1_D2": ["docs/tsc_revision_mechanism_manifest_results_20261018_zh.md", "results/tsc_revision_mechanism_controls_20261018/local_independent_recompute_v1.json"],
        "R3.4_original_Goodput_CI": ["results/tsc_revision_remaining_audit_20261018/fig5_ci_audit_v1.json"],
    }
    evidence = []
    for item, paths in required.items():
        for name in paths:
            p = ROOT / name
            assert p.is_file() and p.stat().st_size > 0, name
            evidence.append({"reviewer_item": item, "path": name, "sha256": sha(p), "bytes": p.stat().st_size})
    for name in ["results/tsc_authorization_task_repair_20261019/local_independent_recompute_v1.json",
                 "results/tsc_revision_mechanism_controls_20261018/local_independent_recompute_v1.json",
                 "results/tsc_ruler_ci_recheck_20261020/recheck_receipt_v1.json",
                 "results/tsc_behavior_scope_repair_20261020/all_local_independent_recompute_v1.json"]:
        assert json.loads((ROOT / name).read_text())["status"] == "PASS"
    result = dict(status="PASS", checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  mode="triage-only; experiment evidence audit, not submission readiness",
                  actual_reviewer_source_sha256=sha(ROOT / "major .txt"),
                  HotpotQA_actual_future_pairs=2430, HotpotQA_original_CI_replay=replay,
                  HotpotQA_RULER_CIs_are_distinct_studies=True,
                  TableIII_same_cohort_full_cost_verified=True,
                  inherited_evidence_checks=evidence, freshly_rehashed_HotpotQA_inputs=hashes,
                  pending_required_GPU_cells_identified=0, new_GPU_requests=0,
                  limits=["Evidence availability does not prove every old scientific claim true.",
                          "Strict-exact repair is a separate protocol; do not silently relabel earlier performance.",
                          "Timing-defense experiment optional because reviewer explicitly permits a limitation.",
                          "Text, citations, artifact version mapping, layout and final response are not complete."])
    OUT.mkdir(parents=True)
    (OUT / "reviewer_experiment_recheck_v1.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "HotpotQA_actual_future_pairs", "pending_required_GPU_cells_identified", "new_GPU_requests")}))


if __name__ == "__main__":
    main()
