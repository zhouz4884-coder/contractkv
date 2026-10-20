#!/usr/bin/env python3
"""Summarize guarded vLLM V1 prefix-cache observations by request."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "request_id", "observation_events", "prompt_tokens", "prefix_lookup_tokens",
    "prefix_hit_tokens", "new_prefill_tokens", "reused_physical_blocks",
    "newly_allocated_blocks", "prefix_cache_evictions", "scheduler_wait_ms",
    "prefill_gpu_ms", "decode_gpu_ms", "metric_availability", "claim_boundary",
]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _maximum(values: list[Any]) -> int | None:
    usable = [int(value) for value in values if value not in (None, "")]
    return max(usable) if usable else None


def _first(values: list[Any]) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def summarize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_request: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event") != "prefix_cache_request_observation":
            continue
        request_id = str(event.get("request_id") or "unknown")
        by_request.setdefault(request_id, []).append(event)
    rows = []
    for request_id, group in sorted(by_request.items()):
        initial = [event for event in group if event.get("initial_prefill_observation")]
        seed = initial[0] if initial else group[0]
        new_prefill = sum(int(event.get("new_prefill_tokens_this_iteration") or 0) for event in group)
        unavailable = []
        if seed.get("prefix_cache_evictions") is None:
            unavailable.append("prefix_cache_evictions")
        if seed.get("prefill_gpu_ms") is None:
            unavailable.append("prefill_gpu_ms")
        if seed.get("decode_gpu_ms") is None:
            unavailable.append("decode_gpu_ms")
        rows.append({
            "request_id": request_id,
            "observation_events": len(group),
            "prompt_tokens": _maximum([event.get("prompt_tokens") for event in group]) or 0,
            "prefix_lookup_tokens": _first([event.get("prefix_lookup_tokens") for event in initial]),
            "prefix_hit_tokens": _first([event.get("prefix_hit_tokens") for event in initial]),
            "new_prefill_tokens": new_prefill,
            "reused_physical_blocks": _first([event.get("reused_physical_blocks") for event in initial]),
            "newly_allocated_blocks": _maximum([event.get("newly_allocated_blocks") for event in group]),
            "prefix_cache_evictions": _first([event.get("prefix_cache_evictions") for event in group]),
            "scheduler_wait_ms": _first([event.get("scheduler_wait_ms") for event in initial]),
            "prefill_gpu_ms": _first([event.get("prefill_gpu_ms") for event in group]),
            "decode_gpu_ms": _first([event.get("decode_gpu_ms") for event in group]),
            "metric_availability": "all_scheduler_observable" if not unavailable else "unavailable:" + ",".join(unavailable),
            "claim_boundary": "Read-only V1 scheduler probe. Reused/new blocks are scheduler-observable derivations; eviction and GPU timings are null unless a later worker/metrics probe exposes them.",
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows = summarize(load_events(args.events))
    write_csv(args.summary, rows)
    print(f"prefix_metric_summary_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
