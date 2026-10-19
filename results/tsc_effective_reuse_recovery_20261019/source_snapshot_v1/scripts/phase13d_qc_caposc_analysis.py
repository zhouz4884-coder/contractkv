#!/usr/bin/env python3
"""Summarize the Phase 13D QC-CAPOSC Qasper replay."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = ["policy", "num_samples", "success_rate", "mean_score", "raw_mean_score", "mean_signed_delta", "fallback_count", "raw_prompt_hash_match_count", "raw_output_match_count", "claim_boundary"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/end_to_end/phase13d_qc_caposc_qasper_raw_v1.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/end_to_end/phase13d_qc_caposc_qasper_summary_v1.csv"))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_sample: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_sample[str(row["sample_id"])][str(row["policy"])] = row
    output = []
    for policy in ["raw-order", "contractkv-caposc", "qc-caposc"]:
        group = [item[policy] for item in by_sample.values() if policy in item]
        raw_scores = [float(item["raw-order"]["score"]) for item in by_sample.values() if "raw-order" in item and policy in item]
        scores = [float(row["score"]) for row in group]
        output.append({
            "policy": policy, "num_samples": len(group), "success_rate": round(sum(bool(row["success"]) for row in group) / len(group), 6) if group else 0.0,
            "mean_score": round(statistics.mean(scores), 6) if scores else 0.0, "raw_mean_score": round(statistics.mean(raw_scores), 6) if raw_scores else 0.0,
            "mean_signed_delta": round(statistics.mean(score - raw for score, raw in zip(scores, raw_scores)), 6) if scores else 0.0,
            "fallback_count": sum(bool(row.get("risk_fallback")) for row in group),
            "raw_prompt_hash_match_count": sum(row.get("prompt_hash") == by_sample[str(row["sample_id"])]["raw-order"].get("prompt_hash") for row in group if "raw-order" in by_sample[str(row["sample_id"])]),
            "raw_output_match_count": sum(row.get("output_text") == by_sample[str(row["sample_id"])]["raw-order"].get("output_text") for row in group if "raw-order" in by_sample[str(row["sample_id"])]),
            "claim_boundary": "Fresh Qasper sanity; prompt-identical QC fallback validates no-regret layout behavior, not official LongBench scoring.",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output)
    print(f"qc_summary_rows={len(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
