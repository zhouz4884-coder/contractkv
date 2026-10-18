#!/usr/bin/env python3
"""Explicit validity scopes for empirical ContractKV certificates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ScopeMode(str, Enum):
    OBSERVATION = "observation"
    QUALIFIED_SESSION = "qualified_session"


@dataclass(frozen=True)
class CertificateValidityScope:
    model_identity: str
    task_family: str
    layout_hash: str
    stable_prefix_hash: str
    scope_mode: str
    observation_identity: str
    observation_epoch: int
    policy_hash: str
    qualification_hash: str = ""


@dataclass(frozen=True)
class RequestValidityContext:
    model_identity: str
    task_family: str
    layout_hash: str
    stable_prefix_hash: str
    observation_identity: str
    observation_epoch: int
    policy_hash: str
    qualification_hash: str = ""


def validation_errors(
    certificate: CertificateValidityScope,
    request: RequestValidityContext,
) -> list[str]:
    """Return every validity mismatch; an empty list admits certificate reuse.

    This validates reuse of an empirical attestation. It does not claim formal
    semantic equivalence. Publication remains independently transactional.
    """
    errors: list[str] = []
    required = {
        "model_identity": certificate.model_identity,
        "task_family": certificate.task_family,
        "layout_hash": certificate.layout_hash,
        "stable_prefix_hash": certificate.stable_prefix_hash,
        "scope_mode": certificate.scope_mode,
        "policy_hash": certificate.policy_hash,
    }
    errors.extend(f"missing_{key}" for key, value in required.items() if not str(value))
    for field in (
        "model_identity", "task_family", "layout_hash",
        "stable_prefix_hash", "policy_hash",
    ):
        if getattr(certificate, field) != getattr(request, field):
            errors.append(f"{field}_mismatch")

    if certificate.scope_mode == ScopeMode.OBSERVATION.value:
        if not certificate.observation_identity:
            errors.append("missing_observation_identity")
        if certificate.observation_identity != request.observation_identity:
            errors.append("observation_identity_mismatch")
        if int(certificate.observation_epoch) != int(request.observation_epoch):
            errors.append("observation_epoch_mismatch")
    elif certificate.scope_mode == ScopeMode.QUALIFIED_SESSION.value:
        if not certificate.qualification_hash:
            errors.append("missing_qualification_hash")
        elif certificate.qualification_hash != request.qualification_hash:
            errors.append("qualification_hash_mismatch")
    else:
        errors.append("unknown_scope_mode")
    return sorted(set(errors))


def is_valid(certificate: CertificateValidityScope, request: RequestValidityContext) -> bool:
    return not validation_errors(certificate, request)
