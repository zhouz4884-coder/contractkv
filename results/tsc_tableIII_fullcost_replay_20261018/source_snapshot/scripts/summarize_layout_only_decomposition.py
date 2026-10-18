#!/usr/bin/env python3
"""Summarize same-runtime raw/layout-only/full-online ContractKV decomposition."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.summarize_submission_repeats import summarize_cell


FIELDS = [
    "model", "cell", "runtime", "prompt_layout", "online_verifier", "fresh_process_repeats",
    "mean_ttft_ms", "mean_p95_ttft_ms", "mean_tpot_ms", "mean_new_prefill_tokens",
    "mean_prefix_hit_tokens", "mean_wall_slo_goodput", "mean_task_score", "completion_rate",
    "optimized_session_coverage", "mean_unhidden_verifier_ms_per_request", "net_mean_ttft_ms", "claim_boundary",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)


def average(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def coverage(path: Path, policy: str) -> float:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    future = [row for row in rows if row.get("row_type") == "future"]
    sessions = {str(row.get("session_id")) for row in future}
    if policy == "raw-order":
        return 0.0
    if policy == "offline-frozen-safe-compiled":
        optimized = {str(row.get("session_id")) for row in future if row.get("offline_qualified") is True}
    else:
        optimized = {str(row.get("session_id")) for row in future if row.get("certificate_issued") is True}
    return len(optimized) / max(len(sessions), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-root", type=Path, required=True)
    parser.add_argument("--layout-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--slo-ms", type=float, default=1500)
    args = parser.parse_args()
    matrix = []
    comparisons = []
    for model in ("qwen", "mistral"):
        groups: dict[str, list[dict[str, Any]]] = {}
        for policy in ("raw-order", "contractkv-full"):
            groups[policy] = [summarize_cell(model, repeat, policy,
                args.submission_root / model / f"repeat{repeat}" / f"{policy}.jsonl", args.slo_ms)
                for repeat in (1, 2, 3)]
        groups["offline-frozen-safe-compiled"] = [summarize_cell(model, repeat, "offline-frozen-safe-compiled",
            args.layout_root / model / f"repeat{repeat}" / "offline-frozen-safe-compiled.jsonl", args.slo_ms)
            for repeat in (1, 2, 3)]
        cells = (
            ("raw-order", "D0", "raw-order", False, "Native vLLM APC raw order."),
            ("offline-frozen-safe-compiled", "D1", "offline-frozen-safe-compiled", False,
             "Same vLLM runtime and compiler layout, with no online certificate request or PSTP publication."),
            ("contractkv-full", "D2", "online-verified-compiled", True,
             "Full online ContractKV with scoped verifier and publication control."),
        )
        by_cell = {}
        for policy, cell, layout, verifier, boundary in cells:
            rows = groups[policy]
            paths = [
                (args.layout_root / model / f"repeat{repeat}" / "offline-frozen-safe-compiled.jsonl")
                if policy == "offline-frozen-safe-compiled" else
                (args.submission_root / model / f"repeat{repeat}" / f"{policy}.jsonl")
                for repeat in (1, 2, 3)
            ]
            record = {
                "model": model, "cell": cell, "runtime": "vLLM-0.10.2-APC",
                "prompt_layout": layout, "online_verifier": verifier, "fresh_process_repeats": len(rows),
                "mean_ttft_ms": average(rows, "mean_ttft_ms"), "mean_p95_ttft_ms": average(rows, "p95_ttft_ms"),
                "mean_tpot_ms": average(rows, "mean_tpot_ms"), "mean_new_prefill_tokens": average(rows, "mean_new_prefill_tokens"),
                "mean_prefix_hit_tokens": average(rows, "mean_prefix_hit_tokens"),
                "mean_wall_slo_goodput": average(rows, "slo_compliant_req_per_sec"),
                "mean_task_score": average(rows, "mean_task_score"), "completion_rate": average(rows, "completion_rate"),
                "optimized_session_coverage": statistics.fmean(coverage(path, policy) for path in paths),
                "mean_unhidden_verifier_ms_per_request": average(rows, "unhidden_verifier_ms_per_request"),
                "net_mean_ttft_ms": average(rows, "net_mean_ttft_ms"), "claim_boundary": boundary,
            }
            matrix.append(record); by_cell[cell] = record
        raw, layout, full = by_cell["D0"], by_cell["D1"], by_cell["D2"]
        comparisons.append({
            "model": model,
            "layout_only_mean_ttft_reduction_vs_raw": 1 - layout["mean_ttft_ms"] / raw["mean_ttft_ms"],
            "layout_only_mean_ttft_speedup_vs_raw": raw["mean_ttft_ms"] / layout["mean_ttft_ms"],
            "layout_only_new_prefill_reduction_vs_raw": 1 - layout["mean_new_prefill_tokens"] / raw["mean_new_prefill_tokens"],
            "full_serving_mean_ttft_reduction_vs_raw": 1 - full["mean_ttft_ms"] / raw["mean_ttft_ms"],
            "full_net_mean_ttft_reduction_vs_raw": 1 - full["net_mean_ttft_ms"] / raw["mean_ttft_ms"],
            "full_net_mean_ttft_speedup_vs_raw": raw["mean_ttft_ms"] / full["net_mean_ttft_ms"],
            "online_control_plane_net_cost_ms": full["net_mean_ttft_ms"] - layout["mean_ttft_ms"],
            "layout_only_task_score_delta_vs_raw": layout["mean_task_score"] - raw["mean_task_score"],
            "full_task_score_delta_vs_raw": full["mean_task_score"] - raw["mean_task_score"],
            "claim_boundary": "D0-D2 share the same vLLM runtime; D1 isolates layout consumption from online verification.",
        })
    write_csv(args.output, matrix)
    payload = {"status": "complete", "matrix": matrix, "comparisons": comparisons}
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
