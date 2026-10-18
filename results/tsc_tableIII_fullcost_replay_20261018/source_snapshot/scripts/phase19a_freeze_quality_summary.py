#!/usr/bin/env python3
"""Freeze Phase 19A quality, coverage, rejection, and opportunity summaries."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


FIELDS = [
    "partition", "candidates", "complete_candidates", "incomplete_candidates",
    "safe_candidates", "unsafe_candidates", "certificate_eligible",
    "safe_coverage", "unsafe_certified", "unsafe_rejected",
    "unsafe_rejection_rate", "potential_prefix_gain_tokens",
    "retained_prefix_gain_tokens", "retained_prefix_gain_rate",
    "incomplete_opportunity_loss_tokens", "mean_quality_drop",
    "claim_boundary",
]


def truth(value: object) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize(partition: str, rows: list[dict[str, str]]) -> dict[str, object]:
    complete = [row for row in rows if row["protocol_status"] == "COMPLETE"]
    incomplete = [row for row in rows if row["protocol_status"] == "INCOMPLETE"]
    labeled = [row for row in complete if row["fresh_unsafe_label"] in {"True", "False"}]
    safe = [row for row in labeled if not truth(row["fresh_unsafe_label"])]
    unsafe = [row for row in labeled if truth(row["fresh_unsafe_label"])]
    certified = [row for row in rows if truth(row["certificate_eligible"])]
    unsafe_certified = [row for row in unsafe if truth(row["certificate_eligible"])]
    gains = lambda values: sum(float(row.get("expected_prefix_gain") or 0) for row in values)
    drops = [float(row["quality_drop"]) for row in labeled if row.get("quality_drop", "")]
    potential = gains(safe)
    retained = gains([row for row in certified if not truth(row.get("fresh_unsafe_label"))])
    return {
        "partition": partition, "candidates": len(rows),
        "complete_candidates": len(complete), "incomplete_candidates": len(incomplete),
        "safe_candidates": len(safe), "unsafe_candidates": len(unsafe),
        "certificate_eligible": len(certified),
        "safe_coverage": len(certified) / max(1, len(safe)),
        "unsafe_certified": len(unsafe_certified),
        "unsafe_rejected": len(unsafe) - len(unsafe_certified),
        "unsafe_rejection_rate": (len(unsafe) - len(unsafe_certified)) / max(1, len(unsafe)),
        "potential_prefix_gain_tokens": potential,
        "retained_prefix_gain_tokens": retained,
        "retained_prefix_gain_rate": retained / max(1.0, potential),
        "incomplete_opportunity_loss_tokens": gains(incomplete),
        "mean_quality_drop": sum(drops) / max(1, len(drops)),
        "claim_boundary": "Frozen-provenance Qwen3-8B task-sanity coverage; not official benchmark scoring.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_csv(args.quality)
    audit = json.loads(args.audit_summary.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for row in rows: groups[row["partition"]].append(row)
    summaries = [summarize("all", rows)] + [summarize(key, groups[key]) for key in sorted(groups)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(summaries)
    payload = {"audit_gate_pass": bool(audit.get("gate_pass")), "summary": summaries,
               "frozen_policy_retuned": False,
               "margin_role": "telemetry_only"}
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if audit.get("gate_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
