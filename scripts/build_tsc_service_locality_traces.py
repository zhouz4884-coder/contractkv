#!/usr/bin/env python3
"""Freeze service-template locality variants without changing arrivals."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DYNAMIC_TYPES = {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def digest(rows: list[dict[str, Any]]) -> str:
    value = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def stable_segments(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(segment) for segment in row["segments"]
            if str(segment.get("type", segment.get("segment_type", ""))) not in DYNAMIC_TYPES]


def replace_stable(row: dict[str, Any], replacement: list[dict[str, Any]]) -> dict[str, Any]:
    output = copy.deepcopy(row)
    dynamic = [copy.deepcopy(segment) for segment in row["segments"]
               if str(segment.get("type", segment.get("segment_type", ""))) in DYNAMIC_TYPES]
    output["segments"] = copy.deepcopy(replacement) + dynamic
    output["total_prompt_tokens"] = sum(int(segment.get("token_count", 0) or 0) for segment in output["segments"])
    return output


def variant(sessions: list[dict[str, Any]], tenants_per_template: int) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sessions:
        by_family[str(row["tsc_family"])].append(row)
    output = []
    for family, rows in sorted(by_family.items()):
        rows.sort(key=lambda row: str(row["tsc_session_id"]))
        for index in range(0, len(rows), tenants_per_template):
            cohort = rows[index:index + tenants_per_template]
            shared = stable_segments(cohort[0])
            template_id = f"tsc-locality-{family.lower()}-g{tenants_per_template}-{index // tenants_per_template:02d}"
            for row in cohort:
                item = replace_stable(row, shared)
                item["service_template_id"] = template_id
                item.setdefault("metadata", {}).update({
                    "tsc_locality_tenants_per_template": tenants_per_template,
                    "tsc_locality_template_id": template_id,
                    "tsc_locality_source_session": cohort[0]["tsc_session_id"],
                    "private_suffix_preserved": True,
                })
                output.append(item)
    return sorted(output, key=lambda row: str(row["tsc_session_id"]))


def variant_template_count(sessions: list[dict[str, Any]], template_count: int) -> list[dict[str, Any]]:
    if template_count % 5 or template_count < 5:
        raise ValueError("mixed five-family variants require a multiple of five templates")
    per_family = template_count // 5
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sessions:
        by_family[str(row["tsc_family"])].append(row)
    output = []
    for family, rows in sorted(by_family.items()):
        rows.sort(key=lambda row: str(row["tsc_session_id"]))
        groups = [[] for _ in range(per_family)]
        for index, row in enumerate(rows):
            groups[index % per_family].append(row)
        for group_index, cohort in enumerate(groups):
            if not cohort:
                continue
            shared = stable_segments(cohort[0])
            template_id = f"tsc-residency-{family.lower()}-t{template_count}-{group_index:02d}"
            for row in cohort:
                item = replace_stable(row, shared)
                item["service_template_id"] = template_id
                item.setdefault("metadata", {}).update({
                    "tsc_active_template_count": template_count,
                    "tsc_locality_template_id": template_id,
                    "tsc_locality_source_session": cohort[0]["tsc_session_id"],
                    "private_suffix_preserved": True,
                })
                output.append(item)
    return sorted(output, key=lambda row: str(row["tsc_session_id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--levels", default="1,5,25")
    parser.add_argument("--template-counts", default="5,25,50")
    args = parser.parse_args()
    sessions = load_jsonl(args.sessions)
    manifest = {"schema_version": "tsc.service-locality.v0", "source_sessions_sha256": digest(sessions), "levels": {}}
    for level in [int(value) for value in args.levels.split(",")]:
        rows = variant(sessions, level)
        path = args.output_dir / f"tsc_service_sessions_locality_g{level}_v0.jsonl"
        write_jsonl(path, rows)
        templates = {row["service_template_id"] for row in rows}
        manifest["levels"][str(level)] = {
            "sessions": len(rows), "service_templates": len(templates),
            "tenants_per_template": level, "sha256": digest(rows), "path": str(path),
        }
    manifest["template_counts"] = {}
    for count in [int(value) for value in args.template_counts.split(",")]:
        rows = variant_template_count(sessions, count)
        path = args.output_dir / f"tsc_service_sessions_templates_t{count}_v0.jsonl"
        write_jsonl(path, rows)
        manifest["template_counts"][str(count)] = {
            "sessions": len(rows), "service_templates": len({row["service_template_id"] for row in rows}),
            "sha256": digest(rows), "path": str(path),
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "tsc_service_locality_commitment_v0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
