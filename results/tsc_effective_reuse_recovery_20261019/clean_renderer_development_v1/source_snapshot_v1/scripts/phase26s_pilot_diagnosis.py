#!/usr/bin/env python3
"""Summarize the sealed-v5 failure that motivated the Phase 26S protocol."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import percentile


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exact = read_jsonl(args.exact)
    contract = read_jsonl(args.contract)
    bad = [row for row in exact if row.get("policy_quality_violation")]
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exact:
        by_family[str(row["family"])].append(row)
    payload: dict[str, Any] = {
        "schema_version": "contractkv.phase26s.pilot-diagnosis.v1",
        "status": "calibration_only_not_formal_evidence",
        "exact_observations": len(exact),
        "contract_observations": len(contract),
        "exact_false_safe_count": len(bad),
        "contract_false_safe_count": sum(bool(row.get("policy_quality_violation")) for row in contract),
        "false_safe_cases": [],
        "family_preparation": {},
        "root_cause_classification": {
            "implementation": "candidate q05=1.0 was not robust to independent TP=2 decode",
            "design": "observation-scoped verifier cost exceeded declared slack outside RULER",
            "scoring_artifact": False,
        },
    }
    for row in bad:
        attempt = next(item for item in row.get("attempts", [])
                       if item.get("certificate_issued"))
        payload["false_safe_cases"].append({
            "session_id": row["session_id"], "turn_id": row["turn_id"],
            "family": row["family"], "quality_drop": row["same_process_quality_drop"],
            "raw_finish_reason": row["raw_reference_finish_reason"],
            "measured_finish_reason": row["finish_reason"],
            "candidate_margin_q05": attempt["candidate_margin_q05"],
            "terminal_stop_margin": attempt["terminal_stop_margin"],
        })
    for family, rows in by_family.items():
        prep = sorted(float(row["preparation_ms"]) for row in rows)
        payload["family_preparation"][family] = {
            "observations": len(rows),
            "exact_passes": sum(bool(row.get("certificate_issued")) for row in rows),
            "mean_preparation_ms": statistics.fmean(prep),
            "p95_preparation_ms": percentile(prep, .95),
            "mean_unhidden_ms_at_6000_slack": statistics.fmean(
                float(row["unhidden_verifier_ms"]) for row in rows),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
