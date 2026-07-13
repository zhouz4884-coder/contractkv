#!/usr/bin/env python3
"""Build the minimal, hash-audited ContractKV paper artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CORE_FILES = [
    "docs/contractkv_certificate_validity_scope.md",
    "scripts/contractkv_certificate_scope.py",
    "scripts/contractkv_transaction.py",
    "scripts/contractkv_pstp.py",
    "scripts/contractkv_verifier.py",
    "scripts/contractkv_frozen_policy.py",
    "scripts/phase12e_cache_aware_posc.py",
    "scripts/phase16r_verifier_live.py",
    "scripts/phase17_live_common.py",
    "scripts/phase19b_end_to_end_live.py",
    "scripts/phase20a_official_quality.py",
    "scripts/install_vllm_v1_phase17_hook.py",
    "scripts/install_vllm_v1_prefix_metrics_probe.py",
    "scripts/install_vllm_v1_ephemeral_shadow_hook.py",
    "scripts/run_vllm_server.sh",
    "scripts/stop_vllm_server.sh",
    "scripts/run_submission_repeats.sh",
    "scripts/summarize_submission_repeats.py",
    "scripts/repair_submission_scope_telemetry.py",
    "scripts/install_sglang_external_baseline.sh",
    "scripts/run_external_sglang_raw_replay.py",
    "scripts/run_external_sglang_baseline.sh",
    "scripts/summarize_external_system_matrix.py",
    "scripts/run_external_after_repeats.sh",
    "scripts/resummarize_submission_results.sh",
    "scripts/freeze_llama_task_qualification.py",
    "scripts/score_llama_qualified_replay.py",
    "scripts/run_llama_qualified_replay.sh",
    "scripts/phase14m_physical_dedup.py",
    "scripts/summarize_physical_dedup_memory.py",
    "scripts/run_physical_dedup_submission.sh",
    "scripts/generate_submission_package.py",
    "tests/test_contractkv_certificate_scope.py",
    "tests/test_phase19_end_to_end.py",
    "tests/test_submission_repeats.py",
    "tests/test_repair_submission_scope_telemetry.py",
    "tests/test_external_sglang_baseline.py",
    "tests/test_external_system_matrix.py",
    "tests/test_generate_submission_package.py",
    "tests/test_paper_artifact.py",
    "tests/test_llama_task_qualification.py",
    "tests/test_physical_dedup_memory.py",
]

GENERATED_FILES = [
    "results/submission_repeats/submission_repeat_cells_v0.csv",
    "results/submission_repeats/submission_repeat_pairs_v0.csv",
    "results/submission_repeats/submission_repeat_aggregate_v0.csv",
    "results/submission_repeats/submission_repeat_summary_v0.json",
    "results/submission_repeats/scope_telemetry_repair_manifest_v0.json",
    "results/external_baseline/external_prefix_baseline_summary_v0.json",
    "results/external_baseline/external_system_matrix_v0.csv",
    "results/cross_model/llama_qualified_replay/llama_task_qualification_v0.json",
    "results/cross_model/llama_qualified_replay/aggregate_v0.csv",
    "results/cross_model/llama_qualified_replay/summary_v0.json",
    "results/cross_model/llama_qualified_replay/quality_pairs_v0.csv",
    "results/cross_model/llama_qualified_replay/quality_summary_v0.json",
    "results/hard_systems/physical_dedup_memory_v0.csv",
    "results/hard_systems/physical_dedup_memory_v0.json",
    "results/manifests/submission_hardening_v1.yaml",
    "submission/contractkv_manuscript.md",
    "submission/contractkv_appendix.md",
    "submission/claim_evidence_map.md",
    "submission/terminology_ledger.md",
    "submission/figures/submission_main_metrics.png",
    "submission/figures/submission_main_metrics.pdf",
    "docs/submission_hardening_closeout.md",
    "docs/submission_fresh_process_repeat_report.md",
    "docs/external_sglang_prefix_baseline_report.md",
    "docs/llama_qualified_cross_model_report.md",
    "docs/physical_dedup_memory_report.md",
    "docs/submission_experiment_diagnostics.md",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "artifact" / "contractkv-paper-v1")
    parser.add_argument("--allow-missing-generated", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    expected_parent = (ROOT / "artifact").resolve()
    if output.parent != expected_parent:
        raise ValueError(f"artifact output must be directly under {expected_parent}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copied: list[dict[str, object]] = []
    missing: list[str] = []
    for relative in CORE_FILES + GENERATED_FILES:
        source = ROOT / relative
        if not source.is_file():
            if relative in GENERATED_FILES and args.allow_missing_generated:
                missing.append(relative)
                continue
            raise FileNotFoundError(source)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({"path": relative, "bytes": target.stat().st_size,
                       "sha256": sha256(target)})

    artifact_readme = (
        "# ContractKV paper artifact v1\n\n"
        "This directory is generated by `scripts/build_paper_artifact.py`. "
        "It contains the final scoped-certificate path, fresh-process repeat "
        "summaries, the bounded external baseline, and submission text. Models, "
        "datasets, raw request logs, and historical exploratory phases are "
        "intentionally excluded. See `MANIFEST.json` for SHA-256 hashes.\n"
    )
    readme_path = output / "README.md"
    readme_path.write_text(artifact_readme, encoding="utf-8")
    copied.append({"path": "README.md", "bytes": readme_path.stat().st_size,
                   "sha256": sha256(readme_path)})
    copied.sort(key=lambda row: str(row["path"]))
    manifest = {
        "artifact": "contractkv-paper-v1",
        "scope": "minimal submission artifact; no models, datasets, raw logs, or historical exploratory phases",
        "files": copied,
        "missing_generated": missing,
    }
    (output / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "files": len(copied),
                      "missing_generated": missing}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
