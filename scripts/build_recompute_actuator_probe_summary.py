#!/usr/bin/env python3
"""Build a CSV summary for the Phase 10.4B recompute actuator probe."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "model",
    "forced_preemption_events",
    "request_completed",
    "free_gpu_blocks_delta",
    "before_free_gpu_blocks",
    "after_free_gpu_blocks",
    "preempt_latency_ms",
    "request_latency_ms",
    "response_bytes",
    "output_sanity",
    "active_recompute_probe_success",
    "notes",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_recompute_probe(
    events: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    actuator_events = [event for event in events if event.get("event") == "contractkv_forced_recompute_preemption"]
    request_completed = any(bool(row.get("success")) for row in requests)
    response_bytes = max([int(row.get("response_bytes") or 0) for row in requests] or [0])
    latency_ms = max([float(row.get("latency_ms") or 0.0) for row in requests] or [0.0])
    if actuator_events:
        first = actuator_events[0]
        delta = int(first.get("free_gpu_blocks_delta") or 0)
        before = int(first.get("before_free_gpu_blocks") or 0)
        after = int(first.get("after_free_gpu_blocks") or 0)
        preempt_latency = float(first.get("preempt_latency_ms") or 0.0)
    else:
        delta = 0
        before = 0
        after = 0
        preempt_latency = 0.0
    output_sanity = request_completed and response_bytes > 0
    success = bool(actuator_events) and request_completed and delta > 0 and output_sanity
    return {
        "model": model,
        "forced_preemption_events": len(actuator_events),
        "request_completed": request_completed,
        "free_gpu_blocks_delta": delta,
        "before_free_gpu_blocks": before,
        "after_free_gpu_blocks": after,
        "preempt_latency_ms": round(preempt_latency, 6),
        "request_latency_ms": round(latency_ms, 6),
        "response_bytes": response_bytes,
        "output_sanity": output_sanity,
        "active_recompute_probe_success": success,
        "notes": "sequence_level_forced_recompute_probe" if success else "probe_incomplete_or_no_block_delta",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_recompute_actuator_probe_v0.csv"))
    args = parser.parse_args()
    row = summarize_recompute_probe(load_jsonl(args.events), load_jsonl(args.requests), args.model)
    write_csv(args.output, [row])
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0 if row["active_recompute_probe_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
