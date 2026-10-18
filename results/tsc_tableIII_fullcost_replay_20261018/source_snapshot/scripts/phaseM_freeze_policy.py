#!/usr/bin/env python3
"""Bind the development-qualified Mistral policy before heldout replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--development-summary", type=Path, required=True)
    parser.add_argument("--development-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    gate = json.loads(args.development_gate.read_text(encoding="utf-8"))
    if not gate.get("gate_pass"):
        raise RuntimeError("development gate failed; heldout policy cannot be frozen")
    frozen = {**policy,
              "schema_version": "mistral.frozen-heldout-policy.v1",
              "development_summary_sha256": sha256(args.development_summary),
              "development_gate_sha256": sha256(args.development_gate),
              "heldout_opened_after_gate_pass": True}
    body = {key: value for key, value in frozen.items() if key != "policy_hash"}
    frozen["policy_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    args.output.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"policy_hash": frozen["policy_hash"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
