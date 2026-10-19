"""Archive result-producing source identities and the exact serving patch."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import write


ENTRYPOINTS = {
    "run_tsc_revision_r1_batch.sh": "main matrix orchestration",
    "run_tsc_revision_r1_cell.sh": "fresh raw/ContractKV serving cells",
    "run_tsc_revision_r1_followup.sh": "zero-slack service and guard orchestration",
    "run_tsc_revision_qwen14_cost.sh": "TP2 cost supplement orchestration",
    "run_vllm_server.sh": "actual model server startup",
    "stop_vllm_server.sh": "owned server cleanup",
    "tsc_revision_build_inputs.py": "source-disjoint frozen input selection",
    "tsc_revision_live.py": "raw-reference attestation and actual free generation",
    "tsc_revision_qwen14_cost_live.py": "TP2 client entrypoint",
    "tsc_revision_qwen14_preflight.py": "frozen TP2 tokenizer/context capacity check",
    "tsc_revision_cell_manifest.py": "per-cell source/runtime/model/input identity",
    "tsc_revision_prepare_service.py": "frozen 20-session service input construction",
    "tsc_revision_zero_slack_live.py": "same-engine raw-reference service attestation",
    "tsc_revision_guard_probe.py": "live order-sensitive reject/zero-publication control",
    "tsc_revision_offline_audit.py": "archived full-cost and free-text analysis",
    "tsc_revision_baseline_audit.py": "matched native-baseline task-score analysis",
    "tsc_revision_input_layout_audit.py": "frozen-tokenizer positional displacement",
    "tsc_revision_registration_audit.py": "CPU registration trust-boundary audit",
    "tsc_revision_summarize.py": "paired performance, token quality, joint-session bootstrap",
    "tsc_revision_diagnostics.py": "raw-repeat, cost, rejection and root-cause diagnostics",
    "tsc_revision_service_summary.py": "actual zero-slack service/quality/log aggregation",
    "audit_tsc_revision_r1_completion.py": "required-cell/count/hash/invariant closure",
    "tsc_revision_source_inventory.py": "source and serving patch provenance",
    "tsc_revision_report.py": "final evidence-bounded X1-X7 report",
    "tsc_revision_package_raw.py": "verified raw-evidence archive and file hashes",
    "tsc_revision_resource_transition.py": "authorized GPU-resource transition audit",
    "install_vllm_v1_ephemeral_shadow_hook.py": "install ephemeral transactional shadow hooks",
    "install_vllm_v1_prefix_metrics_probe.py": "install real prefix/physical-block observations",
}
HELPERS = {
    "phase13b_fresh_policy_quality_replay.py": "build_case: benchmark-derived segments",
    "phase22_llama_layout_ladder.py": "stable-segment expansion and frozen L0-L3 ordering",
    "phase12f_real_vllm_caposc_replay.py": "ordered segment rendering",
    "phase20a_official_quality.py": "frozen official-compatible task scoring",
    "phase17_live_common.py": "actual raw generation, tokenizer and verifier HTTP clients",
    "phase16r_verifier_live.py": "actual token IDs and raw-margin extraction",
    "contractkv_verifier.py": "EOS separation and in-engine compact strict-path report",
    "contractkv_pstp.py": "stable/LCP commit boundary and transaction metadata",
    "contractkv_quiescence.py": "scheduler shadow-work admission",
    "contractkv_shadow_parking.py": "scheduler shadow request parking/resumption",
    "tsc_real_task_open_loop.py": "frozen Poisson trace, service timing and task scores",
    "tsc_service_template_quality_live.py": "template prompt compilation and scope records",
    "contractkv_certificate_binding.py": "signed generation/runtime/manifest scope check",
    "phase12e_cache_aware_posc.py": "service prompt compiler and segment-prefix ledger",
    "phase14c_run_full_pool_quality_jobs.py": "task-specific prompt messages",
    "phase12_prefix_cache_ab.py": "real sync/async streaming clients and percentiles",
    "summarize_submission_supplement.py": "percentile definition",
    "summarize_llama_sota_matrix.py": "archived matched-baseline joins and official scores",
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for role, mapping in (("executed_entrypoint", ENTRYPOINTS), ("result_path_helper", HELPERS)):
        for name, purpose in mapping.items():
            path = a.root / "scripts" / name
            if not path.is_file():
                raise ValueError("Missing result source " + str(path))
            rows.append({"path": "scripts/" + name, "role": role, "purpose": purpose,
                         "current_source_sha256": sha(path),
                         "evidence": "Named batch/client/analysis invocation or imported function on the result-producing path; not a test file."})
    source_files = ["vllm/entrypoints/openai/api_server.py", "vllm/v1/core/sched/scheduler.py",
                    "vllm/v1/engine/__init__.py", "vllm/v1/engine/async_llm.py", "vllm/v1/request.py"]
    def git(*args):
        return subprocess.run(["git", "-C", str(a.source), *args], capture_output=True, check=True).stdout
    patch = git("diff", "v0.10.2", "--", *source_files)
    patch_path = a.output / "vllm_0102_revision_runtime_v1.patch"
    patch_path.write_bytes(patch)
    for name in source_files:
        rows.append({"path": "third_party/vllm-contractkv-tsc-r1/" + name,
                     "role": "actual_serving_engine_source", "purpose": "compact attestation/transaction/metrics path",
                     "current_source_sha256": sha(a.source / name), "evidence": "Exact patched runtime source; patch archived against official v0.10.2 tag."})
    write(a.output / "actual_result_code_inventory_v1.csv", rows)
    document = ["# R1 Actual Result-Producing Code", "",
                "This list excludes test files and private SSH/password helpers. Entry points were invoked by the experimental or analytical pipeline; "
                "helpers supplied functions used on those paths. Serving source is separately identified, not credited as new compiler code.", "",
                "Current file hashes and exact historical main-client identity are in the machine-readable inventory. "
                "The main matrix used the archived pre-augmentation client; the current client adds only Turn-0 output logging.", ""]
    for role in ("executed_entrypoint", "result_path_helper", "actual_serving_engine_source"):
        document.extend(["## " + role.replace("_", " ").title(), "", "| File | Actual role |", "|---|---|"])
        document.extend("| `" + row["path"] + "` | " + row["purpose"] + " |" for row in rows if row["role"] == role)
        document.append("")
    (a.root / "docs/tsc_revision_r1_actual_code_files.md").write_text("\n".join(document), encoding="utf-8")
    manifests = [json.loads(p.read_text()) for p in (a.output / "cells").glob("*/cell_manifest.json")]
    manifests += [json.loads(p.read_text()) for p in (a.output / "service").glob("*/cell_manifest.json")]
    archived_hashes = sorted({r["sha256"] for m in manifests for r in m["sources"] if r["path"].endswith("/scripts/tsc_revision_live.py")})
    main_snapshot = a.output / "source_snapshots/tsc_revision_live_main_v1.py"
    if not main_snapshot.is_file() or sha(main_snapshot) != "fa3b7302bb2ed00807cd3af0885198188f6ec4c77ccd5f5bf04123de66505954":
        raise ValueError("Main execution snapshot unavailable or wrong hash")
    record = {"schema_version": "tsc-revision-source-inventory.v1", "non_test_result_code_files": len(rows),
              "per_cell_manifests": len(manifests), "official_vllm_tag_sha": git("rev-parse", "v0.10.2").decode().strip(),
              "compact_channel_base_commit": git("rev-parse", "HEAD").decode().strip(),
              "patch_sha256": sha(patch_path), "patch_bytes": len(patch),
              "actual_main_live_client_sha256": sha(main_snapshot),
              "cell_live_client_hashes": archived_hashes,
              "logging_only_augmentation_after_main": "Turn0 reference/warm text and token IDs added; exact earlier main source retained by recorded SHA.",
              "packages_from_cell_manifest": manifests[0]["packages"], "python_version": sys.version,
              "linked_native_extensions": [{"relative_path": str(p.relative_to(a.source)),
                                             "resolved_file": str(p.resolve()), "bytes": p.stat().st_size,
                                             "sha256": sha(p)}
                                            for p in sorted((a.source / "vllm").glob("*.so"))],
              "private_credentials_and_network_transition_raw_not_published": True,
              "main_result_token_ids_are_actual_vllm_ids": True}
    (a.output / "runtime_source_inventory_v1.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__": main()
