#!/usr/bin/env python3
"""Versioned frozen verifier-policy manifest and runtime provenance checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


TERMINAL_PROTOCOL_VERSION = "single-returned-terminal-token-v1"
GREEDY_CONFIG = {
    "temperature": 0,
    "top_p": 1,
    "top_k": -1,
    "min_p": 0,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "repetition_penalty": 1,
    "logit_bias": None,
    "guided_decoding": None,
    "seed": 0,
    "max_tokens": 96,
    "return_token_ids": True,
    "logprobs": True,
    "top_logprobs": 2,
}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, (list, tuple)) and all(isinstance(item, bytes) for item in value):
        payload = b"\n".join(value)
    else:
        payload = canonical_json(value)
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class FrozenVerifierPolicy:
    schema_version: str
    policy_version: str
    attestation_mode: str
    model_id: str
    model_revision: str
    tokenizer_hash: str
    chat_template_hash: str
    vllm_version: str
    terminal_protocol_version: str
    verifier_code_commit: str
    tau_raw: float
    tau_abs: float
    tau_drop: float
    calibration_manifest_hash: str
    calibration_split_hash: str
    decode_config_hash: str


@dataclass(frozen=True)
class RuntimeIdentity:
    model_id: str
    model_revision: str
    tokenizer_hash: str
    chat_template_hash: str
    vllm_version: str
    terminal_protocol_version: str
    decode_config_hash: str


def policy_hash(policy: FrozenVerifierPolicy) -> str:
    return digest(asdict(policy))


def load_frozen_policy(path: Path) -> tuple[FrozenVerifierPolicy, str]:
    policy = FrozenVerifierPolicy(**json.loads(path.read_text(encoding="utf-8")))
    return policy, policy_hash(policy)


def validate_policy_runtime(policy: FrozenVerifierPolicy, runtime: RuntimeIdentity) -> list[str]:
    errors: list[str] = []
    for field in (
        "model_id", "model_revision", "tokenizer_hash", "chat_template_hash",
        "vllm_version", "terminal_protocol_version", "decode_config_hash",
    ):
        expected, actual = getattr(policy, field), getattr(runtime, field)
        if expected != actual:
            errors.append(f"{field}: expected={expected}, actual={actual}")
    return errors


def runtime_identity(model_id: str, model_path: Path, vllm_version: str) -> RuntimeIdentity:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    config = model_path / "config.json"
    tokenizer_files = [model_path / name for name in ("tokenizer.json", "tokenizer_config.json") if (model_path / name).exists()]
    return RuntimeIdentity(
        model_id=model_id,
        model_revision=file_hash(config),
        tokenizer_hash=digest([file_hash(path) for path in tokenizer_files]),
        chat_template_hash=digest(str(getattr(tokenizer, "chat_template", ""))),
        vllm_version=vllm_version,
        terminal_protocol_version=TERMINAL_PROTOCOL_VERSION,
        decode_config_hash=digest(GREEDY_CONFIG),
    )


def git_commit(cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    except Exception:
        return os.environ.get("CONTRACTKV_VERIFIER_CODE_COMMIT", "unversioned-remote-copy")


def build_policy(*, model_id: str, model_path: Path, vllm_version: str, threshold_path: Path, calibration_csv: Path, repo: Path) -> FrozenVerifierPolicy:
    thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
    identity = runtime_identity(model_id, model_path, vllm_version)
    rows = calibration_csv.read_bytes()
    calibration_lines = [line for line in rows.splitlines() if b",calibration," in line]
    return FrozenVerifierPolicy(
        schema_version="phase17r.frozen-policy.v1",
        policy_version="phase17r-v0",
        attestation_mode="same-backend-teacher-forced-strict-top1",
        **asdict(identity),
        verifier_code_commit=git_commit(repo),
        tau_raw=float(thresholds["tau_raw"]), tau_abs=float(thresholds["tau_abs"]), tau_drop=float(thresholds["tau_drop"]),
        calibration_manifest_hash=digest(rows), calibration_split_hash=digest(calibration_lines),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-id", default="qwen3-8b")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--vllm-version", default="0.10.2")
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--calibration-csv", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()
    policy = build_policy(model_id=args.model_id, model_path=args.model_path, vllm_version=args.vllm_version,
                          threshold_path=args.thresholds, calibration_csv=args.calibration_csv, repo=args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(policy), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"policy_hash": policy_hash(policy), "policy_version": policy.policy_version}, indent=2))


if __name__ == "__main__":
    main()
