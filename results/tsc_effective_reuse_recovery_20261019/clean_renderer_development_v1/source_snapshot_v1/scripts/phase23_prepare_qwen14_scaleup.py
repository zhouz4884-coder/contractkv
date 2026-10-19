#!/usr/bin/env python3
"""Freeze source-group-disjoint Qwen3-14B scale-up sessions and policy transfer."""

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


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--phase19a-quality", type=Path, required=True)
    parser.add_argument("--prior-sessions", type=Path, action="append", default=[])
    parser.add_argument("--sessions-per-family", type=int, default=5)
    parser.add_argument("--selection-salt", default="qwen3-14b-tp2-scaleup-v0")
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--source-policy-hash", required=True)
    parser.add_argument("--sessions-output", type=Path, required=True)
    parser.add_argument("--commitment-output", type=Path, required=True)
    parser.add_argument("--policy-manifest-output", type=Path, required=True)
    args = parser.parse_args()

    with args.phase19a_quality.open(encoding="utf-8", newline="") as handle:
        used_keys = {row["sample_key"] for row in csv.DictReader(handle)}
    prior = [row for path in args.prior_sessions for row in load_jsonl(path)]
    used_keys.update(sample_key(row) for row in prior)
    used_groups = {group_key(row) for row in prior if group_key(row)}
    selected_groups = set(used_groups)
    pool = load_jsonl(args.full_pool)
    sessions: list[dict[str, Any]] = []
    available_counts: dict[str, int] = {}
    for fam, predicate in FAMILIES.items():
        candidates = [
            row for row in pool
            if predicate(row)
            and (row.get("metadata") or {}).get("phase14_partition") == "live_serving"
            and sample_key(row) not in used_keys
            and group_key(row)
            and group_key(row) not in selected_groups
        ]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"{args.selection_salt}:{fam}:{group_key(row)}:{row.get('sample_id')}".encode()
        ).hexdigest())
        unique: list[dict[str, Any]] = []
        local_groups = set()
        for row in candidates:
            group = group_key(row)
            if group in local_groups or group in selected_groups:
                continue
            local_groups.add(group)
            available_counts[fam] = available_counts.get(fam, 0) + 1
            if len(unique) < args.sessions_per_family:
                selected_groups.add(group)
                sid = f"qwen14-{fam}-{row.get('sample_id')}"
                unique.append({
                    **row, "phase23_family": fam, "phase23_session_id": sid,
                    "phase19b_session_id": sid, "phase23_partition": "frozen_scaleup",
                })
        if len(unique) != args.sessions_per_family:
            raise RuntimeError(f"insufficient untouched source groups for {fam}: {len(unique)}/{args.sessions_per_family}")
        sessions.extend(unique)

    args.sessions_output.parent.mkdir(parents=True, exist_ok=True)
    args.sessions_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in sessions), encoding="utf-8"
    )
    commitment = {
        "schema_version": "contractkv.qwen3-14b-scaleup-split.v1",
        "selection_salt": args.selection_salt,
        "session_count": len(sessions),
        "sessions_per_family": args.sessions_per_family,
        "sessions_sha256": digest_rows(sessions),
        "sample_overlap_with_prior": sum(sample_key(row) in used_keys for row in sessions),
        "source_group_overlap_with_prior": sum(group_key(row) in used_groups for row in sessions),
        "selected_source_groups_unique": len({group_key(row) for row in sessions}) == len(sessions),
        "available_untouched_source_groups_at_freeze": available_counts,
        "families": {fam: sum(row["phase23_family"] == fam for row in sessions) for fam in FAMILIES},
        "opened_for_tuning": False,
    }
    args.commitment_output.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    policy = {
        "schema_version": "contractkv.qwen3-14b-policy-transfer.v1",
        "model_identity": args.model_identity,
        "source_architecture_policy": "Qwen3-8B Phase19B contractkv-full",
        "source_policy_hash": args.source_policy_hash,
        "online_turn0_verification_required": True,
        "certificate_scope_mode": "qualified_session",
        "concurrency": 2,
        "tensor_parallel_size": 2,
        "dtype": "float16",
        "max_model_len": 8192,
        "max_num_seqs": 2,
        "max_tokens": 96,
        "stable_word_limit": 2600,
        "tool_slack_ms": 2000,
        "repeats": 3,
        "session_commitment_sha256": hashlib.sha256(args.commitment_output.read_bytes()).hexdigest(),
        "claim_boundary": (
            "Limited TP=2 architecture-policy transfer with model-local Turn-0 verification; "
            "not a Qwen3-14B-specific threshold calibration."
        ),
    }
    policy["qualification_hash"] = canonical_hash(policy)
    args.policy_manifest_output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"commitment": commitment, "policy": policy}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
