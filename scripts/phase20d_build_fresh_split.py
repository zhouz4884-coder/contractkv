#!/usr/bin/env python3
"""Freeze source-group-disjoint Phase 20 development and sealed held-out splits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


FAMILIES = {
    "ruler": lambda row: row.get("dataset") == "RULER",
    "hotpotqa": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "hotpotqa",
    "narrativeqa": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "narrativeqa",
    "qasper": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "qasper",
    "repobench": lambda row: row.get("dataset") == "RepoBench",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def group_key(row: dict[str, Any]) -> str:
    return str((row.get("metadata") or {}).get("source_group_id") or "")


def digest_rows(rows: list[dict[str, Any]]) -> str:
    values = sorted((sample_key(row), group_key(row)) for row in rows)
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--phase19a-quality", type=Path, required=True)
    parser.add_argument("--prior-sessions", type=Path, action="append", default=[])
    parser.add_argument("--development-per-family", type=int, default=5)
    parser.add_argument("--heldout-per-family", type=int, default=10)
    parser.add_argument("--development-output", type=Path, required=True)
    parser.add_argument("--heldout-output", type=Path, required=True)
    parser.add_argument("--commitment-output", type=Path, required=True)
    args = parser.parse_args()

    with args.phase19a_quality.open(encoding="utf-8", newline="") as handle:
        used_keys = {row["sample_key"] for row in csv.DictReader(handle)}
    prior = [row for path in args.prior_sessions for row in load_jsonl(path)]
    used_keys.update(sample_key(row) for row in prior)
    used_groups = {group_key(row) for row in prior if group_key(row)}
    pool = load_jsonl(args.full_pool)
    development: list[dict[str, Any]] = []
    heldout: list[dict[str, Any]] = []
    selected_groups = set(used_groups)
    needed = args.development_per_family + args.heldout_per_family
    for family, predicate in FAMILIES.items():
        candidates = [row for row in pool if predicate(row)
                      and (row.get("metadata") or {}).get("phase14_partition") == "live_serving"
                      and sample_key(row) not in used_keys and group_key(row)
                      and group_key(row) not in selected_groups]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"phase20:{family}:{group_key(row)}:{row.get('sample_id')}".encode()).hexdigest())
        unique: list[dict[str, Any]] = []
        local_groups = set()
        for row in candidates:
            group = group_key(row)
            if group in local_groups or group in selected_groups:
                continue
            local_groups.add(group); selected_groups.add(group)
            session_id = f"phase20-{family}-{row.get('sample_id')}"
            unique.append({**row, "phase20_family": family,
                           "phase20_session_id": session_id,
                           "phase19b_session_id": session_id})
            if len(unique) == needed:
                break
        if len(unique) != needed:
            raise RuntimeError(f"insufficient untouched source groups for {family}: {len(unique)}/{needed}")
        development.extend({**row, "phase20_partition": "development"}
                           for row in unique[:args.development_per_family])
        heldout.extend({**row, "phase20_partition": "held_out_sealed"}
                       for row in unique[args.development_per_family:])

    for path, rows in ((args.development_output, development), (args.heldout_output, heldout)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    commitment = {
        "schema_version": "phase20.fresh-split.v1", "development_count": len(development),
        "heldout_count": len(heldout), "development_hash": digest_rows(development),
        "heldout_hash": digest_rows(heldout), "sample_overlap": len({sample_key(x) for x in development} & {sample_key(x) for x in heldout}),
        "source_group_overlap": len({group_key(x) for x in development} & {group_key(x) for x in heldout}),
        "prior_sample_overlap": sum(sample_key(x) in used_keys for x in development + heldout),
        "prior_source_group_overlap": sum(group_key(x) in used_groups for x in development + heldout),
        "families": {family: {"development": sum(x["phase20_family"] == family for x in development),
                               "heldout": sum(x["phase20_family"] == family for x in heldout)}
                     for family in FAMILIES},
        "heldout_opened_for_tuning": False,
    }
    args.commitment_output.parent.mkdir(parents=True, exist_ok=True)
    args.commitment_output.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(commitment, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
