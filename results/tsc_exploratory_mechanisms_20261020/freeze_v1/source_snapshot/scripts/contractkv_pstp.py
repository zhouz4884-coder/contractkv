#!/usr/bin/env python3
"""Frozen Prefix-Selective Transactional Promotion interfaces."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class VerifyDecision(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class PSTPSpec:
    txn_id: str
    stable_prefix_end_token: int
    verify_decision: VerifyDecision
    failure_reason: str = ""
    expected_stable_tokens: int = 0
    tokenization_glue_loss: int = 0
    glue_status: str = "exact"
    shadow_work: bool = True


def lcp_length(left: list[int] | tuple[int, ...], right: list[int] | tuple[int, ...]) -> int:
    matched = 0
    for left_token, right_token in zip(left, right):
        if left_token != right_token:
            break
        matched += 1
    return matched


def classify_tokenization_glue(expected_stable_tokens: int, stable_prefix_end_token: int) -> tuple[int, str]:
    loss = max(0, int(expected_stable_tokens) - int(stable_prefix_end_token))
    if loss == 0:
        return loss, "exact"
    if loss <= 5:
        return loss, "boundary_glue"
    return loss, "severe_drift"


def aligned_commit_tokens(stable_prefix_end_token: int, num_computed_tokens: int, block_size: int) -> int:
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    safe_tokens = min(max(0, int(stable_prefix_end_token)), max(0, int(num_computed_tokens)))
    return (safe_tokens // block_size) * block_size


def build_pstp_spec(
    txn_id: str,
    stable_ids: list[int],
    candidate_ids: list[int],
    verify_decision: VerifyDecision,
    block_size: int,
    failure_reason: str = "",
    shadow_work: bool = True,
) -> PSTPSpec:
    boundary = lcp_length(stable_ids, candidate_ids)
    loss, status = classify_tokenization_glue(len(stable_ids), boundary)
    decision = verify_decision
    reason = failure_reason
    if loss >= block_size:
        decision = VerifyDecision.INCOMPLETE
        reason = reason or f"tokenization_glue_loss={loss} exceeds block_size={block_size}"
    return PSTPSpec(
        txn_id=txn_id,
        stable_prefix_end_token=boundary,
        verify_decision=decision,
        failure_reason=reason,
        expected_stable_tokens=len(stable_ids),
        tokenization_glue_loss=loss,
        glue_status=status,
        shadow_work=shadow_work,
    )


def _normalize_request_id(request_id: str) -> tuple[str, ...]:
    values = [str(request_id)]
    for prefix in ("chatcmpl-", "cmpl-"):
        if values[0].startswith(prefix):
            values.append(values[0][len(prefix):])
    return tuple(values)


def load_registry(path: str | Path) -> dict[str, PSTPSpec]:
    registry_path = Path(path)
    if not registry_path.exists():
        return {}
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    records = payload.get("requests", payload)
    result: dict[str, PSTPSpec] = {}
    for request_id, value in records.items():
        item = dict(value)
        item["verify_decision"] = VerifyDecision(str(item["verify_decision"]))
        result[str(request_id)] = PSTPSpec(**item)
    return result


def lookup_pstp_spec(request_id: str, registry_path: str | Path | None = None) -> PSTPSpec | None:
    path = registry_path or os.environ.get("CONTRACTKV_PSTP_REGISTRY")
    if not path:
        return None
    registry = load_registry(path)
    for candidate in _normalize_request_id(request_id):
        if candidate in registry:
            return registry[candidate]
    return None


def write_registry(path: str | Path, specs: dict[str, PSTPSpec]) -> None:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "requests": {
            request_id: {
                **asdict(spec),
                "verify_decision": spec.verify_decision.value,
            }
            for request_id, spec in sorted(specs.items())
        },
    }
    fd, temp_name = tempfile.mkstemp(prefix=registry_path.name, suffix=".tmp", dir=registry_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, registry_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def upsert_registry_spec(path: str | Path, request_id: str, spec: PSTPSpec) -> None:
    existing = load_registry(path)
    existing[str(request_id)] = spec
    write_registry(path, existing)


def spec_to_dict(spec: PSTPSpec) -> dict[str, Any]:
    return {**asdict(spec), "verify_decision": spec.verify_decision.value}
