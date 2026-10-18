#!/usr/bin/env python3
"""Freeze model-specific session quality labels from paired live layouts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
    "session_id", "dataset", "task", "sample_id", "paired_turns",
    "quality_label", "max_quality_drop", "mean_quality_drop",
    "certificate_issued", "unsafe_certified", "raw_mean_new_prefill_tokens",
    "candidate_mean_new_prefill_tokens", "full_mean_new_prefill_tokens",
    "available_prefix_gain_tokens", "retained_prefix_gain_tokens",
    "retained_prefix_gain_rate",
]


def load_jsonl(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def truth(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def prefill_tokens(row: dict[str, Any]) -> float:
    if row.get("prompt_tokens", "") != "" and row.get("prefix_hit_tokens", "") != "":
        return max(0.0, number(row["prompt_tokens"]) - number(row["prefix_hit_tokens"]))
    return number(row.get("new_prefill_tokens"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--quality-epsilon", type=float, default=.03)
    parser.add_argument("--policy-hash", default="")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    rows = load_jsonl(args.inputs)
    future = [row for row in rows if row.get("row_type") == "future" and truth(row.get("success"))]
    by_policy: dict[str, dict[tuple[str, int], dict[str, Any]]] = defaultdict(dict)
    for row in future:
        by_policy[str(row["policy"])][(str(row["session_id"]), int(row["turn_id"]))] = row
    raw = by_policy["raw-order"]
    candidate = by_policy["physical-cache-aware"]
    full = by_policy.get("contractkv-full", {})
    sessions = sorted({sid for sid, _ in raw} | {sid for sid, _ in candidate})
    labels = []
    for sid in sessions:
        paired = sorted(turn for session, turn in raw if session == sid and (sid, turn) in candidate)
        exemplar = next((raw[(sid, turn)] for turn in paired), None)
        if exemplar is None:
            continue
        drops = [max(0.0, number(raw[(sid, turn)].get("task_score")) -
                         number(candidate[(sid, turn)].get("task_score"))) for turn in paired]
        expected_turns = sorted(turn for session, turn in raw if session == sid)
        label = "incomplete" if paired != expected_turns else (
            "unsafe" if any(value > args.quality_epsilon for value in drops) else "safe"
        )
        certificate = any(truth(row.get("certificate_issued")) for (session, _), row in full.items() if session == sid)
        raw_prefill = [prefill_tokens(raw[(sid, turn)]) for turn in paired]
        candidate_prefill = [prefill_tokens(candidate[(sid, turn)]) for turn in paired]
        full_prefill = [prefill_tokens(full[(sid, turn)]) for turn in paired if (sid, turn) in full]
        raw_mean = statistics.mean(raw_prefill) if raw_prefill else 0.0
        candidate_mean = statistics.mean(candidate_prefill) if candidate_prefill else 0.0
        full_mean = statistics.mean(full_prefill) if full_prefill else raw_mean
        available = max(0.0, raw_mean - candidate_mean)
        retained = max(0.0, raw_mean - full_mean)
        labels.append({
            "session_id": sid, "dataset": exemplar.get("dataset", ""),
            "task": exemplar.get("task", ""), "sample_id": exemplar.get("sample_id", ""),
            "paired_turns": len(paired), "quality_label": label,
            "max_quality_drop": max(drops, default=0.0),
            "mean_quality_drop": statistics.mean(drops) if drops else 0.0,
            "certificate_issued": certificate,
            "unsafe_certified": label == "unsafe" and certificate,
            "raw_mean_new_prefill_tokens": raw_mean,
            "candidate_mean_new_prefill_tokens": candidate_mean,
            "full_mean_new_prefill_tokens": full_mean,
            "available_prefix_gain_tokens": available,
            "retained_prefix_gain_tokens": retained,
            "retained_prefix_gain_rate": retained / max(.001, available),
        })
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(labels)
    safe = [row for row in labels if row["quality_label"] == "safe"]
    unsafe = [row for row in labels if row["quality_label"] == "unsafe"]
    summary = {
        "policy_hash": args.policy_hash,
        "sessions": len(labels), "safe_sessions": len(safe),
        "unsafe_sessions": len(unsafe),
        "incomplete_sessions": sum(row["quality_label"] == "incomplete" for row in labels),
        "safe_certified": sum(truth(row["certificate_issued"]) for row in safe),
        "unsafe_certified": sum(truth(row["certificate_issued"]) for row in unsafe),
        "safe_coverage": sum(truth(row["certificate_issued"]) for row in safe) / max(1, len(safe)),
        "retained_prefix_gain_rate": sum(number(row["retained_prefix_gain_tokens"]) for row in labels) /
                                     max(.001, sum(number(row["available_prefix_gain_tokens"]) for row in labels)),
        "quality_epsilon": args.quality_epsilon,
    }
    args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["labels_sha256"] = file_hash(args.output_csv)
    args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
