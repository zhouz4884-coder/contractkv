#!/usr/bin/env python3
"""Summarize ContractKV vLLM runtime probe JSONL events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = [
    "request_id",
    "num_sequence_events",
    "num_scheduler_events",
    "seq_ids",
    "prompt_token_count",
    "block_size",
    "logical_block_table_length",
    "num_physical_block_ids",
    "has_block_table",
    "has_block_counters",
    "saw_swap_in_out_fields",
    "free_gpu_blocks",
    "used_gpu_blocks",
    "free_cpu_blocks",
    "swapped_cpu_blocks",
    "probe_join_success",
    "phase10_3b_gate",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _request_id(event: dict[str, Any]) -> str:
    return str(event.get("request_id") or event.get("group_id") or "unknown")


def summarize_probe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        groups.setdefault(_request_id(event), []).append(event)
    rows = []
    for request_id, group in sorted(groups.items()):
        sequence_events = [event for event in group if event.get("event") == "sequence_group_state"]
        scheduler_events = [event for event in group if event.get("event") == "scheduler_output"]
        sequence = sequence_events[-1] if sequence_events else {}
        scheduler = scheduler_events[-1] if scheduler_events else {}
        physical = sequence.get("physical_block_ids") or []
        has_block_table = bool(sequence.get("logical_block_table_length", 0)) or bool(physical)
        has_counters = any(k in sequence for k in ("free_gpu_blocks", "used_gpu_blocks", "free_cpu_blocks", "swapped_cpu_blocks"))
        saw_swap = "blocks_to_swap_in" in scheduler or "blocks_to_swap_out" in scheduler
        join_success = bool(sequence_events) and bool(scheduler_events)
        rows.append(
            {
                "request_id": request_id,
                "num_sequence_events": len(sequence_events),
                "num_scheduler_events": len(scheduler_events),
                "seq_ids": json.dumps(sequence.get("seq_ids", [])),
                "prompt_token_count": int(sequence.get("prompt_token_count") or 0),
                "block_size": int(sequence.get("block_size") or 0),
                "logical_block_table_length": int(sequence.get("logical_block_table_length") or 0),
                "num_physical_block_ids": len(physical),
                "has_block_table": has_block_table,
                "has_block_counters": has_counters,
                "saw_swap_in_out_fields": saw_swap,
                "free_gpu_blocks": int(sequence.get("free_gpu_blocks") or 0),
                "used_gpu_blocks": int(sequence.get("used_gpu_blocks") or 0),
                "free_cpu_blocks": int(sequence.get("free_cpu_blocks") or 0),
                "swapped_cpu_blocks": int(sequence.get("swapped_cpu_blocks") or 0),
                "probe_join_success": join_success,
                "phase10_3b_gate": "open" if join_success and has_block_table and has_counters else "closed",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("results/hard_systems/vllm_runtime_probe_events_v0.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("results/hard_systems/vllm_runtime_probe_summary_v0.csv"))
    args = parser.parse_args()
    rows = summarize_probe_events(load_jsonl(args.events))
    write_csv(args.summary, rows)
    print(f"probe_summary_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
