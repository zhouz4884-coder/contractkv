#!/usr/bin/env python3
"""Freeze Phase 26S numerical and economic gates from the disjoint v5 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import percentile
from scripts.phase26r_policy import wilson_lower


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-slack-ms", type=float, default=7000.0)
    parser.add_argument("--margin-buffer", type=float, default=.15)
    args = parser.parse_args()

    rows = read_jsonl(args.pilot)
    if len(rows) != 500:
        raise RuntimeError(f"calibration pilot must contain 500 observations, got {len(rows)}")
    false_safe_margins = []
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[str(row["family"])].append(row)
        if row.get("policy_quality_violation"):
            for attempt in row.get("attempts", []):
                if attempt.get("certificate_issued"):
                    false_safe_margins.append(float(attempt["candidate_margin_q05"]))
    if not false_safe_margins:
        raise RuntimeError("pilot did not expose the expected false-safe boundary")
    minimum_margin = max(1.25, max(false_safe_margins) + args.margin_buffer)

    manifest = json.loads(args.base_manifest.read_text(encoding="utf-8"))
    manifest["schema_version"] = "contractkv.phase26s.observation-policy.v2"
    manifest["calibration_source"] = {
        "role": "disjoint pilot only; excluded from formal results",
        "path": str(args.pilot),
        "sha256": hashlib.sha256(args.pilot.read_bytes()).hexdigest(),
        "observations": len(rows),
        "false_safe_count": sum(bool(row.get("policy_quality_violation")) for row in rows),
    }
    manifest["exact_robustness_thresholds"].update({
        "minimum_candidate_margin_q05": minimum_margin,
        "calibration_rule": (
            "v5 disjoint pilot maximum false-safe candidate q05 plus 0.15; "
            "fresh v6 required for every reported result"
        ),
    })
    manifest["economics"]["tool_slack_ms"] = args.tool_slack_ms
    manifest["economics"]["admission_rule"] = (
        "p95 preparation must fit declared slack and Wilson-LCB expected saved time must be positive"
    )

    for family, spec in manifest["family_specs"].items():
        family_rows = by_family[family]
        preparations = sorted(float(row["preparation_ms"]) for row in family_rows)
        eligible = 0
        for row in family_rows:
            attempts = [attempt for attempt in row.get("attempts", [])
                        if attempt.get("stage") == "tier_e_compact_teacher_forced"]
            if not attempts:
                continue
            attempt = attempts[0]
            if (attempt.get("certificate_issued")
                    and float(attempt.get("candidate_margin_q05", -math.inf)) >= minimum_margin):
                eligible += 1
        spec["pilot_observations"] = len(family_rows)
        spec["preparation_p95_ms"] = percentile(preparations, .95)
        spec["exact_passes_at_frozen_margin"] = eligible
        spec["exact_pass_probability_lcb"] = wilson_lower(eligible, len(family_rows))

    manifest["heldout_opened"] = False
    manifest["formal_split"] = "fresh v6; disjoint from development and v1-v5"
    manifest["claim_boundary"] = (
        "v5 is calibration-only after exposing a false-safe; only fresh v6 may support Phase 26S claims."
    )
    manifest.pop("qualification_hash", None)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["qualification_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "minimum_candidate_margin_q05": minimum_margin,
        "qualification_hash": manifest["qualification_hash"],
        "families": {key: {
            "preparation_p95_ms": value["preparation_p95_ms"],
            "exact_pass_probability_lcb": value["exact_pass_probability_lcb"],
        } for key, value in manifest["family_specs"].items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
