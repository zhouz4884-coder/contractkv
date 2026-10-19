#!/usr/bin/env python3
"""Freeze a second, source-group-disjoint prospective Llama split."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20d_build_fresh_split import FAMILIES, digest_rows, group_key, load_jsonl, sample_key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--phase19a-quality", type=Path, required=True)
    parser.add_argument("--prior-sessions", type=Path, action="append", default=[])
    parser.add_argument("--development-per-family", type=int, default=5)
    parser.add_argument("--heldout-per-family", type=int, default=10)
    parser.add_argument("--selection-salt", default="llama-broad-r1-v1")
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
        candidates = [
            row for row in pool
            if predicate(row)
            and (row.get("metadata") or {}).get("phase14_partition") == "live_serving"
            and sample_key(row) not in used_keys
            and group_key(row)
            and group_key(row) not in selected_groups
        ]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"{args.selection_salt}:{family}:{group_key(row)}:{row.get('sample_id')}".encode()
        ).hexdigest())
        selected: list[dict[str, Any]] = []
        for row in candidates:
            group = group_key(row)
            if group in selected_groups:
                continue
            selected_groups.add(group)
            sid = f"phase22r-{family}-{row.get('sample_id')}"
            selected.append({
                **row, "phase22r_family": family, "phase22r_session_id": sid,
                "phase19b_session_id": sid,
            })
            if len(selected) == needed:
                break
        if len(selected) != needed:
            raise RuntimeError(f"insufficient untouched source groups for {family}: {len(selected)}/{needed}")
        development.extend({**row, "phase22r_partition": "development"} for row in selected[:args.development_per_family])
        heldout.extend({**row, "phase22r_partition": "heldout_sealed"} for row in selected[args.development_per_family:])

    for path, rows in ((args.development_output, development), (args.heldout_output, heldout)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    commitment = {
        "schema_version": "contractkv.llama-broad-r1-split.v1",
        "selection_salt": args.selection_salt,
        "development_count": len(development), "heldout_count": len(heldout),
        "development_sha256": digest_rows(development), "heldout_sha256": digest_rows(heldout),
        "sample_overlap": len({sample_key(x) for x in development} & {sample_key(x) for x in heldout}),
        "source_group_overlap": len({group_key(x) for x in development} & {group_key(x) for x in heldout}),
        "prior_sample_overlap": sum(sample_key(x) in used_keys for x in development + heldout),
        "prior_source_group_overlap": sum(group_key(x) in used_groups for x in development + heldout),
        "families": {
            family: {
                "development": sum(x["phase22r_family"] == family for x in development),
                "heldout": sum(x["phase22r_family"] == family for x in heldout),
            } for family in FAMILIES
        },
        "heldout_opened_for_tuning": False,
    }
    args.commitment_output.parent.mkdir(parents=True, exist_ok=True)
    args.commitment_output.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(commitment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
