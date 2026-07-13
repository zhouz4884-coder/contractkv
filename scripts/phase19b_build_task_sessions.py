#!/usr/bin/env python3
"""Build an untouched Phase 19B task-bearing live-serving session split."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--phase19a-quality", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.phase19a_quality.open(encoding="utf-8", newline="") as handle:
        used = {row["sample_key"] for row in csv.DictReader(handle)}
    families = {
        "ruler": lambda row: row.get("dataset") == "RULER",
        "hotpotqa": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "hotpotqa",
        "narrativeqa": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "narrativeqa",
        "qasper": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "qasper",
        "repobench": lambda row: row.get("dataset") == "RepoBench",
    }
    selected = []
    for family, predicate in families.items():
        candidates = [row for row in load_jsonl(args.full_pool)
                      if predicate(row)
                      and row.get("metadata", {}).get("phase14_partition") == "live_serving"
                      and key(row) not in used]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"phase19b:{family}:{row.get('metadata', {}).get('source_group_id')}:{row.get('sample_id')}".encode()
        ).hexdigest())
        groups = set()
        for row in candidates:
            group = str(row.get("metadata", {}).get("source_group_id", ""))
            if not group or group in groups:
                continue
            groups.add(group)
            selected.append({**row, "phase19b_family": family,
                             "phase19b_session_id": f"{family}-{row.get('sample_id')}"})
            if len(groups) == args.per_family:
                break
        if len(groups) != args.per_family:
            raise RuntimeError(f"insufficient untouched {family} sessions")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    print(json.dumps({"sessions": len(selected), "phase19a_overlap": sum(key(row) in used for row in selected),
                      "families": {name: sum(row["phase19b_family"] == name for row in selected) for name in families}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
