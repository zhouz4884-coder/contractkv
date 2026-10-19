#!/usr/bin/env python3
"""Freeze source-group-disjoint RULER sessions for the submission supplement."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def source_group(row: dict[str, Any]) -> str:
    return str((row.get("metadata") or {}).get("source_group_id", ""))


def digest_rows(rows: list[dict[str, Any]]) -> str:
    payload = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, action="append", default=[])
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--selection-salt", default="submission-ruler-extension-v0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    args = parser.parse_args()
    prior = [row for path in args.exclude for row in load(path)]
    used_keys = {sample_key(row) for row in prior}
    used_groups = {source_group(row) for row in prior if source_group(row)}
    candidates = [
        row for row in load(args.full_pool)
        if row.get("dataset") == "RULER"
        and row.get("task") == "niah_single_1"
        and (row.get("metadata") or {}).get("phase14_partition") == "live_serving"
        and sample_key(row) not in used_keys
        and source_group(row)
        and source_group(row) not in used_groups
    ]
    candidates.sort(key=lambda row: hashlib.sha256(
        f"{args.selection_salt}:{source_group(row)}:{row.get('sample_id')}".encode()).hexdigest())
    selected, selected_groups = [], set()
    for row in candidates:
        group = source_group(row)
        if group in selected_groups:
            continue
        selected_groups.add(group)
        sid = f"submission-ruler-ext-{row.get('sample_id')}"
        selected.append({**row, "phase19b_session_id": sid, "submission_extension": "ruler-source-disjoint-v0"})
        if len(selected) == args.count:
            break
    if len(selected) != args.count:
        raise RuntimeError(f"insufficient source-disjoint RULER sessions: {len(selected)}/{args.count}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    commitment = {
        "schema_version": "contractkv.submission-ruler-extension.v1",
        "selection_salt": args.selection_salt,
        "sessions": len(selected),
        "turns": 10,
        "source_group_overlap_with_prior": sum(source_group(row) in used_groups for row in selected),
        "sample_overlap_with_prior": sum(sample_key(row) in used_keys for row in selected),
        "selected_sha256": digest_rows(selected),
        "frozen_level": "L3",
        "heldout_opened_for_tuning": False,
        "claim_boundary": "Additional source-disjoint RULER qualified-scope replication; not a global Llama result.",
    }
    args.commitment.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(commitment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
