#!/usr/bin/env python3
"""Apply a frozen, conservative admission rule to sealed live economics lanes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "point_id", "lane", "stable_prefix_tokens", "future_reuses", "tool_slack_ms",
    "certificate_issued", "gate_accepted", "effective_policy", "observed_net_benefit_ms",
    "observed_net_benefit_fraction", "raw_completion_rate", "contract_completion_rate",
    "raw_quality_sanity_rate", "contract_quality_sanity_rate", "verify_decision", "txn_state",
    "claim_boundary",
]


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    rule = gate["development_rule"]
    rows = list(csv.DictReader(args.raw.open(encoding="utf-8")))
    output = []
    for row in rows:
        accepted = (
            int(row["future_reuses"]) >= int(rule["minimum_future_reuses"])
            and float(row["tool_slack_ms"]) >= float(rule["minimum_tool_slack_ms"])
            and (not rule.get("require_certificate", True) or truth(row["certificate_issued"]))
            and (not rule.get("require_completion", True)
                 or float(row["raw_completion_rate"]) == 1.0
                 and float(row["contract_completion_rate"]) == 1.0)
        )
        output.append({
            "point_id": row["point_id"], "lane": row["lane"],
            "stable_prefix_tokens": row["stable_prefix_tokens"],
            "future_reuses": row["future_reuses"], "tool_slack_ms": row["tool_slack_ms"],
            "certificate_issued": row["certificate_issued"], "gate_accepted": accepted,
            "effective_policy": "ContractKV" if accepted else "raw-fallback",
            "observed_net_benefit_ms": row["observed_net_benefit_ms"] if accepted else "0.0",
            "observed_net_benefit_fraction": row["observed_net_benefit_fraction"] if accepted else "0.0",
            "raw_completion_rate": row["raw_completion_rate"],
            "contract_completion_rate": row["contract_completion_rate"],
            "raw_quality_sanity_rate": row["raw_quality_sanity_rate"],
            "contract_quality_sanity_rate": row["contract_quality_sanity_rate"],
            "verify_decision": row["verify_decision"], "txn_state": row["txn_state"],
            "claim_boundary": (
                "Frozen gate selected on the development grid. Rejected lanes are reported as raw fallback; "
                "contract measurements on rejected lanes are diagnostic only."
            ),
        })
    accepted = [row for row in output if truth(row["gate_accepted"])]
    result = {
        "gate_id": gate["gate_id"], "heldout_lanes": len(output), "accepted_lanes": len(accepted),
        "rejected_lanes": len(output) - len(accepted),
        "all_accepted_observed_net_positive": all(float(row["observed_net_benefit_ms"]) > 0 for row in accepted),
        "minimum_accepted_observed_net_benefit_ms": min(
            (float(row["observed_net_benefit_ms"]) for row in accepted), default=0.0),
        "accepted_completion_100pct": all(
            float(row["raw_completion_rate"]) == 1.0 and float(row["contract_completion_rate"]) == 1.0
            for row in accepted),
        "accepted_quality_sanity_100pct": all(
            float(row["raw_quality_sanity_rate"]) == 1.0 and float(row["contract_quality_sanity_rate"]) == 1.0
            for row in accepted),
        "claim_boundary": "Held-out operating-point validation for a conservative gate, not a learned online benefit predictor.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(output)
    args.summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_accepted_observed_net_positive"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
