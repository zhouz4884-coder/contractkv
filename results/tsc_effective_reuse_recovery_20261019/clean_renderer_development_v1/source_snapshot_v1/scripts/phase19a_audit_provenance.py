#!/usr/bin/env python3
"""Audit Phase 19A row identity, joins, protocol, and frozen provenance."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "sample_key", "candidate_id", "partition", "identity_auditable",
    "candidate_identity_match", "join_match", "provenance_complete",
    "protocol_known", "fresh_label_present", "legacy_label_changed",
    "stale_label_used", "unexplained_join_mismatch", "unknown_protocol_error",
    "audit_pass", "audit_message",
]


def truth(value: object) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--legacy-labels", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    quality = read_csv(args.quality)
    legacy_rows = read_csv(args.legacy_labels)
    legacy = {(row["sample_key"], row["candidate_id"]): row for row in legacy_rows}
    jobs = {(str(row["sample_key"]), str(row["candidate_id"])): row
            for row in load_jsonl(args.jobs) if row.get("policy") != "raw-order"}
    quality_by_key = {(row["sample_key"], row["candidate_id"]): row for row in quality}
    duplicate_count = len(quality) - len(quality_by_key)
    expected = set(legacy) | set(jobs)
    missing = expected - set(quality_by_key)
    extra = set(quality_by_key) - expected
    hash_fields = ["model_revision", "tokenizer_hash", "chat_template_hash",
                   "candidate_builder_hash", "evaluator_hash", "policy_hash",
                   "raw_prompt_hash", "candidate_prompt_hash",
                   "raw_answer_ids_hash", "candidate_answer_ids_hash"]
    rows = []
    for key, row in sorted(quality_by_key.items()):
        join_match = key in legacy and key in jobs and row["partition"] == legacy[key]["partition"]
        identity_match = truth(row["candidate_identity_match"])
        identity_auditable = bool(key[0] and key[1] and row.get("candidate_prompt_hash"))
        provenance_complete = all(row.get(field, "") for field in hash_fields)
        protocol_known = row.get("verifier_decision") in {"PASS", "FAIL", "INCOMPLETE"}
        fresh_present = row.get("fresh_unsafe_label", "") in {"True", "False"}
        changed = False
        if fresh_present and key in legacy:
            changed = truth(row["fresh_unsafe_label"]) != truth(legacy[key]["unsafe_quality_drop"])
        messages = []
        if not identity_auditable: messages.append("identity_not_auditable")
        if not identity_match: messages.append("candidate_identity_mismatch")
        if not join_match: messages.append("join_mismatch")
        if not provenance_complete: messages.append("provenance_incomplete")
        if not protocol_known: messages.append("unknown_protocol")
        audit_pass = not messages
        rows.append({
            "sample_key": key[0], "candidate_id": key[1],
            "partition": row.get("partition", ""),
            "identity_auditable": identity_auditable,
            "candidate_identity_match": identity_match,
            "join_match": join_match, "provenance_complete": provenance_complete,
            "protocol_known": protocol_known, "fresh_label_present": fresh_present,
            "legacy_label_changed": changed,
            "stale_label_used": False,
            "unexplained_join_mismatch": not join_match,
            "unknown_protocol_error": not protocol_known,
            "audit_pass": audit_pass, "audit_message": ";".join(messages),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    summary = {
        "expected_candidates": 734, "quality_rows": len(quality),
        "unique_quality_rows": len(quality_by_key), "duplicate_rows": duplicate_count,
        "missing_rows": len(missing), "extra_rows": len(extra),
        "identity_auditable": sum(truth(row["identity_auditable"]) for row in rows),
        "provenance_complete": sum(truth(row["provenance_complete"]) for row in rows),
        "candidate_identity_mismatch": sum(not truth(row["candidate_identity_match"]) for row in rows),
        "stale_label_used": sum(truth(row["stale_label_used"]) for row in rows),
        "unexplained_join_mismatch": sum(truth(row["unexplained_join_mismatch"]) for row in rows),
        "unknown_protocol_error": sum(truth(row["unknown_protocol_error"]) for row in rows),
        "legacy_label_changed": sum(truth(row["legacy_label_changed"]) for row in rows),
    }
    summary["gate_pass"] = (
        summary["quality_rows"] == 734 and summary["unique_quality_rows"] == 734
        and summary["identity_auditable"] == 734
        and summary["provenance_complete"] == 734
        and summary["candidate_identity_mismatch"] == 0
        and summary["stale_label_used"] == 0
        and summary["unexplained_join_mismatch"] == 0
        and summary["unknown_protocol_error"] == 0
        and summary["missing_rows"] == 0 and summary["extra_rows"] == 0
    )
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
