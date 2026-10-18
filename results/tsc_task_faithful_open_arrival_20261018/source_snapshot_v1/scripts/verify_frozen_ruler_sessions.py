#!/usr/bin/env python3
"""Verify that a common-scope replay consumes the frozen RULER split."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_extended_ruler_sessions import digest_rows, load


def verify(sessions: Path, commitment: Path, expected_sha256: str, expected_count: int, expected_turns: int) -> dict:
    rows = load(sessions)
    frozen = json.loads(commitment.read_text(encoding="utf-8"))
    actual_sha256 = digest_rows(rows)
    errors = []
    if actual_sha256 != expected_sha256:
        errors.append("session_sha256_mismatch")
    if frozen.get("selected_sha256") != expected_sha256:
        errors.append("commitment_sha256_mismatch")
    if len(rows) != expected_count or frozen.get("sessions") != expected_count:
        errors.append("session_count_mismatch")
    if frozen.get("turns") != expected_turns:
        errors.append("turn_count_mismatch")
    if len({str(row.get("phase19b_session_id")) for row in rows}) != expected_count:
        errors.append("session_id_not_unique")
    if any(row.get("dataset") != "RULER" or row.get("task") != "niah_single_1" for row in rows):
        errors.append("scope_mismatch")
    result = {
        "status": "pass" if not errors else "fail",
        "actual_sha256": actual_sha256,
        "sessions": len(rows),
        "turns": expected_turns,
        "errors": errors,
    }
    if errors:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-count", type=int, default=30)
    parser.add_argument("--expected-turns", type=int, default=10)
    args = parser.parse_args()
    result = verify(args.sessions, args.commitment, args.expected_sha256, args.expected_count, args.expected_turns)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
