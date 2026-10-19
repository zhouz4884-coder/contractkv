#!/usr/bin/env python3
"""Freeze Mistral runtime identity and preregistered policy before replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--vllm-source", type=Path, required=True)
    parser.add_argument("--split-commitment", type=Path, required=True)
    parser.add_argument("--candidate-builder", type=Path, required=True)
    parser.add_argument("--quality-scorer", type=Path, required=True)
    parser.add_argument("--runtime-output", type=Path, required=True)
    parser.add_argument("--policy-output", type=Path, required=True)
    args = parser.parse_args()

    import torch

    config = json.loads((args.model_path / "config.json").read_text(encoding="utf-8"))
    tokenizer_config = json.loads((args.model_path / "tokenizer_config.json").read_text(encoding="utf-8"))
    revision = subprocess.run(
        ["git", "-C", str(args.vllm_source), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False).stdout.strip() or "unavailable"
    files = {
        name: sha256(args.model_path / name)
        for name in ("config.json", "tokenizer.json", "tokenizer.model", "tokenizer_config.json")
        if (args.model_path / name).exists()
    }
    runtime = {
        "schema_version": "mistral.runtime-manifest.v1",
        "model_id": "Mistral-7B-Instruct-v0.3",
        "model_path": str(args.model_path),
        "model_config_hash": files.get("config.json"),
        "model_revision": config.get("_commit_hash") or "local-checkpoint-no-revision",
        "tokenizer_hash": stable_hash({key: value for key, value in files.items() if key.startswith("tokenizer")}),
        "chat_template_hash": stable_hash(tokenizer_config.get("chat_template", "")),
        "chat_template_separator": "\\n\\n between typed segments; frozen before protocol audit",
        "vllm_patch_commit": revision,
        "python": platform.python_version(), "torch": torch.__version__,
        "torch_cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
        "gpu_names": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
        "decode": {"temperature": 0, "top_p": 1, "max_context": 8192,
                   "max_output_tokens": 128, "single_terminal_token": True,
                   "stable_word_limit": 1500, "dtype": "float16"},
        "candidate_builder_hash": sha256(args.candidate_builder),
        "quality_scorer_hash": sha256(args.quality_scorer),
        "verifier_payload_parser_hash": sha256(Path("scripts/phase16r_verifier_live.py")),
        "split_commitment_hash": sha256(args.split_commitment),
    }
    policy_body = {
        "schema_version": "mistral.prospective-policy.v1",
        "model_id": runtime["model_id"],
        "method": ["dependency-constrained-cache-aware-layout",
                   "strict-tier1-token-path-attestation",
                   "compact-enginecore-result",
                   "prefix-selective-transactional-promotion"],
        "excluded": ["tier2-free-decode", "semantic-fallback", "promotion-only-second-prefill"],
        "certificate_scope": "MODEL_TASK_QUALIFIED_SESSION",
        "margin_mode": "telemetry-only",
        "quality_epsilon": .03, "tool_slack_ms": 2000,
        "main_concurrency": 2, "max_output_tokens": 128,
        "development_gate": {"completion_rate": 1.0, "certified_future_violations": 0,
                             "safe_coverage_min": .35, "protocol_bugs": 0},
        "heldout_gate": {"completion_rate": 1.0, "unsafe_certified_sessions": 0,
                         "certified_future_violations": 0, "safe_coverage_min": .50,
                         "retained_prefix_gain_min": .50, "new_prefill_reduction_min": .30,
                         "net_mean_ttft_reduction_min": .30,
                         "certified_reuse_min": .95, "dynamic_suffix_reuse_max": 0},
        "runtime_manifest_hash": stable_hash(runtime),
        "split_commitment_hash": runtime["split_commitment_hash"],
        "heldout_threshold_retuning_allowed": False,
        "third_model_after_mistral_allowed": False,
    }
    policy_body["policy_hash"] = stable_hash(policy_body)
    for path, value in ((args.runtime_output, runtime), (args.policy_output, policy_body)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runtime": runtime, "policy_hash": policy_body["policy_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
