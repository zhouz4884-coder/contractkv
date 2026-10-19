#!/usr/bin/env python3
"""Record the Phase 26 v0 cumulative-cost bug and fused-v1 repair."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26d_typed_analysis import summarize_scope


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def summarize(label: str, result_dir: Path, manifest_path: Path) -> dict[str, Any]:
    raw = load_jsonl(result_dir / "r1-raw.jsonl")
    contract = load_jsonl(result_dir / "r1-contract.jsonl")
    session_ids = {str(row["session_id"]) for row in raw}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row, _ = summarize_scope(raw, contract, session_ids, 1, "all", 1500.0, manifest)
    return {
        "implementation": label,
        "repeat_scope": "r1 diagnostic pair",
        "certificate_session_coverage": row["certificate_session_coverage"],
        "mean_canary_verification_ms": row["mean_canary_verification_ms"],
        "unhidden_verifier_ms_total": row["unhidden_verifier_ms_total"],
        "observed_mean_ttft_reduction": row["observed_mean_ttft_reduction"],
        "net_mean_ttft_reduction": row["net_mean_ttft_reduction"],
        "new_prefill_reduction": row["new_prefill_reduction"],
        "policy_attributable_quality_violations": row["policy_attributable_quality_violations"],
        "status": ("invalidated_cumulative_cost_estimator" if label == "v0_multi_attempt"
                   else "corrected_single_candidate_deadline"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [
        summarize("v0_multi_attempt", args.base / "heldout",
                  args.base / "coder" / "typed_qualification_manifest_v0.json"),
        summarize("v1_fused", args.base / "heldout_v1",
                  args.base / "coder" / "fused_qualification_manifest_v1.json"),
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
