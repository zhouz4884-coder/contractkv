#!/usr/bin/env python3
"""Join Phase 13C live rows with observed vLLM actuator events."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


RAW_FIELDS = [
    "policy", "concurrency", "dataset", "task", "sample_id", "request_id", "success", "capacity_failure",
    "ttft_ms", "tpot_ms", "total_latency_ms", "prompt_tokens", "rar_trigger_reason", "blocks_freed_planned",
    "observed_rar_event", "observed_free_block_delta", "observed_suffix_blocks_freed", "actuator_latency_ms",
    "event_joined", "claim_boundary",
]
SUMMARY_FIELDS = [
    "policy", "concurrency", "attempted_requests", "completed_requests", "capacity_failures", "completion_rate",
    "mean_ttft_ms", "p95_ttft_ms", "slo_compliant_requests", "slo_compliant_req_per_sec", "event_joined_rows",
    "positive_free_block_event_rows", "sum_observed_free_block_delta", "sum_observed_suffix_blocks_freed",
    "claim_boundary",
]


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def analyze(rows: list[dict[str, Any]], events: list[dict[str, Any]], slo_ms: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_request = {str(event.get("request_id", "")): event for event in events if event.get("request_id")}
    enriched = []
    for row in rows:
        event = by_request.get(str(row.get("request_id", "")), {})
        enriched.append({
            "policy": row.get("policy", ""), "concurrency": row.get("concurrency", ""), "dataset": row.get("dataset", ""),
            "task": row.get("task", ""), "sample_id": row.get("sample_id", ""), "request_id": row.get("request_id", ""),
            "success": row.get("success", False), "capacity_failure": row.get("capacity_failure", False),
            "ttft_ms": row.get("ttft_ms", 0.0), "tpot_ms": row.get("tpot_ms", 0.0), "total_latency_ms": row.get("total_latency_ms", 0.0),
            "prompt_tokens": row.get("prompt_tokens", ""), "rar_trigger_reason": row.get("rar_trigger_reason", ""),
            "blocks_freed_planned": row.get("blocks_freed_planned", 0), "observed_rar_event": bool(event),
            "observed_free_block_delta": event.get("free_gpu_blocks_delta", 0), "observed_suffix_blocks_freed": event.get("suffix_blocks_freed", 0),
            "actuator_latency_ms": event.get("actuator_latency_ms", 0.0), "event_joined": bool(event),
            "claim_boundary": "Observed vLLM event joined by request_id; event log is endpoint-global and not an isolated policy effect.",
        })
    groups = defaultdict(list)
    for row in enriched:
        groups[(str(row["policy"]), int(row["concurrency"]))].append(row)
    summaries = []
    for (policy, concurrency), group in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        good = [row for row in group if _bool(row["success"])]
        ttft = sorted(_float(row["ttft_ms"]) for row in good if _float(row["ttft_ms"]) > 0)
        wall = max(_float(row.get("batch_wall_time_sec")) for row in rows if str(row.get("policy")) == policy and int(row.get("concurrency")) == concurrency) if group else 0.0
        joined = [row for row in group if row["event_joined"]]
        positive = [row for row in joined if _float(row["observed_free_block_delta"]) > 0]
        summaries.append({
            "policy": policy, "concurrency": concurrency, "attempted_requests": len(group), "completed_requests": len(good),
            "capacity_failures": sum(_bool(row["capacity_failure"]) for row in group), "completion_rate": round(len(good) / len(group), 6) if group else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0, "p95_ttft_ms": round(ttft[min(len(ttft) - 1, int(len(ttft) * 0.95))], 6) if ttft else 0.0,
            "slo_compliant_requests": sum(_float(row["ttft_ms"]) <= slo_ms for row in good), "slo_compliant_req_per_sec": round(sum(_float(row["ttft_ms"]) <= slo_ms for row in good) / wall, 6) if wall else 0.0,
            "event_joined_rows": len(joined), "positive_free_block_event_rows": len(positive),
            "sum_observed_free_block_delta": sum(_float(row["observed_free_block_delta"]) for row in joined),
            "sum_observed_suffix_blocks_freed": sum(_float(row["observed_suffix_blocks_freed"]) for row in joined),
            "claim_boundary": "No capacity lift claim: endpoint-global actuator events are joined, but policy-isolated causal benefit is not established.",
        })
    return enriched, summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-input", type=Path, default=Path("results/end_to_end/phase13c_live_capacity_cliff_raw_v0.csv"))
    parser.add_argument("--event-input", type=Path, default=Path("results/hard_systems/phase13c_capacity_rar_events_v0.jsonl"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13c_live_capacity_cliff_enriched_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13c_live_capacity_cliff_enriched_summary_v0.csv"))
    parser.add_argument("--slo-ms", type=float, default=3000.0)
    args = parser.parse_args()
    enriched, summary = analyze(read_csv(args.raw_input), read_jsonl(args.event_input), args.slo_ms)
    write_csv(args.raw_output, enriched, RAW_FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"enriched_rows={len(enriched)} summary_rows={len(summary)}")
    return 0 if enriched else 1


if __name__ == "__main__":
    raise SystemExit(main())
