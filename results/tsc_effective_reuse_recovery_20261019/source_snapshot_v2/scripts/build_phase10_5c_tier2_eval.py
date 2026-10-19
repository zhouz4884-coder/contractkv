#!/usr/bin/env python3
"""Aggregate Phase 10.5C Tier2 concurrent pressure runs."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_recompute_policy_pressure_eval import aggregate_pressure_metrics, write_csv


POLICIES = ["vllm-default", "full-recompute", "greedy-rar-exact", "contractkv-rar-exact"]
CONCURRENCY_LEVELS = [2, 4, 6]

RAW_FIELDS = [
    "policy",
    "concurrent_requests",
    "run_id",
    "request_id",
    "model",
    "max_num_seqs",
    "completed",
    "slo_violation",
    "latency_ms",
    "ttft_ms",
    "tpot_ms",
    "blocks_freed",
    "free_gpu_blocks_before",
    "free_gpu_blocks_after",
    "full_recompute_tokens",
    "anchored_recompute_tokens",
    "recompute_tokens_saved_vs_full",
    "recompute_events",
    "error_type",
    "error_message",
]

SUMMARY_FIELDS = [
    "policy",
    "concurrent_requests",
    "attempted_requests",
    "completed_requests",
    "success_rate",
    "slo_compliant_requests",
    "capacity_failures",
    "slo_compliant_req_per_sec",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "mean_total_latency_ms",
    "total_blocks_freed",
    "mean_block_headroom_gain",
    "total_recompute_tokens_saved_vs_full",
    "completion_lift_vs_default",
    "capacity_failure_reduction",
    "slo_goodput_delta_vs_default",
]

SLO_SWEEP_FIELDS = ["slo_ttft_ms", *SUMMARY_FIELDS]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def event_metrics(event: dict[str, Any]) -> dict[str, int]:
    if not event:
        return {
            "blocks_freed": 0,
            "free_gpu_blocks_before": 0,
            "free_gpu_blocks_after": 0,
            "full_recompute_tokens": 0,
            "anchored_recompute_tokens": 0,
            "recompute_tokens_saved_vs_full": 0,
            "recompute_events": 0,
        }
    if event.get("event") == "contractkv_forced_recompute_preemption":
        full = _int(event.get("before_block_table_length")) * 16
        anchored = full
        blocks = _int(event.get("free_gpu_blocks_delta"))
    else:
        block_size = _int(event.get("block_size", 16)) or 16
        prefix = _int(event.get("prefix_blocks_retained"))
        suffix = _int(event.get("suffix_blocks_freed"))
        full = (prefix + suffix) * block_size
        anchored = max(0, full - _int(event.get("anchor_token_end")))
        blocks = suffix or _int(event.get("free_gpu_blocks_delta"))
    return {
        "blocks_freed": blocks,
        "free_gpu_blocks_before": _int(event.get("before_free_gpu_blocks")),
        "free_gpu_blocks_after": _int(event.get("after_free_gpu_blocks")),
        "full_recompute_tokens": full,
        "anchored_recompute_tokens": anchored,
        "recompute_tokens_saved_vs_full": max(0, full - anchored),
        "recompute_events": 1,
    }


def build_tier2_rows(
    policy: str,
    concurrent_requests: int,
    streams: list[dict[str, Any]],
    events: list[dict[str, Any]],
    model: str,
    max_num_seqs: int,
    slo_ttft_ms: float,
) -> list[dict[str, Any]]:
    events_by_request_id = {str(event.get("request_id", "")): event for event in events if event.get("request_id")}
    rows = []
    for index, stream in enumerate(streams):
        event = events_by_request_id.get(str(stream.get("request_id", "")), events[index] if index < len(events) else {})
        metrics = event_metrics(event)
        completed = bool(stream.get("success")) and str(stream.get("error_type", "none")) == "none"
        ttft = _float(stream.get("ttft_ms"))
        rows.append({
            "policy": policy,
            "concurrent_requests": concurrent_requests,
            "run_id": index,
            "request_id": stream.get("request_id", ""),
            "model": model,
            "max_num_seqs": max_num_seqs,
            "completed": completed,
            "slo_violation": (not completed) or ttft > slo_ttft_ms,
            "latency_ms": _float(stream.get("total_latency_ms")),
            "ttft_ms": ttft,
            "tpot_ms": _float(stream.get("tpot_ms")),
            "error_type": stream.get("error_type", "none"),
            "error_message": stream.get("error_message", ""),
            **metrics,
        })
    return rows


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"1", "true", "yes"}


def aggregate_tier2_rows(
    rows: list[dict[str, Any]],
    duration_sec_by_key: dict[tuple[str, int], float] | None = None,
) -> list[dict[str, Any]]:
    duration_sec_by_key = duration_sec_by_key or {}
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((_int(row.get("concurrent_requests")), str(row.get("policy"))), []).append(row)

    out = []
    defaults: dict[int, dict[str, Any]] = {}
    for (concurrency, policy), group in sorted(grouped.items()):
        duration = duration_sec_by_key.get((policy, concurrency))
        if duration is None:
            duration = max((_float(row.get("latency_ms")) for row in group), default=0.0) / 1000.0
        summary = aggregate_pressure_metrics(group, duration_sec=duration)
        item = summary[0]
        completed = _int(item["completed_requests"])
        attempted = _int(item["attempted_requests"])
        item["concurrent_requests"] = concurrency
        item["success_rate"] = round(completed / attempted, 6) if attempted else 0.0
        item["mean_total_latency_ms"] = round(statistics.mean([_float(row.get("latency_ms")) for row in group]), 6) if group else 0.0
        if policy == "vllm-default":
            defaults[concurrency] = item
        out.append(item)

    for item in out:
        default = defaults.get(_int(item["concurrent_requests"]))
        if default:
            item["completion_lift_vs_default"] = _int(item["completed_requests"]) - _int(default["completed_requests"])
            item["capacity_failure_reduction"] = _int(default["capacity_failures"]) - _int(item["capacity_failures"])
            item["slo_goodput_delta_vs_default"] = round(_float(item["slo_compliant_req_per_sec"]) - _float(default["slo_compliant_req_per_sec"]), 6)
    return [{field: row.get(field, "") for field in SUMMARY_FIELDS} for row in out]


def build_slo_sweep_rows(
    input_dir: Path,
    model: str,
    max_num_seqs: int,
    slo_buckets_ms: list[float],
) -> list[dict[str, Any]]:
    out = []
    for slo in slo_buckets_ms:
        rows = build_all_rows(input_dir, model, max_num_seqs, slo)
        for summary in aggregate_tier2_rows(rows):
            item = {"slo_ttft_ms": int(slo) if float(slo).is_integer() else slo}
            item.update(summary)
            out.append({field: item.get(field, "") for field in SLO_SWEEP_FIELDS})
    return out


def build_all_rows(input_dir: Path, model: str, max_num_seqs: int, slo_ttft_ms: float) -> list[dict[str, Any]]:
    rows = []
    for concurrency in CONCURRENCY_LEVELS:
        for policy in POLICIES:
            stem = f"phase10_5c3_{policy.replace('-', '_')}_c{concurrency}_qwen3_8b"
            stream = load_jsonl(input_dir / f"{stem}.jsonl")
            events = load_jsonl(input_dir / f"{stem}_events.jsonl")
            rows.extend(build_tier2_rows(policy, concurrency, stream, events, model, max_num_seqs, slo_ttft_ms))
    return rows


def write_raw_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in RAW_FIELDS} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("results/hard_systems"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_tier2_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_tier2_summary_v0.csv"))
    parser.add_argument("--slo-sweep-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_tier3_slo_sweep_v0.csv"))
    parser.add_argument("--slo-buckets-ms", default="2000,2500,3000")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--max-num-seqs", type=int, default=2)
    parser.add_argument("--slo-ttft-ms", type=float, default=2500.0)
    args = parser.parse_args()
    rows = build_all_rows(args.input_dir, args.model, args.max_num_seqs, args.slo_ttft_ms)
    write_raw_csv(args.raw_output, rows)
    write_csv(args.summary_output, aggregate_tier2_rows(rows), SUMMARY_FIELDS)
    slo_buckets = [float(item.strip()) for item in args.slo_buckets_ms.split(",") if item.strip()]
    write_csv(args.slo_sweep_output, build_slo_sweep_rows(args.input_dir, args.model, args.max_num_seqs, slo_buckets), SLO_SWEEP_FIELDS)
    print(f"tier2_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
