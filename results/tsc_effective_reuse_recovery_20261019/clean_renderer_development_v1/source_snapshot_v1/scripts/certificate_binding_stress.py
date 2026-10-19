#!/usr/bin/env python3
"""Adversarial audit of signed ContractKV certificate bindings."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_certificate_binding import (
    CertificateBinding, RequestBinding, sign, validation_errors,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    secret = b"contractkv-binding-stress-secret-not-persisted"
    cert = CertificateBinding(
        schema_version="contractkv.certificate-binding.v1", certificate_id="cert-17",
        model_id="llama31-8b", model_revision="model-r1", tokenizer_hash="tok-h1",
        chat_template_hash="chat-h1", serving_runtime="vllm", runtime_revision="0.10.2+hook-r1",
        generation_config_hash="gen-greedy-96", qualification_manifest_hash="manifest-h1",
        policy_hash="policy-h1", tenant_id="tenant-7", authorization_domain="domain-a",
        service_template_id="template-3", service_template_epoch=4,
        stable_prefix_hash="stable-h1", layout_hash="layout-l2", expires_at_epoch=8,
    )
    signature = sign(cert, secret)
    base = RequestBinding(**{
        key: value for key, value in asdict(cert).items()
        if key not in {"schema_version", "certificate_id", "expires_at_epoch"}
    }, current_epoch=4, private_suffix_excluded=True)
    cases = [
        ("exact_match", base, cert, signature, True),
        ("unseen_private_suffix", base, cert, signature, True),
        ("unseen_suffix_claimed_shareable", replace(base, private_suffix_excluded=False), cert, signature, False),
        ("stable_content_changed", replace(base, stable_prefix_hash="stable-evil"), cert, signature, False),
        ("malicious_tenant_metadata", replace(base, tenant_id="tenant-root"), cert, signature, False),
        ("authorization_scope_forgery", replace(base, authorization_domain="domain-b"), cert, signature, False),
        ("generation_config_changed", replace(base, generation_config_hash="gen-temp-07"), cert, signature, False),
        ("runtime_revision_changed", replace(base, runtime_revision="0.10.3"), cert, signature, False),
        ("model_revision_changed", replace(base, model_revision="model-r2"), cert, signature, False),
        ("qualification_manifest_changed", replace(base, qualification_manifest_hash="manifest-h2"), cert, signature, False),
        ("policy_changed", replace(base, policy_hash="policy-h2"), cert, signature, False),
        ("template_epoch_changed", replace(base, service_template_epoch=5), cert, signature, False),
        ("certificate_expired", replace(base, current_epoch=9), cert, signature, False),
        ("missing_signature", base, cert, "", False),
        ("tampered_signed_payload", base, replace(cert, layout_hash="layout-l3"), signature, False),
    ]
    rows = []
    for name, request, candidate, candidate_signature, expected in cases:
        errors = validation_errors(candidate, request, candidate_signature, secret)
        actual = not errors
        rows.append({
            "case": name, "expected_admitted": expected, "actual_admitted": actual,
            "decision": "ADMIT" if actual else "FAIL_CLOSED", "errors": json.dumps(errors),
            "pass": actual == expected,
        })
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = {
        "schema_version": "contractkv.certificate-binding-stress.v1",
        "cases": len(rows), "expected_admits": sum(row["expected_admitted"] for row in rows),
        "false_admits": sum(row["actual_admitted"] and not row["expected_admitted"] for row in rows),
        "false_rejects": sum(not row["actual_admitted"] and row["expected_admitted"] for row in rows),
        "all_cases_pass": all(row["pass"] for row in rows),
        "unseen_private_suffix_admitted": next(row["actual_admitted"] for row in rows if row["case"] == "unseen_private_suffix"),
        "malicious_metadata_fail_closed": all(not row["actual_admitted"] for row in rows if "malicious" in row["case"] or "forgery" in row["case"]),
        "claim_boundary": "Deterministic signed-binding audit. Live lifecycle and vLLM publication evidence are reported separately.",
    }
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_cases_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
