#!/usr/bin/env python3
"""Score one model's paired outputs on the frozen common RULER scope."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--pair", action="append", required=True, help="repeat,raw.jsonl,contract.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    sessions = {str(row["phase19b_session_id"]): row for row in load(args.sessions)}
    rows = []
    for spec in args.pair:
        repeat, raw_path, contract_path = spec.split(",", 2)
        raw = {(str(row["session_id"]), int(row["turn_id"])): row for row in load(Path(raw_path))
               if row.get("row_type") == "future"}
        contract = {(str(row["session_id"]), int(row["turn_id"])): row for row in load(Path(contract_path))
                    if row.get("row_type") == "future"}
        for key in sorted(raw.keys() & contract.keys()):
            sid, turn = key
            sample = sessions[sid]
            raw_score, metric, source = standard_score(
                str(sample["dataset"]), str(sample["task"]), str(raw[key].get("output_text", "")), sample.get("answer", ""))
            contract_score, _, _ = standard_score(
                str(sample["dataset"]), str(sample["task"]), str(contract[key].get("output_text", "")), sample.get("answer", ""))
            drop = max(0.0, raw_score - contract_score)
            rows.append({
                "model": args.model, "repeat": int(repeat), "session_id": sid, "turn_id": turn,
                "sample_id": sample["sample_id"], "raw_score": raw_score,
                "contract_score": contract_score, "quality_drop": drop,
                "quality_violation": drop > .03, "metric": metric, "metric_source": source,
                "certificate_issued": contract[key].get("certificate_issued", False),
                "certificate_scope_valid": contract[key].get("certificate_scope_valid", False),
                "effective_policy": contract[key].get("effective_policy", ""),
            })
    summary = {
        "model": args.model,
        "paired_future_outputs": len(rows),
        "mean_raw_score": statistics.fmean(float(row["raw_score"]) for row in rows) if rows else 0.0,
        "mean_contract_score": statistics.fmean(float(row["contract_score"]) for row in rows) if rows else 0.0,
        "mean_quality_drop": statistics.fmean(float(row["quality_drop"]) for row in rows) if rows else 0.0,
        "max_quality_drop": max((float(row["quality_drop"]) for row in rows), default=0.0),
        "quality_violations": sum(row["quality_violation"] for row in rows),
        "scope_invalid_admitted": sum(
            row["effective_policy"] != "raw-order" and not row["certificate_scope_valid"] for row in rows),
        "certificate_coverage": sum(row["certificate_issued"] is True for row in rows) / max(len(rows), 1),
    }
    summary["gate_pass"] = len(rows) == 810 and summary["quality_violations"] == 0 and summary["scope_invalid_admitted"] == 0
    summary["claim_boundary"] = "Fresh paired scoring on the frozen 30-session common RULER scope."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader(); writer.writerows(rows)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
