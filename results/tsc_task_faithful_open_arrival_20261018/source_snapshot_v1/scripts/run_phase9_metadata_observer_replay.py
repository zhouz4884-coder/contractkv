#!/usr/bin/env python3
"""Join Phase 9 metadata, observer, and orchestrator proxy records."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


FIELDS = [
    "request_id",
    "trace_id",
    "policy",
    "dataset",
    "sample_id",
    "metadata_success",
    "observer_join_success",
    "controller_overhead_ms",
    "observed_ttft_ms",
    "observed_tpot_ms",
    "residual_stall_ms",
    "quality_violation_rate",
    "slo_violation",
    "admission_rate",
    "admitted",
    "copy_strategy",
    "predicted_transfer_size_mb",
    "real_kv_cache_movement",
    "block_stats_available",
]

SUMMARY_FIELDS = [
    "policy",
    "num_requests",
    "metadata_success_rate",
    "observer_join_success_rate",
    "mean_controller_overhead_ms",
    "mean_observed_ttft_ms",
    "mean_observed_tpot_ms",
    "mean_residual_stall_ms",
    "quality_violation_rate",
    "slo_violation_rate",
    "admission_rate",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _admission_value(row: dict[str, Any]) -> float:
    if "admission_rate" in row:
        return float(row["admission_rate"])
    return 1.0 if _bool(row.get("admitted", False)) else 0.0


def build_replay_row(
    metadata: dict[str, Any],
    observer: dict[str, Any] | None,
    orchestrator: dict[str, Any] | None,
) -> dict[str, Any]:
    observer_join = observer is not None
    stall = float((orchestrator or {}).get("residual_stall_ms") or 0.0)
    observer_ttft = float((observer or {}).get("ttft_ms") or 0.0)
    observed_ttft = observer_ttft + stall
    slo_budget = float(metadata.get("slo_budget_ms") or 0.0)
    admitted = bool(metadata.get("admitted", False))
    quality_violation = float(metadata.get("estimated_risk") or 0.0) > float(metadata.get("risk_budget") or 0.0)
    return {
        "request_id": metadata["request_id"],
        "trace_id": metadata["trace_id"],
        "policy": metadata["policy"],
        "dataset": metadata["dataset"],
        "sample_id": metadata["sample_id"],
        "metadata_success": True,
        "observer_join_success": observer_join,
        "controller_overhead_ms": round(float(metadata.get("controller_overhead_ms") or 0.0), 6),
        "observed_ttft_ms": round(observed_ttft, 6),
        "observed_tpot_ms": round(float((observer or {}).get("tpot_ms") or 0.0), 6),
        "residual_stall_ms": round(stall, 6),
        "quality_violation_rate": 1.0 if quality_violation else 0.0,
        "slo_violation": observed_ttft > slo_budget if slo_budget > 0 else False,
        "admission_rate": 1.0 if admitted else 0.0,
        "admitted": admitted,
        "copy_strategy": (orchestrator or {}).get("copy_strategy", "missing"),
        "predicted_transfer_size_mb": int(float((orchestrator or {}).get("predicted_transfer_size_mb") or 0)),
        "real_kv_cache_movement": _bool((orchestrator or {}).get("real_kv_cache_movement", False)),
        "block_stats_available": _bool((observer or {}).get("block_stats_available", False)),
    }


def aggregate_phase9_replay(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["policy"], []).append(row)
    out = []
    for policy, group in sorted(groups.items()):
        out.append(
            {
                "policy": policy,
                "num_requests": len(group),
                "metadata_success_rate": round(sum(_bool(r["metadata_success"]) for r in group) / len(group), 6),
                "observer_join_success_rate": round(sum(_bool(r["observer_join_success"]) for r in group) / len(group), 6),
                "mean_controller_overhead_ms": round(statistics.mean(float(r["controller_overhead_ms"]) for r in group), 6),
                "mean_observed_ttft_ms": round(statistics.mean(float(r["observed_ttft_ms"]) for r in group), 6),
                "mean_observed_tpot_ms": round(statistics.mean(float(r["observed_tpot_ms"]) for r in group), 6),
                "mean_residual_stall_ms": round(statistics.mean(float(r["residual_stall_ms"]) for r in group), 6),
                "quality_violation_rate": round(statistics.mean(float(r["quality_violation_rate"]) for r in group), 6),
                "slo_violation_rate": round(sum(_bool(r["slo_violation"]) for r in group) / len(group), 6),
                "admission_rate": round(statistics.mean(_admission_value(r) for r in group), 6),
            }
        )
    return out


def build_phase9_replay_rows(
    metadata_rows: list[dict[str, Any]],
    observer_rows: list[dict[str, Any]],
    orchestrator_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observer_by_id = {row["request_id"]: row for row in observer_rows}
    orchestrator_by_id = {row["request_id"]: row for row in orchestrator_rows}
    return [build_replay_row(row, observer_by_id.get(row["request_id"]), orchestrator_by_id.get(row["request_id"])) for row in metadata_rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("results/runtime/vllm_metadata_hook_logs_v0.jsonl"))
    parser.add_argument("--observer", type=Path, default=Path("results/runtime/vllm_observer_stats_v0.csv"))
    parser.add_argument("--orchestrator", type=Path, default=Path("results/runtime/vllm_prefetch_orchestrator_proxy_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/phase9_metadata_observer_replay_v0.csv"))
    parser.add_argument("--summary", type=Path, default=Path("results/runtime/phase9_metadata_observer_replay_summary_v0.csv"))
    args = parser.parse_args()
    rows = build_phase9_replay_rows(load_jsonl(args.metadata), read_csv(args.observer), read_csv(args.orchestrator))
    write_csv(args.output, rows, FIELDS)
    write_csv(args.summary, aggregate_phase9_replay(rows), SUMMARY_FIELDS)
    print(f"phase9_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
