#!/usr/bin/env python3
"""Freeze five semantically coherent service templates for task-quality audit."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


FAMILIES = ("RULER", "HotpotQA", "NarrativeQA", "Qasper", "RepoBench")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build(sessions: list[dict[str, Any]], tenants_per_template: int) -> list[dict[str, Any]]:
    representatives: dict[str, dict[str, Any]] = {}
    for row in sorted(sessions, key=lambda item: str(item["tsc_session_id"])):
        representatives.setdefault(str(row["tsc_family"]), row)
    missing = set(FAMILIES) - set(representatives)
    if missing:
        raise ValueError(f"missing service-template families: {sorted(missing)}")

    output = []
    for family in FAMILIES:
        source = representatives[family]
        template_id = f"tsc-quality-{family.lower()}-v0"
        for tenant in range(tenants_per_template):
            row = copy.deepcopy(source)
            row["tsc_session_id"] = f"tsc-quality-{family.lower()}-tenant-{tenant:02d}"
            row["tenant_id"] = f"quality-tenant-{family.lower()}-{tenant:02d}"
            row["service_template_id"] = template_id
            row.setdefault("metadata", {}).update({
                "authorization_domain": template_id,
                "service_epoch": 1,
                "tsc_quality_source_session": source["tsc_session_id"],
                "tsc_quality_source_group": source.get("metadata", {}).get("source_group_id", ""),
                "tsc_quality_semantic_replica": True,
            })
            output.append(row)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--tenants-per-template", type=int, default=10)
    parser.add_argument("--turns", type=int, default=10)
    args = parser.parse_args()
    rows = build(load_jsonl(args.sessions), args.tenants_per_template)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    commitment = {
        "schema_version": "tsc.service-template-quality-trace.v0",
        "families": dict(Counter(str(row["tsc_family"]) for row in rows)),
        "service_templates": len({row["service_template_id"] for row in rows}),
        "authorized_tenants": len(rows),
        "turns_per_tenant": args.turns,
        "future_requests_per_policy_repeat": len(rows) * (args.turns - 1),
        "semantic_rule": "Each tenant consumes an exact copy of its service template's context, query, and answer; only neutral TOOL_OBS identity varies.",
        "sessions_sha256": digest(rows),
        "frozen_before_measurement": True,
    }
    args.commitment.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(commitment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
