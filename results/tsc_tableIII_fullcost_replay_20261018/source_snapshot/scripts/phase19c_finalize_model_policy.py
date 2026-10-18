#!/usr/bin/env python3
"""Bind a Phase 19C policy manifest to model-specific calibration labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_frozen_policy import digest


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--calibration-labels", type=Path, required=True)
    parser.add_argument("--calibration-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.draft.read_text(encoding="utf-8"))
    policy.pop("policy_hash", None)
    policy.update({
        "schema_version": "phase19c.model-policy.v2",
        "calibration_quality_labels_sha256": sha256(args.calibration_labels),
        "calibration_quality_summary_sha256": sha256(args.calibration_summary),
        "model_specific_quality_labels": True,
        "thresholds_retuned_from_heldout": False,
    })
    policy["policy_hash"] = digest(policy)
    args.output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(policy["policy_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
