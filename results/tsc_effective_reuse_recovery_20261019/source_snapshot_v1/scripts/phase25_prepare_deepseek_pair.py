#!/usr/bin/env python3
"""Freeze Phase 25 inputs and build the development-only compatibility subset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_FAMILIES = {
    "RULER:niah_single_1",
    "LongBench:hotpotqa",
    "LongBench:narrativeqa",
    "LongBench:qasper",
    "RepoBench:python_v1.1",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def family(row: dict[str, Any]) -> str:
    return f"{row.get('dataset', '')}:{row.get('task', '')}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--preflight-output", type=Path, required=True)
    parser.add_argument("--commitment-output", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    development = load_jsonl(args.development)
    heldout = load_jsonl(args.heldout)
    expected_dev = int(protocol["workload"]["development_sessions_per_family"])
    expected_heldout = int(protocol["workload"]["heldout_sessions_per_family"])
    preflight_per_family = int(protocol["workload"]["preflight_sessions_per_family"])

    for label, rows, expected in (
        ("development", development, expected_dev),
        ("heldout", heldout, expected_heldout),
    ):
        counts = Counter(family(row) for row in rows)
        if set(counts) != EXPECTED_FAMILIES:
            raise RuntimeError(f"{label} family mismatch: {sorted(counts)}")
        if any(count != expected for count in counts.values()):
            raise RuntimeError(f"{label} count mismatch: {dict(counts)}")

    dev_ids = {str(row["phase19b_session_id"]) for row in development}
    heldout_ids = {str(row["phase19b_session_id"]) for row in heldout}
    if dev_ids & heldout_ids:
        raise RuntimeError("development and heldout session IDs overlap")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in development:
        grouped[family(row)].append(row)
    preflight = []
    for key in sorted(EXPECTED_FAMILIES):
        selected = sorted(grouped[key], key=lambda row: str(row["phase19b_session_id"]))[:preflight_per_family]
        preflight.extend(selected)
    args.preflight_output.parent.mkdir(parents=True, exist_ok=True)
    args.preflight_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in preflight), encoding="utf-8"
    )

    commitment = {
        "schema_version": "contractkv.phase25.deepseek-pair-commitment.v1",
        "protocol_sha256": sha256(args.protocol),
        "protocol_hash": canonical_hash(protocol),
        "development_path": str(args.development),
        "development_sha256": sha256(args.development),
        "development_sessions": len(development),
        "heldout_path": str(args.heldout),
        "heldout_sha256": sha256(args.heldout),
        "heldout_sessions": len(heldout),
        "preflight_path": str(args.preflight_output),
        "preflight_sha256": sha256(args.preflight_output),
        "preflight_sessions": len(preflight),
        "sample_overlap": 0,
        "heldout_opened_for_retuning": False,
        "frozen_models": protocol["models"],
        "frozen_runtime": protocol["runtime"],
        "frozen_gates": protocol["primary_gates"],
    }
    args.commitment_output.parent.mkdir(parents=True, exist_ok=True)
    args.commitment_output.write_text(json.dumps(commitment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"preflight_sessions": len(preflight), "commitment_hash": canonical_hash(commitment)}, indent=2))


if __name__ == "__main__":
    main()
