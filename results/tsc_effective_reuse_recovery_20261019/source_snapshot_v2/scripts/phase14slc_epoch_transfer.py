#!/usr/bin/env python3
"""Untouched multi-turn output-transfer experiment for Phase 14 SLC-B."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, compile_static_policy
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories
from scripts.phase12f_real_vllm_caposc_replay import _messages_for_case, _ordered_text, score_real_output


RAW_FIELDS = [
    "cell_id", "tool_slack_ms", "trajectory_id", "case_type", "turn_id",
    "raw_request_id", "caposc_request_id", "raw_success", "caposc_success",
    "raw_quality_sanity", "caposc_quality_sanity", "raw_output_hash",
    "caposc_output_hash", "exact_output_match", "certificate_issued",
    "shadow_runtime_ms", "shadow_hidden_by_slack", "claim_boundary",
]

SUMMARY_FIELDS = [
    "tool_slack_ms", "horizon_turns", "sessions", "certificate_issued",
    "certificate_issue_rate", "future_pairs", "future_exact_matches",
    "future_mismatch_rate", "future_match_wilson95_upper", "shadow_hidden_fraction",
    "mean_shadow_runtime_ms", "claim_boundary",
]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def normalized_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def wilson_upper(failures: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 1.0
    p = failures / total
    denominator = 1 + z * z / total
    return min(1.0, (p + z * z / (2 * total) + z * ((p * (1 - p) + z * z / (4 * total)) / total) ** .5) / denominator)


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = build_multiturn_trajectories(args.trajectories_per_type, args.turns)
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        sessions[str(case["trajectory_id"])].append(case)
    rows = []
    for session_id, turns in sorted(sessions.items()):
        raw_ledger, caposc_ledger = SegmentPrefixLedger(), SegmentPrefixLedger()
        certificate = False
        for case in sorted(turns, key=lambda row: int(row["turn_id"])):
            raw = compile_static_policy(case["segments"], "raw-order")
            caposc = cache_aware_posc_compile(case["segments"], caposc_ledger, session_id, int(case["turn_id"]), float(args.tool_slack_ms))
            raw_messages = _messages_for_case(case, _ordered_text(raw["topological_order"], case["segments"]))
            cap_messages = _messages_for_case(case, _ordered_text(caposc["topological_order"], case["segments"]))
            for messages in (raw_messages, cap_messages):
                messages[0]["content"] = f"[SLC_EPOCH:{args.cell_id}]\n" + messages[0]["content"]
            raw_result = send_chat_stream(args.base_url, args.model, raw_messages, args.max_tokens, args.timeout, f"{args.cell_id}-{session_id}-{case['turn_id']}-raw")
            cap_result = send_chat_stream(args.base_url, args.model, cap_messages, args.max_tokens, args.timeout, f"{args.cell_id}-{session_id}-{case['turn_id']}-caposc")
            raw_sanity, _ = score_real_output(raw_result.get("output_text", ""), case["expected_answer"], case["unsafe_answer"], raw.get("violated_edges", []))
            cap_sanity, _ = score_real_output(cap_result.get("output_text", ""), case["expected_answer"], case["unsafe_answer"], caposc.get("violated_edges", []))
            exact = bool(raw_result.get("success")) and bool(cap_result.get("success")) and normalized_hash(raw_result.get("output_text", "")) == normalized_hash(cap_result.get("output_text", ""))
            if int(case["turn_id"]) == 0:
                certificate = exact and raw_sanity and cap_sanity
            rows.append({
                "cell_id": args.cell_id, "tool_slack_ms": args.tool_slack_ms,
                "trajectory_id": session_id, "case_type": case["case_type"], "turn_id": case["turn_id"],
                "raw_request_id": raw_result.get("request_id", ""), "caposc_request_id": cap_result.get("request_id", ""),
                "raw_success": raw_result.get("success", False), "caposc_success": cap_result.get("success", False),
                "raw_quality_sanity": raw_sanity, "caposc_quality_sanity": cap_sanity,
                "raw_output_hash": normalized_hash(raw_result.get("output_text", "")),
                "caposc_output_hash": normalized_hash(cap_result.get("output_text", "")),
                "exact_output_match": exact, "certificate_issued": certificate,
                "shadow_runtime_ms": cap_result.get("total_latency_ms", 0.0),
                "shadow_hidden_by_slack": float(args.tool_slack_ms) >= float(cap_result.get("total_latency_ms", 0.0)),
                "claim_boundary": "Untouched synthetic multi-turn output-transfer replay. First-turn equality does not itself prove future-turn safety.",
            })
            raw_ledger.update(session_id, int(case["turn_id"]), case["segments"], raw["topological_order"], policy="raw-order")
            caposc_ledger.update(session_id, int(case["turn_id"]), case["segments"], caposc["topological_order"], policy="cache-aware-posc")
    return rows


def summarize(rows: list[dict[str, Any]], horizons: list[int]) -> list[dict[str, Any]]:
    output = []
    for slack in sorted({float(row["tool_slack_ms"]) for row in rows}):
        group = [row for row in rows if float(row["tool_slack_ms"]) == slack]
        certificates = {row["trajectory_id"]: _bool(row["certificate_issued"]) for row in group if int(row["turn_id"]) == 0}
        for horizon in horizons:
            future = [row for row in group if 0 < int(row["turn_id"]) <= horizon and certificates.get(row["trajectory_id"], False)]
            matches = sum(_bool(row["exact_output_match"]) for row in future)
            shadows = [row for row in group if int(row["turn_id"]) == 0]
            output.append({
                "tool_slack_ms": slack, "horizon_turns": horizon, "sessions": len(certificates),
                "certificate_issued": sum(certificates.values()),
                "certificate_issue_rate": sum(certificates.values()) / len(certificates) if certificates else 0.0,
                "future_pairs": len(future), "future_exact_matches": matches,
                "future_mismatch_rate": (len(future) - matches) / len(future) if future else 0.0,
                "future_match_wilson95_upper": wilson_upper(len(future) - matches, len(future)),
                "shadow_hidden_fraction": sum(_bool(row["shadow_hidden_by_slack"]) for row in shadows) / len(shadows) if shadows else 0.0,
                "mean_shadow_runtime_ms": statistics.mean(float(row["shadow_runtime_ms"]) for row in shadows) if shadows else 0.0,
                "claim_boundary": "Future exact-match transfer over an untouched synthetic trajectory split; no claim beyond tested horizon.",
            })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--tool-slack-ms", type=float, required=True)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--horizons", default="1,3,5")
    args = parser.parse_args()
    rows = run(args)
    write_csv(args.raw_output, rows, RAW_FIELDS)
    write_csv(args.summary_output, summarize(rows, [int(value) for value in args.horizons.split(",")]), SUMMARY_FIELDS)
    print(f"slc_epoch_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
