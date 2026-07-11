#!/usr/bin/env python3
"""Combine Phase 16R node outputs and classify historical verifier misses."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def historical_false_safe(rows_path: Path) -> list[dict[str, Any]]:
    wanted = {("LongBench", "qasper", "58"), ("LongBench", "narrativeqa", "165")}
    if not rows_path.exists():
        return []
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    output = []
    for row in rows:
        key = (str(row.get("dataset")), str(row.get("task")), str(row.get("sample_id")))
        if key not in wanted or str(row.get("policy")) == "raw-order":
            continue
        top1 = float(row.get("token_path_match_rate", 0) or 0)
        margin = float(row.get("minimum_logit_margin", 0) or 0)
        stop_ok = str(row.get("eos_consistency", "")).lower() == "true"
        if top1 < 1.0:
            mechanism = "top1_path_mismatch"
        elif not stop_ok:
            mechanism = "stop_inconsistency"
        else:
            mechanism = "low_margin_false_safe_candidate"
        output.append({
            "dataset": key[0], "task": key[1], "sample_id": key[2],
            "candidate_id": row.get("candidate_id", ""),
            "quality_drop_vs_raw": row.get("quality_drop_vs_raw", ""),
            "token_path_match_rate": top1,
            "minimum_logit_margin": margin,
            "eos_consistency": stop_ok,
            "historical_certificate_issued": row.get("certificate_issued", ""),
            "mechanism_classification": mechanism,
            "claim_boundary": "Post-hoc classification of Phase 15 teacher-forced evidence; not a rerun under Phase 16R thresholds.",
        })
    return output


def repair_pstp_metrics(path: Path) -> None:
    if not path.exists():
        return
    rows = read_csv(path)
    for row in rows:
        prompt = int(row.get("candidate_prompt_tokens", 0) or 0)
        prefill = int(row.get("candidate_new_prefill_tokens", prompt) or prompt)
        cached = max(0, prompt - prefill)
        commit = int(row.get("commit_tokens", 0) or 0)
        block_size = int(row.get("block_size", 16) or 16)
        inherited = min(cached, block_size) if commit == 0 else 0
        row["candidate_cached_tokens"] = str(cached)
        row["inherited_common_tokens"] = str(inherited)
        row["dynamic_suffix_reused_tokens"] = str(max(0, cached - commit - inherited))
        row["stable_probe_reuse_fraction"] = str(round(min(cached, commit) / max(commit, 1), 6) if commit else 0.0)
    write_csv(path, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiescence", type=Path, nargs="+", default=[])
    parser.add_argument("--quiescence-output", type=Path, required=True)
    parser.add_argument("--historical-input", type=Path, required=True)
    parser.add_argument("--false-safe-output", type=Path, required=True)
    parser.add_argument("--pstp", type=Path)
    args = parser.parse_args()
    combined = []
    for path in args.quiescence:
        combined.extend(read_csv(path))
    write_csv(args.quiescence_output, combined)
    write_csv(args.false_safe_output, historical_false_safe(args.historical_input))
    if args.pstp:
        repair_pstp_metrics(args.pstp)


if __name__ == "__main__":
    main()
