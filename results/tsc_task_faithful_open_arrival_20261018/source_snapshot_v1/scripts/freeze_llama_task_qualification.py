#!/usr/bin/env python3
"""Freeze prospective Llama task-family qualification from development only."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--minimum-development-sessions", type=int, default=5)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--qualified-heldout", type=Path, required=True)
    args = parser.parse_args()
    development = load(args.development)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in development:
        grouped[f"{row.get('dataset', '')}:{row.get('task', '')}"].append(row)
    decisions = []
    qualified = []
    for family, rows in sorted(grouped.items()):
        passed = sum(row.get("certificate_issued") is True for row in rows)
        errors = sum(str(row.get("error_type", "none")) != "none" for row in rows)
        eligible = len(rows) >= args.minimum_development_sessions and passed == len(rows) and errors == 0
        decisions.append({
            "task_family": family, "development_sessions": len(rows),
            "strict_certificates": passed, "errors": errors,
            "qualified": eligible,
            "reason": ("all_development_sessions_strictly_certified" if eligible
                       else "fail_closed_incomplete_development_coverage"),
        })
        if eligible:
            qualified.append(family)
    frozen = {
        "schema_version": "contractkv.llama-task-qualification.v1",
        "model_identity": args.model_identity,
        "qualification_basis": "development_only_all_sessions_strict_certificate",
        "minimum_development_sessions": args.minimum_development_sessions,
        "development_source_sha256": hashlib.sha256(args.development.read_bytes()).hexdigest(),
        "heldout_opened_for_tuning": False,
        "decisions": decisions,
        "qualified_task_families": qualified,
        "fallback": "raw-order",
        "claim_boundary": ("Qualification is task-family scoped and prospective. It is not a universal Llama certificate; "
                           "all unqualified families fail closed to raw order."),
    }
    frozen["qualification_hash"] = canonical_hash(frozen)
    heldout = [row for row in load(args.heldout)
               if f"{row.get('dataset', '')}:{row.get('task', '')}" in set(qualified)]
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    args.qualified_heldout.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in heldout), encoding="utf-8")
    print(json.dumps({"qualified": qualified, "heldout_sessions": len(heldout),
                      "qualification_hash": frozen["qualification_hash"]}, indent=2))
    return 0 if qualified and heldout else 2


if __name__ == "__main__":
    raise SystemExit(main())
