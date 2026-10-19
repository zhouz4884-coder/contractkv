"""Audit manifest ownership, declarations and their confidentiality boundary."""
from __future__ import annotations
import argparse
from copy import deepcopy
import csv
import hashlib
import hmac
import json
import secrets
from pathlib import Path


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def signature(manifest: dict, secret: bytes) -> str:
    return hmac.new(secret, canonical(manifest), hashlib.sha256).hexdigest()


def registration_errors(manifest: dict, tag: str, secret: bytes,
                        trusted_operator: str, request_role: str) -> list[str]:
    errors = []
    if request_role != "operator": errors.append("client_cannot_register_shared_state")
    if manifest.get("issuer") != trusted_operator: errors.append("untrusted_issuer")
    if not hmac.compare_digest(signature(manifest, secret), tag): errors.append("manifest_signature_mismatch")
    seen = set()
    for segment in manifest.get("segments", []):
        sid = segment.get("id")
        if not sid or sid in seen: errors.append("invalid_segment_identity")
        seen.add(sid)
        if segment.get("content_hash") != hashlib.sha256(segment.get("text", "").encode()).hexdigest():
            errors.append("content_hash_mismatch")
        if segment.get("publish") and (not segment.get("stable") or segment.get("visibility") == "tenant_private"):
            errors.append("declared_private_or_mutable_publication")
    if not manifest.get("authorization_domain") or not manifest.get("template_version"):
        errors.append("missing_version_or_authorization_scope")
    return sorted(set(errors))


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    secret = secrets.token_bytes(32)
    stable = "Public repository documentation."
    private = "TENANT_PRIVATE_CANARY_4b17"
    base = {"issuer": "trusted-operator", "template_version": "v1", "authorization_domain": "domain-a",
            "segments": [{"id": "stable", "text": stable, "stable": True, "visibility": "domain_shared", "publish": True,
                          "content_hash": hashlib.sha256(stable.encode()).hexdigest()},
                         {"id": "private", "text": private, "stable": False, "visibility": "tenant_private", "publish": False,
                          "content_hash": hashlib.sha256(private.encode()).hexdigest()}]}
    tag = signature(base, secret); cases = []
    def add(name, manifest, signed, role, expected_reject, meaning):
        errors = registration_errors(manifest, signed, secret, "trusted-operator", role)
        cases.append({"case": name, "actual_reject": bool(errors), "expected_reject": expected_reject,
                      "errors": json.dumps(errors), "expectation_matched": bool(errors) == expected_reject,
                      "interpretation": meaning})
    add("authorized_template", base, tag, "operator", False, "valid operator-owned shared prefix")
    add("untrusted_client_reuses_operator_manifest", base, tag, "tenant", True, "metadata alone cannot grant registration authority")
    forged = deepcopy(base); forged["issuer"] = "tenant"
    add("forged_operator_identity", forged, tag, "operator", True, "identity and signature mismatch")
    changed = deepcopy(base); changed["segments"][0]["text"] += " changed"
    add("changed_content_stale_hash", changed, signature(changed, secret), "operator", True, "hash verifies declared bytes")
    forbidden = deepcopy(base); forbidden["segments"][1]["publish"] = True
    add("explicit_private_publication", forbidden, signature(forbidden, secret), "operator", True, "declared private segment cannot be shared")
    unstable = deepcopy(base); unstable["segments"][0]["stable"] = False
    add("mutable_shared_segment", unstable, signature(unstable, secret), "operator", True, "declared mutable segment cannot be shared")
    missing = deepcopy(base); missing["authorization_domain"] = ""
    add("missing_authorization", missing, signature(missing, secret), "operator", True, "registration scope must be explicit")
    tampered = deepcopy(base); tampered["template_version"] = "v2"
    add("stale_signed_version", tampered, tag, "operator", True, "lifecycle identity cannot be changed under old tag")
    wrong = deepcopy(base); wrong["segments"][1].update(stable=True, visibility="domain_shared", publish=True)
    add("trusted_operator_mislabels_private_as_public", wrong, signature(wrong, secret), "operator", False,
        "TRUST_BOUNDARY: valid hash/signature cannot infer confidentiality; operator misconfiguration is not prevented")
    a.output.mkdir(parents=True, exist_ok=True)
    with (a.output / "registration_manifest_cases_v1.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0])); writer.writeheader(); writer.writerows(cases)
    summary = {"schema_version": "tsc-revision-registration-audit.v1", "cases": len(cases),
               "all_expectations_matched": all(row["expectation_matched"] for row in cases),
               "operator_semantic_mislabel_detected": False,
               "hash_is_confidentiality_classifier": False,
               "boundary": "Registration validation trusts operator semantic declarations. Prefix timing channels remain outside authorization guarantees.",
               "evidence_type": "CPU registration validator audit; not a live vLLM confidentiality proof"}
    (a.output / "registration_manifest_summary_v1.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["all_expectations_matched"] else 2

if __name__ == "__main__": raise SystemExit(main())
