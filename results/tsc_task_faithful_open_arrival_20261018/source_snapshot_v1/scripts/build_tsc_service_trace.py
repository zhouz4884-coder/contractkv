#!/usr/bin/env python3
"""Freeze the five-family service trace used by the TSC extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


FAMILIES = {
    "RULER": lambda row: row.get("dataset") == "RULER",
    "HotpotQA": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "hotpotqa",
    "NarrativeQA": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "narrativeqa",
    "Qasper": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "qasper",
    "RepoBench": lambda row: row.get("dataset") == "RepoBench",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def select_sessions(rows: list[dict[str, Any]], per_family: int, seed: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for family, predicate in FAMILIES.items():
        candidates = [
            row for row in rows
            if predicate(row) and row.get("metadata", {}).get("phase14_partition") == "live_serving"
        ]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"tsc-service-v0|{seed}|{family}|{row.get('metadata', {}).get('source_group_id')}|{row.get('sample_id')}".encode()
        ).hexdigest())
        groups: set[str] = set()
        for row in candidates:
            group = str(row.get("metadata", {}).get("source_group_id", ""))
            if not group or group in groups:
                continue
            groups.add(group)
            index = len(groups) - 1
            selected.append({
                **row,
                "tsc_family": family,
                "tsc_session_id": f"tsc-{family.lower()}-{index:03d}",
                "tenant_id": f"tenant-{family.lower()}-{index:03d}",
                "service_template_id": f"service-{family.lower()}-{index // 5:02d}",
            })
            if len(groups) == per_family:
                break
        if len(groups) != per_family:
            raise RuntimeError(f"insufficient unique live-serving groups for {family}: {len(groups)}")
    return selected


def build_arrivals(sessions: list[dict[str, Any]], turns: int, seed: int) -> list[dict[str, Any]]:
    """Freeze unit-rate exponential gaps while preserving turn order per session."""
    rng = random.Random(seed)
    arrivals: list[dict[str, Any]] = []
    sequence = 0
    for turn in range(1, turns):
        wave = list(sessions)
        rng.shuffle(wave)
        for sample in wave:
            arrivals.append({
                "sequence": sequence,
                "session_id": sample["tsc_session_id"],
                "turn_id": turn,
                "unit_exponential_gap": rng.expovariate(1.0),
            })
            sequence += 1
    return arrivals


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--sessions-output", type=Path, required=True)
    parser.add_argument("--arrivals-output", type=Path, required=True)
    parser.add_argument("--commitment-output", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=25)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--seed", type=int, default=27001)
    args = parser.parse_args()
    sessions = select_sessions(load_jsonl(args.full_pool), args.per_family, args.seed)
    arrivals = build_arrivals(sessions, args.turns, args.seed + 1)
    write_jsonl(args.sessions_output, sessions)
    write_jsonl(args.arrivals_output, arrivals)
    commitment = {
        "schema_version": "tsc.service-trace.v0",
        "seed": args.seed,
        "families": dict(Counter(row["tsc_family"] for row in sessions)),
        "sessions": len(sessions),
        "turns_per_session": args.turns,
        "future_requests_per_cell": len(arrivals),
        "sessions_sha256": sha256(sessions),
        "arrivals_sha256": sha256(arrivals),
        "source_partition": "phase14/live_serving",
        "source_group_overlap": 0,
        "frozen_before_measurement": True,
    }
    args.commitment_output.parent.mkdir(parents=True, exist_ok=True)
    args.commitment_output.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(commitment, indent=2))
    return 0 if len(arrivals) >= 1000 else 2


if __name__ == "__main__":
    raise SystemExit(main())
