#!/usr/bin/env python3
"""Phase 17 verification-driven PSTP transaction contracts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.contractkv_pstp import VerifyDecision


class TxnState(str, Enum):
    OPEN = "OPEN"
    VERIFYING = "VERIFYING"
    FINALIZING = "FINALIZING"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass(frozen=True)
class PSTPPlan:
    txn_id: str
    stable_prefix_end_token: int
    expected_stable_tokens: int
    tokenization_glue_loss: int
    glue_status: str
    stable_content_hash: str
    layout_hash: str
    dependency_graph_hash: str
    shadow_work: bool = True
    fault_mode: str = "none"
    policy_hash: str = ""
    policy_version: str = ""
    attestation_mode: str = ""
    runtime_identity: dict[str, Any] = field(default_factory=dict)


@dataclass
class PSTPRuntime:
    plan: PSTPPlan
    verify_payload: dict[str, Any] = field(default_factory=dict)
    verify_report: Any | None = None
    verify_decision: VerifyDecision = VerifyDecision.PENDING
    txn_state: TxnState = TxnState.OPEN
    committed_tokens: int = 0
    finalize_count: int = 0


@dataclass(frozen=True)
class TransactionalCertificate:
    txn_id: str
    stable_content_hash: str
    layout_hash: str
    dependency_graph_hash: str
    committed_prefix_tokens: int
    committed_full_blocks: int
    raw_margin_q05: float
    candidate_margin_q05: float
    degradation_q95: float
    robustness_reserve: float
    issued_cache_epoch: int
    policy_hash: str = ""
    policy_version: str = ""
    attestation_mode: str = ""
    model_revision: str = ""
    tokenizer_hash: str = ""
    chat_template_hash: str = ""


def runtime_to_dict(runtime: PSTPRuntime) -> dict[str, Any]:
    return {
        "plan": asdict(runtime.plan),
        "verify_payload": runtime.verify_payload,
    }


def runtime_from_dict(value: dict[str, Any]) -> PSTPRuntime:
    return PSTPRuntime(
        plan=PSTPPlan(**dict(value["plan"])),
        verify_payload=dict(value.get("verify_payload") or {}),
    )


def write_runtime_registry(path: str | Path, entries: dict[str, PSTPRuntime]) -> None:
    from scripts.contractkv_pstp import write_registry as _unused  # noqa: F401
    import tempfile

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 2, "requests": {key: runtime_to_dict(value) for key, value in sorted(entries.items())}}
    fd, temp_name = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_runtime_registry(path: str | Path) -> dict[str, PSTPRuntime]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return {str(key): runtime_from_dict(value) for key, value in payload.get("requests", {}).items()}


def lookup_runtime(request_id: str, registry_path: str | Path | None = None) -> PSTPRuntime | None:
    path = registry_path or os.environ.get("CONTRACTKV_PHASE17_REGISTRY")
    if not path:
        return None
    candidates = [str(request_id)]
    for prefix in ("chatcmpl-", "cmpl-"):
        if candidates[0].startswith(prefix):
            stripped = candidates[0][len(prefix):]
            candidates.append(stripped)
            # vLLM appends the prompt index to legacy completion request IDs.
            stem, separator, suffix = stripped.rpartition("-")
            if prefix == "cmpl-" and separator and suffix.isdigit():
                candidates.append(stem)
    registry = load_runtime_registry(path)
    for candidate in candidates:
        if candidate in registry:
            return registry[candidate]
    return None
