#!/usr/bin/env python3
"""Aggregate per-request quality rows for the common three-model RULER scope."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def summarize(label: str, path: Path) -> dict[str, Any]:
    rows = load_csv(path)
    result = {
        "model": label,
        "paired_future_outputs": len(rows),
        "mean_raw_score": statistics.fmean(float(row["raw_score"]) for row in rows),
        "mean_contract_score": statistics.fmean(float(row["contract_score"]) for row in rows),
        "mean_quality_drop": statistics.fmean(float(row["quality_drop"]) for row in rows),
        "max_quality_drop": max(float(row["quality_drop"]) for row in rows),
        "quality_violations": sum(truth(row["quality_violation"]) for row in rows),
        "scope_invalid_admitted": sum(
            str(row.get("effective_policy", "")) != "raw-order"
            and not truth(row.get("certificate_scope_valid", "")) for row in rows),
        "certificate_coverage": sum(truth(row.get("certificate_issued", "")) for row in rows) / max(len(rows), 1),
    }
    result["gate_pass"] = len(rows) == 810 and result["quality_violations"] == 0 and result["scope_invalid_admitted"] == 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", action="append", required=True, help="label,path")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    rows = [summarize(label, Path(path)) for label, path in (spec.split(",", 1) for spec in args.quality)]
    total = sum(int(row["paired_future_outputs"]) for row in rows)
    macro = {
        "model": "cross-model-total", "paired_future_outputs": total,
        "mean_raw_score": sum(row["mean_raw_score"] * row["paired_future_outputs"] for row in rows) / total,
        "mean_contract_score": sum(row["mean_contract_score"] * row["paired_future_outputs"] for row in rows) / total,
        "mean_quality_drop": sum(row["mean_quality_drop"] * row["paired_future_outputs"] for row in rows) / total,
        "max_quality_drop": max(row["max_quality_drop"] for row in rows),
        "quality_violations": sum(row["quality_violations"] for row in rows),
        "scope_invalid_admitted": sum(row["scope_invalid_admitted"] for row in rows),
        "certificate_coverage": sum(row["certificate_coverage"] * row["paired_future_outputs"] for row in rows) / total,
        "gate_pass": all(row["gate_pass"] for row in rows),
    }
    rows.append(macro)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    args.json_output.write_text(json.dumps({"status": "complete", "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "rows": rows}, indent=2))
    return 0 if macro["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
