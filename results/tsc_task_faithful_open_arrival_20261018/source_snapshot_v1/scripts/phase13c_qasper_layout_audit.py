#!/usr/bin/env python3
"""Audit Qasper raw-order versus CAPOSC layout changes from Phase 13C."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase13b_fresh_policy_quality_replay import build_case, load_jsonl


FIELDS = [
    "sample_id", "raw_score", "caposc_score", "signed_quality_delta", "paired_outcome",
    "raw_order", "caposc_order", "first_changed_segment", "relative_order_edit_distance",
    "adjacency_preservation_ratio", "evidence_query_distance_raw_tokens",
    "evidence_query_distance_caposc_tokens", "evidence_query_distance_delta_tokens",
    "tool_obs_crosses_evidence", "raw_output", "caposc_output", "answer", "claim_boundary",
]


def _normalise(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).lower() for item in value]
    return [str(value).lower()]


def _evidence_ids(case: dict[str, Any]) -> list[str]:
    answers = [item for item in _normalise(case.get("answer", "")) if item]
    ids = []
    for segment in case["segments"]:
        text = str(segment.get("text", "")).lower()
        if any(answer in text for answer in answers):
            ids.append(str(segment["segment_id"]))
    return ids


def _distance(order: list[str], case: dict[str, Any], evidence_ids: list[str]) -> int:
    by_id = {str(item["segment_id"]): item for item in case["segments"]}
    query_id = next((str(item["segment_id"]) for item in case["segments"] if item.get("segment_type") == "USER_QUERY"), "")
    if not query_id or query_id not in order or not evidence_ids:
        return 0
    query_pos = order.index(query_id)
    candidates = []
    for evidence_id in evidence_ids:
        if evidence_id not in order:
            continue
        pos = order.index(evidence_id)
        if pos < query_pos:
            candidates.append(sum(int(by_id[sid].get("token_count") or 0) for sid in order[pos + 1:query_pos]))
    return min(candidates) if candidates else 0


def _first_changed(raw: list[str], caposc: list[str]) -> str:
    for left, right in zip(raw, caposc):
        if left != right:
            return f"{left}->{right}"
    return "none"


def _adjacency_ratio(raw: list[str], caposc: list[str]) -> float:
    if len(raw) < 2:
        return 1.0
    pairs = set(zip(raw, raw[1:]))
    preserved = sum(pair in set(zip(caposc, caposc[1:])) for pair in pairs)
    return round(preserved / len(pairs), 6)


def _edit_distance(raw: list[str], caposc: list[str]) -> int:
    # Levenshtein distance over segment identities, adequate for tiny DAGs.
    table = list(range(len(caposc) + 1))
    for i, left in enumerate(raw, start=1):
        next_row = [i]
        for j, right in enumerate(caposc, start=1):
            next_row.append(min(next_row[-1] + 1, table[j] + 1, table[j - 1] + (left != right)))
        table = next_row
    return table[-1]


def audit(rows: list[dict[str, Any]], samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sample = {str(sample["sample_id"]): sample for sample in samples if sample.get("task") == "qasper"}
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row.get("task") != "qasper" or row.get("policy") not in {"raw-order", "contractkv-caposc"}:
            continue
        grouped.setdefault(str(row["sample_id"]), {})[str(row["policy"])] = row
    output = []
    for sample_id, pair in sorted(grouped.items()):
        if "raw-order" not in pair or "contractkv-caposc" not in pair or sample_id not in by_sample:
            continue
        case = build_case(by_sample[sample_id], stable_word_limit=2600)
        raw_order = json.loads(pair["raw-order"]["topological_order"])
        caposc_order = json.loads(pair["contractkv-caposc"]["topological_order"])
        evidence = _evidence_ids(case)
        raw_score = float(pair["raw-order"]["score"])
        caposc_score = float(pair["contractkv-caposc"]["score"])
        delta = caposc_score - raw_score
        tool_id = next((str(item["segment_id"]) for item in case["segments"] if item.get("segment_type") == "TOOL_OBS"), "")
        crossed = bool(evidence and tool_id and raw_order.index(tool_id) < raw_order.index(evidence[0]) and caposc_order.index(tool_id) > caposc_order.index(evidence[0]))
        output.append({
            "sample_id": sample_id, "raw_score": raw_score, "caposc_score": caposc_score, "signed_quality_delta": round(delta, 6),
            "paired_outcome": "win" if delta > 1e-9 else "loss" if delta < -1e-9 else "tie",
            "raw_order": json.dumps(raw_order), "caposc_order": json.dumps(caposc_order),
            "first_changed_segment": _first_changed(raw_order, caposc_order),
            "relative_order_edit_distance": _edit_distance(raw_order, caposc_order),
            "adjacency_preservation_ratio": _adjacency_ratio(raw_order, caposc_order),
            "evidence_query_distance_raw_tokens": _distance(raw_order, case, evidence),
            "evidence_query_distance_caposc_tokens": _distance(caposc_order, case, evidence),
            "evidence_query_distance_delta_tokens": _distance(caposc_order, case, evidence) - _distance(raw_order, case, evidence),
            "tool_obs_crosses_evidence": crossed, "raw_output": pair["raw-order"].get("output_text", ""),
            "caposc_output": pair["contractkv-caposc"].get("output_text", ""), "answer": by_sample[sample_id].get("answer", ""),
            "claim_boundary": "Phase 13C Qasper layout audit; identifies correlations, not causal proof of a single risk feature.",
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("results/end_to_end/phase13c_quality_raw_v0.jsonl"))
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/end_to_end/phase13c_qasper_layout_audit_v0.csv"))
    args = parser.parse_args()
    rows = audit(load_jsonl(args.raw), load_jsonl(args.samples))
    write_csv(args.output, rows)
    print(f"qasper_audit_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
