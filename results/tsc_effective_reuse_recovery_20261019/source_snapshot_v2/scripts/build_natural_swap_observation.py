#!/usr/bin/env python3
"""Summarize natural vLLM swap/preemption observation events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "model",
    "server_config",
    "num_events",
    "num_requests_observed",
    "observed_swap_events",
    "observed_preemptions",
    "min_free_gpu_blocks",
    "max_used_gpu_blocks",
    "actual_behavior",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize_natural_observation(events: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    scheduler_events = [event for event in events if event.get("event") == "scheduler_output"]
    sequence_events = [event for event in events if event.get("event") == "sequence_group_state"]
    swap_events = 0
    preemptions = 0
    for event in scheduler_events:
        swap_events += len(event.get("blocks_to_swap_in") or []) + len(event.get("blocks_to_swap_out") or [])
        preemptions += int(event.get("num_preempted") or 0)
    free = [int(event.get("free_gpu_blocks") or 0) for event in sequence_events if "free_gpu_blocks" in event]
    used = [int(event.get("used_gpu_blocks") or 0) for event in sequence_events if "used_gpu_blocks" in event]
    if swap_events:
        behavior = "natural_swap_observed"
    elif preemptions:
        behavior = "preemption_or_recompute_without_swap"
    else:
        behavior = "no_swap_or_preemption_observed"
    return [
        {
            "model": config.get("model", ""),
            "server_config": json.dumps(config, ensure_ascii=False),
            "num_events": len(events),
            "num_requests_observed": len({event.get("request_id") for event in sequence_events if event.get("request_id")}),
            "observed_swap_events": swap_events,
            "observed_preemptions": preemptions,
            "min_free_gpu_blocks": min(free) if free else 0,
            "max_used_gpu_blocks": max(used) if used else 0,
            "actual_behavior": behavior,
        }
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("results/hard_systems/vllm_natural_swap_events_v0.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_natural_swap_observation_v0.csv"))
    parser.add_argument("--model", default="")
    parser.add_argument("--server-config", default="{}")
    args = parser.parse_args()
    config = json.loads(args.server_config)
    if args.model:
        config["model"] = args.model
    rows = summarize_natural_observation(load_jsonl(args.events), config)
    write_csv(args.output, rows)
    print(f"natural_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
