#!/usr/bin/env bash
set -euo pipefail
cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
base=results/tsc_revision_r4/input_fidelity_validation_v1
"$PY" scripts/tsc_revision_r4_fidelity_summary_v2.py --root "$base" --output "$base/analysis"
"$PY" scripts/tsc_revision_r4_strata_calibration.py --root "$base" --output "$base/analysis"
"$PY" scripts/tsc_revision_r4_output_length_audit.py --root "$base" --output "$base/analysis/output_length_audit_v1.json"
"$PY" scripts/tsc_revision_r4_physical_prefix_accounting.py --root "$base" --output "$base/analysis/physical_prefix_accounting_v1.json"
"$PY" scripts/tsc_revision_r4_all_business_quality.py --root "$base" --output-prefix "$base/all_business_quality_v1"
"$PY" scripts/tsc_revision_r4_score_balance.py --root "$base" --output "$base/score_balance_v1.json"
"$PY" scripts/tsc_revision_r4_routing_attribution.py --root "$base" --output "$base/routing_attribution_v1.json"
"$PY" scripts/tsc_revision_r4_scope_object_audit.py --root "$base" --output "$base/scope_object_audit_v1.json"
"$PY" scripts/tsc_revision_r4_actual_prompt_audit.py --root "$base" --output "$base/independent_actual_prompt_ID_audit_v1.json"
"$PY" scripts/tsc_revision_r4_package_fidelity_validation_v1.py --root . --study input_fidelity_validation_v1
"$PY" scripts/tsc_revision_split_raw_archive.py --archive "$base/input_fidelity_validation_v1_raw_evidence_v1.tar.gz"
"$PY" scripts/tsc_revision_verify_archive.py --root "$base" --archive "$base/input_fidelity_validation_v1_raw_evidence_v1.tar.gz" --output "$base/remote_archive_verification_v1.json"
echo FIDELITY_INDEPENDENT18_AUDITED_ARCHIVED_SCIENTIFIC_RESULTS_SEPARATE
