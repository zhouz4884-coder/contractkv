#!/usr/bin/env python3
"""Signed generation/runtime/manifest binding for ContractKV certificates."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


@dataclass(frozen=True)
class CertificateBinding:
    schema_version: str
    certificate_id: str
    model_id: str
    model_revision: str
    tokenizer_hash: str
    chat_template_hash: str
    serving_runtime: str
    runtime_revision: str
    generation_config_hash: str
    qualification_manifest_hash: str
    policy_hash: str
    tenant_id: str
    authorization_domain: str
    service_template_id: str
    service_template_epoch: int
    stable_prefix_hash: str
    layout_hash: str
    expires_at_epoch: int


@dataclass(frozen=True)
class RequestBinding:
    model_id: str
    model_revision: str
    tokenizer_hash: str
    chat_template_hash: str
    serving_runtime: str
    runtime_revision: str
    generation_config_hash: str
    qualification_manifest_hash: str
    policy_hash: str
    tenant_id: str
    authorization_domain: str
    service_template_id: str
    service_template_epoch: int
    stable_prefix_hash: str
    layout_hash: str
    current_epoch: int
    private_suffix_excluded: bool


def sign(binding: CertificateBinding, secret: bytes) -> str:
    return hmac.new(secret, canonical_json(asdict(binding)), hashlib.sha256).hexdigest()


def verify_signature(binding: CertificateBinding, signature: str, secret: bytes) -> bool:
    return hmac.compare_digest(sign(binding, secret), str(signature))


def validation_errors(binding: CertificateBinding, request: RequestBinding,
                      signature: str, secret: bytes) -> list[str]:
    errors: list[str] = []
    if not verify_signature(binding, signature, secret):
        errors.append("signature_mismatch")
    fields = (
        "model_id", "model_revision", "tokenizer_hash", "chat_template_hash",
        "serving_runtime", "runtime_revision", "generation_config_hash",
        "qualification_manifest_hash", "policy_hash", "tenant_id",
        "authorization_domain", "service_template_id", "service_template_epoch",
        "stable_prefix_hash", "layout_hash",
    )
    for field in fields:
        if getattr(binding, field) != getattr(request, field):
            errors.append(f"{field}_mismatch")
    if int(request.current_epoch) > int(binding.expires_at_epoch):
        errors.append("certificate_expired")
    if not request.private_suffix_excluded:
        errors.append("private_suffix_not_excluded")
    return sorted(set(errors))


def admitted(binding: CertificateBinding, request: RequestBinding,
             signature: str, secret: bytes) -> bool:
    return not validation_errors(binding, request, signature, secret)
