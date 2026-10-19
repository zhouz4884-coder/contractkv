#!/usr/bin/env python3
"""Mechanical taxonomy for every Phase 17 incomplete calibration record."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from enum import Enum
from pathlib import Path


class IncompleteClass(str, Enum):
    RAW_ATTESTATION_MISSING = "RAW_ATTESTATION_MISSING"
    FINISH_REASON_LENGTH = "FINISH_REASON_LENGTH"
    TERMINAL_TOKEN_MISSING = "TERMINAL_TOKEN_MISSING"
    PROMPT_TOKEN_ID_MISMATCH = "PROMPT_TOKEN_ID_MISMATCH"
    ANSWER_SPAN_OUT_OF_RANGE = "ANSWER_SPAN_OUT_OF_RANGE"
    ANSWER_LENGTH_MISMATCH = "ANSWER_LENGTH_MISMATCH"
    TARGET_TOKEN_ABSENT = "TARGET_TOKEN_ABSENT"
    COMPETITOR_LOGPROB_ABSENT = "COMPETITOR_LOGPROB_ABSENT"
    TOKEN_RANK_MISSING = "TOKEN_RANK_MISSING"
    STOP_TOKEN_NOT_TOP1 = "STOP_TOKEN_NOT_TOP1"
    LCP_SEVERE_DRIFT = "LCP_SEVERE_DRIFT"
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    CONNECTOR_FAILURE = "CONNECTOR_FAILURE"
    UNKNOWN_PROTOCOL_ERROR = "UNKNOWN_PROTOCOL_ERROR"


def classify_incomplete(error_type: str, failure_reason: str, error_message: str) -> IncompleteClass:
    text = f"{error_type} {failure_reason} {error_message}".lower()
    rules = [
        ("raw_attestation_missing", IncompleteClass.RAW_ATTESTATION_MISSING),
        ("raw attestation", IncompleteClass.RAW_ATTESTATION_MISSING),
        ("finish_reason=length", IncompleteClass.FINISH_REASON_LENGTH),
        ("finish reason=length", IncompleteClass.FINISH_REASON_LENGTH),
        ("terminal stop", IncompleteClass.TERMINAL_TOKEN_MISSING),
        ("prompt ids changed", IncompleteClass.PROMPT_TOKEN_ID_MISMATCH),
        ("prompt_token_id_mismatch", IncompleteClass.PROMPT_TOKEN_ID_MISMATCH),
        ("answer offset", IncompleteClass.ANSWER_SPAN_OUT_OF_RANGE),
        ("answer length mismatch", IncompleteClass.ANSWER_LENGTH_MISMATCH),
        ("target token", IncompleteClass.TARGET_TOKEN_ABSENT),
        ("no competitor", IncompleteClass.COMPETITOR_LOGPROB_ABSENT),
        ("rank missing", IncompleteClass.TOKEN_RANK_MISSING),
        ("stop token", IncompleteClass.STOP_TOKEN_NOT_TOP1),
        ("severe_drift", IncompleteClass.LCP_SEVERE_DRIFT),
        ("cancel", IncompleteClass.REQUEST_CANCELLED),
        ("timeout", IncompleteClass.REQUEST_TIMEOUT),
        ("connection", IncompleteClass.CONNECTOR_FAILURE),
        ("http", IncompleteClass.CONNECTOR_FAILURE),
    ]
    return next((category for pattern, category in rules if pattern in text), IncompleteClass.UNKNOWN_PROTOCOL_ERROR)


def truth(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle: source = list(csv.DictReader(handle))
    rows = []
    for row in source:
        if row.get("error_type") == "none": continue
        category = classify_incomplete(row.get("error_type", ""), row.get("failure_reason", ""), row.get("error_message", ""))
        rows.append({"sample_key": row.get("sample_key", ""), "candidate_id": row.get("candidate_id", ""), "partition": row.get("partition", ""),
                     "dataset": row.get("dataset", ""), "task": row.get("task", ""), "sample_id": row.get("sample_id", ""),
                     "unsafe_quality_drop": row.get("unsafe_quality_drop", ""), "expected_prefix_gain": row.get("expected_prefix_gain", "0"),
                     "error_type": row.get("error_type", ""), "failure_reason": row.get("failure_reason", ""), "error_message": row.get("error_message", ""),
                     "incomplete_class": category.value, "claim_boundary": "Mechanical classification of observed Phase 17 calibration incompleteness; no recovery claim."})
    fields = list(rows[0]) if rows else ["incomplete_class"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows: groups[row["incomplete_class"]].append(row)
    summary = []
    for category, group in sorted(groups.items()):
        gain = sum(float(row.get("expected_prefix_gain") or 0) for row in group if not truth(row.get("unsafe_quality_drop")))
        summary.append({"incomplete_class": category, "count": len(group), "safe": sum(not truth(row.get("unsafe_quality_drop")) for row in group),
                        "unsafe": sum(truth(row.get("unsafe_quality_drop")) for row in group), "calibration": sum(row.get("partition") == "calibration" for row in group),
                        "held_out_quality": sum(row.get("partition") == "held_out_quality" for row in group), "safe_prefix_gain_lost": gain,
                        "category_type": "data" if category == IncompleteClass.RAW_ATTESTATION_MISSING.value else "workload" if category == IncompleteClass.FINISH_REASON_LENGTH.value else "API/protocol"})
    with args.summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]) if summary else ["incomplete_class"]); writer.writeheader(); writer.writerows(summary)
    unknown = sum(row["incomplete_class"] == IncompleteClass.UNKNOWN_PROTOCOL_ERROR.value for row in rows)
    print({"rows": len(rows), "unknown": unknown})
    raise SystemExit(0 if rows and unknown == 0 else 1)


if __name__ == "__main__":
    main()
