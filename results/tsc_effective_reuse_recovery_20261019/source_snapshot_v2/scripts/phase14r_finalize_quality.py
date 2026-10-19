#!/usr/bin/env python3
"""Merge Phase 14R quality shards, verify completeness, and calibrate QC-v2."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase14c_run_full_pool_quality_jobs import (
    LABEL_FIELDS,
    SUMMARY_FIELDS as LABEL_SUMMARY_FIELDS,
    build_labels,
    load_jsonl,
    summarize_labels,
    write_csv,
    write_jsonl,
)
from scripts.phase14r_qc_candidate_calibration import (
    SCORE_FIELDS,
    SUMMARY_FIELDS as QC_SUMMARY_FIELDS,
    calibrate,
)


AUDIT_FIELDS = [
    "manifest_jobs", "raw_rows_before_dedup", "deduplicated_rows", "duplicate_rows",
    "missing_jobs", "unexpected_jobs", "successful_jobs", "failed_jobs", "paired_labels",
    "candidate_feature_rows", "target_wilson95_upper", "claim_boundary",
]


def _csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def finalize(
    jobs: list[dict[str, Any]],
    raw_shards: list[list[dict[str, Any]]],
    features: list[dict[str, Any]],
    eps: float,
    target_wilson: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    merged = [row for shard in raw_shards for row in shard]
    by_job: dict[str, dict[str, Any]] = {}
    for row in merged:
        job_id = str(row.get("job_id", ""))
        if not job_id:
            continue
        previous = by_job.get(job_id)
        if previous is None or (not previous.get("success") and row.get("success")):
            by_job[job_id] = row
    manifest_ids = {str(job.get("job_id", "")) for job in jobs}
    final_rows = [by_job[job_id] for job_id in sorted(by_job) if job_id in manifest_ids]
    labels = build_labels(final_rows, features, eps=eps)
    scores, qc_summary, model = calibrate(features, labels, target_wilson)
    missing = manifest_ids - set(by_job)
    unexpected = set(by_job) - manifest_ids
    audit = [{
        "manifest_jobs": len(manifest_ids),
        "raw_rows_before_dedup": len(merged),
        "deduplicated_rows": len(final_rows),
        "duplicate_rows": len(merged) - len(by_job),
        "missing_jobs": len(missing),
        "unexpected_jobs": len(unexpected),
        "successful_jobs": sum(row.get("success") is True or str(row.get("success", "")).lower() == "true" for row in final_rows),
        "failed_jobs": sum(not (row.get("success") is True or str(row.get("success", "")).lower() == "true") for row in final_rows),
        "paired_labels": len(labels),
        "candidate_feature_rows": len(features),
        "target_wilson95_upper": target_wilson,
        "claim_boundary": "Fresh deterministic Qwen3-8B task-sanity labels; official benchmark scoring remains separate.",
    }]
    return final_rows, labels, summarize_labels(labels), scores, model, audit + qc_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--raw-shards", type=Path, nargs="+", required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--eps", type=float, default=0.03)
    parser.add_argument("--target-wilson95-upper", type=float, default=0.03)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--labels-output", type=Path, required=True)
    parser.add_argument("--label-summary-output", type=Path, required=True)
    parser.add_argument("--scores-output", type=Path, required=True)
    parser.add_argument("--qc-summary-output", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    jobs = load_jsonl(args.jobs)
    shards = [load_jsonl(path) for path in args.raw_shards]
    features = _csv_rows(args.features)
    final_rows, labels, label_summary, scores, model, combined = finalize(
        jobs, shards, features, args.eps, args.target_wilson95_upper
    )
    audit, qc_summary = combined[:1], combined[1:]
    write_jsonl(args.raw_output, final_rows)
    write_csv(args.labels_output, labels, LABEL_FIELDS)
    write_csv(args.label_summary_output, label_summary, LABEL_SUMMARY_FIELDS)
    write_csv(args.scores_output, scores, SCORE_FIELDS)
    write_csv(args.qc_summary_output, qc_summary, QC_SUMMARY_FIELDS)
    write_csv(args.audit_output, audit, AUDIT_FIELDS)
    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    args.model_output.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    record = audit[0]
    print(f"manifest={record['manifest_jobs']} completed={record['deduplicated_rows']} missing={record['missing_jobs']} failed={record['failed_jobs']} labels={record['paired_labels']}")
    return 0 if record["missing_jobs"] == 0 and record["failed_jobs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
