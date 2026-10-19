#!/usr/bin/env python3
"""Summarize Phase 17R policy lineage and conditional refreshed-label evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase17_calibrate_thresholds import metrics


def truth(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True); parser.add_argument("--integrated", type=Path, required=True)
    parser.add_argument("--margins", type=Path, required=True); parser.add_argument("--refresh", type=Path, required=True)
    parser.add_argument("--policy-output", type=Path, required=True); parser.add_argument("--refreshed-output", type=Path, required=True)
    args = parser.parse_args(); policy = json.loads(args.policy.read_text(encoding="utf-8"))
    import hashlib
    expected_hash = hashlib.sha256(json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    with args.integrated.open(encoding="utf-8", newline="") as handle: integrated = list(csv.DictReader(handle))
    lineage = []
    for row in integrated:
        mismatch = row["case_class"] == "manifest_mismatch"
        lineage.append({"case_id": row["case_id"], "case_class": row["case_class"], "expected_policy_hash": expected_hash, "observed_policy_hash": row["policy_hash"],
                        "normal_lineage_consistent": truth(row["policy_consistent"]), "manifest_mismatch_rejected": mismatch and row["txn_state"] == "ABORTED" and int(row["cache_entries_delta"] or 0) == 0 and not truth(row["certificate_issued"]),
                        "txn_state": row["txn_state"], "cache_entries_delta": row["cache_entries_delta"], "certificate_issued": row["certificate_issued"], "gate_pass": row["gate_pass"],
                        "claim_boundary": "Policy lineage is evaluated per transaction; deliberate manifest mismatches are expected to reject rather than match."})
    args.policy_output.parent.mkdir(parents=True, exist_ok=True)
    with args.policy_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(lineage[0])); writer.writeheader(); writer.writerows(lineage)
    with args.margins.open(encoding="utf-8", newline="") as handle: margins = list(csv.DictReader(handle))
    with args.refresh.open(encoding="utf-8", newline="") as handle: refresh = list(csv.DictReader(handle))
    stale = {(row["sample_key"], row["candidate_id"]) for row in refresh if row["label_status"] == "stale_or_nonreproducible"}
    adjusted = [{**row, "unsafe_quality_drop": "false" if (row["sample_key"], row["candidate_id"]) in stale else row["unsafe_quality_drop"]} for row in margins]
    rows = []
    thresholds = (-1e9, -1e9, 1e9)
    for split in ("calibration", "held_out_quality"):
        result = metrics([row for row in adjusted if row["partition"] == split], thresholds)
        rows.append({"split": split, **result, "stale_labels_reclassified": sum(row["partition"] == split for row in refresh if row["label_status"] == "stale_or_nonreproducible"),
                     "refresh_incomplete": sum(row["partition"] == split for row in refresh if row["label_status"] == "refresh_incomplete"),
                     "claim_boundary": "Conditional re-evaluation: only the 34 historically unsafe labels were refreshed; this is not a full 734-row label regeneration."})
    with args.refreshed_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"policy_hash": expected_hash, "normal_lineages": sum(row["case_class"] != "manifest_mismatch" for row in lineage), "refreshed": rows}, indent=2))


if __name__ == "__main__":
    main()
