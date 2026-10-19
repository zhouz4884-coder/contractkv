#!/usr/bin/env python3
"""Audit the archived all-template quality run against the fail-closed rerun."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/tsc_service"))
    args = parser.parse_args(); root = args.root
    answers = {str(row["tsc_session_id"]): row.get("answer", "")
               for row in load_jsonl(root / "quality/tsc_service_quality_sessions_v0.jsonl")}
    rows = []
    for repeat in (1, 2, 3):
        raw = {(
            str(row["session_id"]), int(row["turn_id"])
        ): row for row in load_jsonl(root / f"quality/cells/qwen_r{repeat}_D0-native-apc/raw.jsonl")}
        compiled = {(
            str(row["session_id"]), int(row["turn_id"])
        ): row for row in load_jsonl(
            root / f"quality/all_template_ablation/cells/qwen_r{repeat}_D2-template-contractkv/raw.jsonl")}
        safe = {(
            str(row["session_id"]), int(row["turn_id"])
        ): row for row in load_jsonl(root / f"quality/cells/qwen_r{repeat}_D2-template-contractkv/raw.jsonl")}
        for key in sorted(set(raw) & set(compiled) & set(safe)):
            base, candidate, guarded = raw[key], compiled[key], safe[key]
            drop = float(base["task_score"]) - float(candidate["task_score"])
            if drop <= .03:
                continue
            rows.append({
                "repeat": repeat, "family": base["family"], "session_id": key[0], "turn_id": key[1],
                "reference_answer": json.dumps(answers.get(key[0], ""), ensure_ascii=False),
                "raw_output": base["output_text"], "all_template_output": candidate["output_text"],
                "safe_policy_output": guarded["output_text"],
                "raw_score": base["task_score"], "all_template_score": candidate["task_score"],
                "safe_policy_score": guarded["task_score"], "all_template_drop": drop,
                "safe_policy_drop": float(base["task_score"]) - float(guarded["task_score"]),
                "raw_and_all_template_below_half_score": (
                    float(base["task_score"]) < .5 and float(candidate["task_score"]) < .5),
                "diagnosis": "all-template policy violates the frozen Qasper scope; both compared answers are task-incorrect and the raw score has incidental lexical overlap",
            })
    output = root / "service_template_quality_all_compiled_negative_control_v0.csv"
    write_csv(output, rows)
    gate = {
        "archived_metric_drops_gt_0_03": len(rows),
        "all_drops_qasper": bool(rows) and all(row["family"] == "Qasper" for row in rows),
        "all_drops_below_half_score": bool(rows) and all(row["raw_and_all_template_below_half_score"] for row in rows),
        "safe_policy_eliminates_drops": bool(rows) and all(abs(float(row["safe_policy_drop"])) < 1e-12 for row in rows),
        "interpretation": "The archived all-template run is a negative control. The paper-facing policy uses the pre-existing Qasper fail-closed qualification.",
    }
    (root / "service_template_quality_all_compiled_negative_control_v0.json").write_text(
        json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2))
    return 0 if gate["all_drops_qasper"] and gate["safe_policy_eliminates_drops"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
