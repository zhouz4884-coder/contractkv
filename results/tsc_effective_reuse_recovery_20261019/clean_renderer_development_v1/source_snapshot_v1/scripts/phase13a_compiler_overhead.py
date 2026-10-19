#!/usr/bin/env python3
"""Phase 13A CAPOSC compiler overhead and rebase accounting."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase12e_cache_aware_posc import (
    SegmentPrefixLedger,
    cache_aware_posc_compile,
    estimate_lcp_tokens,
)
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories


OVERHEAD_RAW_FIELDS = [
    "iteration",
    "trajectory_id",
    "turn_id",
    "case_type",
    "compile_ms",
    "ledger_lookup_ms",
    "candidate_eval_ms",
    "candidate_count",
    "selected_policy",
    "layout_decision",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "rebase_triggered",
    "rebase_hidden_by_slack",
    "rebase_overhead_ms",
    "tool_slack_ms",
    "claim_boundary",
]

OVERHEAD_SUMMARY_FIELDS = [
    "num_compiles",
    "compile_ms_mean",
    "compile_ms_p50",
    "compile_ms_p95",
    "ledger_lookup_ms_mean",
    "ledger_lookup_ms_p95",
    "candidate_eval_ms_mean",
    "candidate_eval_ms_p95",
    "candidate_count_mean",
    "candidate_count_p95",
    "claim_boundary",
]

REBASE_SUMMARY_FIELDS = [
    "num_compiles",
    "rebase_triggered_count",
    "rebase_hidden_by_slack_count",
    "rebase_selected_fraction",
    "rebase_hidden_fraction",
    "rebase_overhead_ms_mean",
    "rebase_overhead_ms_p95",
    "selected_policy_counts",
    "claim_boundary",
]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_p95(values: list[float]) -> float:
    return round(percentile(values, 0.95), 6) if values else 0.0


def measure_compile_once(case: dict[str, Any], iteration: int, ledger: SegmentPrefixLedger | None = None) -> tuple[dict[str, Any], SegmentPrefixLedger]:
    ledger = ledger or SegmentPrefixLedger()
    session_id = str(case["trajectory_id"])
    segments = case["segments"]

    started = time.perf_counter()
    compiled = cache_aware_posc_compile(
        segments,
        ledger,
        session_id=session_id,
        turn_id=int(case["turn_id"]),
        tool_slack_ms=float(case.get("tool_slack_ms") or 0.0),
    )
    compile_ms = (time.perf_counter() - started) * 1000.0

    lookup_started = time.perf_counter()
    for candidate in compiled.get("candidates", []):
        estimate_lcp_tokens(candidate["topological_order"], segments, ledger, session_id=session_id)
    ledger_lookup_ms = (time.perf_counter() - lookup_started) * 1000.0
    candidate_eval_ms = max(0.0, compile_ms - ledger_lookup_ms)

    rebase_candidate = next((item for item in compiled.get("candidates", []) if item["policy"] == "cache-aware-posc-rebase"), {})
    rebase_triggered = bool(rebase_candidate.get("rebase_performed", False))
    tool_slack_ms = float(case.get("tool_slack_ms") or 0.0)
    rebase_overhead_ms = float(rebase_candidate.get("rebase_cost_ms") or 0.0)
    rebase_hidden_by_slack = rebase_triggered and tool_slack_ms >= rebase_overhead_ms

    row = {
        "iteration": iteration,
        "trajectory_id": session_id,
        "turn_id": int(case["turn_id"]),
        "case_type": case.get("case_type", ""),
        "compile_ms": round(compile_ms, 6),
        "ledger_lookup_ms": round(ledger_lookup_ms, 6),
        "candidate_eval_ms": round(candidate_eval_ms, 6),
        "candidate_count": len(compiled.get("candidates", [])),
        "selected_policy": compiled.get("selected_policy", ""),
        "layout_decision": compiled.get("layout_decision", ""),
        "estimated_lcp_tokens": compiled.get("estimated_lcp_tokens", 0),
        "estimated_new_prefill_tokens": compiled.get("estimated_new_prefill_tokens", 0),
        "rebase_triggered": rebase_triggered,
        "rebase_hidden_by_slack": rebase_hidden_by_slack,
        "rebase_overhead_ms": round(rebase_overhead_ms, 6),
        "tool_slack_ms": tool_slack_ms,
        "claim_boundary": "local compiler microbenchmark; Python timing includes measurement overhead.",
    }
    ledger.update(session_id, int(case["turn_id"]), segments, compiled["topological_order"], policy="cache-aware-posc")
    return {field: row.get(field, "") for field in OVERHEAD_RAW_FIELDS}, ledger


def summarize_overhead_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compile_ms = [_float(row.get("compile_ms")) for row in rows]
    ledger_ms = [_float(row.get("ledger_lookup_ms")) for row in rows]
    candidate_ms = [_float(row.get("candidate_eval_ms")) for row in rows]
    counts = [_float(row.get("candidate_count")) for row in rows]
    record = {
        "num_compiles": len(rows),
        "compile_ms_mean": round(statistics.mean(compile_ms), 6) if compile_ms else 0.0,
        "compile_ms_p50": round(percentile(compile_ms, 0.50), 6),
        "compile_ms_p95": _safe_p95(compile_ms),
        "ledger_lookup_ms_mean": round(statistics.mean(ledger_ms), 6) if ledger_ms else 0.0,
        "ledger_lookup_ms_p95": _safe_p95(ledger_ms),
        "candidate_eval_ms_mean": round(statistics.mean(candidate_ms), 6) if candidate_ms else 0.0,
        "candidate_eval_ms_p95": _safe_p95(candidate_ms),
        "candidate_count_mean": round(statistics.mean(counts), 6) if counts else 0.0,
        "candidate_count_p95": _safe_p95(counts),
        "claim_boundary": "compiler overhead measured locally without vLLM request execution.",
    }
    return [{field: record.get(field, "") for field in OVERHEAD_SUMMARY_FIELDS}]


def summarize_rebase_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    triggered = [row for row in rows if _bool(row.get("rebase_triggered"))]
    hidden = [row for row in triggered if _bool(row.get("rebase_hidden_by_slack"))]
    overhead = [_float(row.get("rebase_overhead_ms")) for row in triggered]
    selected_counts: dict[str, int] = {}
    for row in rows:
        selected = str(row.get("selected_policy", ""))
        selected_counts[selected] = selected_counts.get(selected, 0) + 1
    record = {
        "num_compiles": len(rows),
        "rebase_triggered_count": len(triggered),
        "rebase_hidden_by_slack_count": len(hidden),
        "rebase_selected_fraction": round(len(triggered) / len(rows), 6) if rows else 0.0,
        "rebase_hidden_fraction": round(len(hidden) / len(triggered), 6) if triggered else 0.0,
        "rebase_overhead_ms_mean": round(statistics.mean(overhead), 6) if overhead else 0.0,
        "rebase_overhead_ms_p95": _safe_p95(overhead),
        "selected_policy_counts": json.dumps(selected_counts, sort_keys=True),
        "claim_boundary": "rebase is a layout/cache-warmup accounting event, not a free primitive.",
    }
    return [{field: record.get(field, "") for field in REBASE_SUMMARY_FIELDS}]


def run_overhead_benchmark(cases: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered = sorted(cases, key=lambda item: (str(item["trajectory_id"]), int(item["turn_id"])))
    for iteration in range(repeats):
        ledger = SegmentPrefixLedger()
        for case in ordered:
            row, ledger = measure_compile_once(case, iteration=iteration, ledger=ledger)
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories", type=Path)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--repeats", type=int, default=1000)
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase13a_compiler_overhead_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase13a_compiler_overhead_summary_v0.csv"))
    parser.add_argument("--rebase-output", type=Path, default=Path("results/prefix_cache/phase13a_rebase_accounting_v0.csv"))
    args = parser.parse_args()

    cases = load_jsonl(args.trajectories) if args.trajectories else build_multiturn_trajectories(args.trajectories_per_type, args.turns)
    rows = run_overhead_benchmark(cases, args.repeats)
    write_csv(args.raw_output, rows, OVERHEAD_RAW_FIELDS)
    summary = summarize_overhead_rows(rows)
    write_csv(args.summary_output, summary, OVERHEAD_SUMMARY_FIELDS)
    rebase = summarize_rebase_rows(rows)
    write_csv(args.rebase_output, rebase, REBASE_SUMMARY_FIELDS)
    print(f"compile_rows={len(rows)} summary_rows={len(summary)} rebase_rows={len(rebase)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
