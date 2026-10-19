#!/usr/bin/env python3
"""Repair the pre-fix scope telemetry without changing executed policy data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repair(path: Path) -> dict[str, Any]:
    original = path.read_bytes()
    rows = [json.loads(line) for line in original.decode("utf-8").splitlines()
            if line.strip()]
    repaired = 0
    for row in rows:
        if row.get("row_type") != "future" or row.get("policy") != "contractkv-full":
            continue
        expected_valid = row.get("effective_policy") != "raw-order"
        expected_errors = [] if expected_valid else [
            "certificate_missing_or_unissued"
            if row.get("certificate_issued") is not True
            else "scope_invalid_fail_closed"
        ]
        if (row.get("certificate_scope_valid") != expected_valid
                or row.get("certificate_scope_errors") != expected_errors):
            row["scope_telemetry_original_valid"] = row.get("certificate_scope_valid")
            row["scope_telemetry_original_errors"] = row.get("certificate_scope_errors")
            row["certificate_scope_valid"] = expected_valid
            row["certificate_scope_errors"] = expected_errors
            row["scope_telemetry_repaired"] = True
            repaired += 1
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {
        "path": str(path),
        "original_sha256": sha256(original),
        "repaired_sha256": sha256(payload),
        "rows": len(rows),
        "telemetry_rows_repaired": repaired,
        "executed_policy_rows_changed": 0,
        "timing_or_prefix_metrics_changed": 0,
        "reason": "pre-fix async completion used the final loop scope_errors value; executed effective_policy was already request-local",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    records = [repair(path) for path in args.input]
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "repair": "submission_scope_telemetry_v1",
        "records": records,
        "claim_boundary": "telemetry-only correction; request execution, timing, output, and physical prefix metrics are unchanged",
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
