#!/usr/bin/env python3
"""Summarize Phase 10.5B anchored recompute POC events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "model",
    "anchored_recompute_success",
    "request_completed",
    "anchor_token_end",
    "recompute_start_token",
    "boundary_guard_tokens",
    "prefix_blocks_retained",
    "suffix_blocks_freed",
    "free_gpu_blocks_delta",
    "num_computed_tokens_after",
    "prefix_blocks_retained_exact",
    "suffix_blocks_freed_exact",
    "duplicate_block_id_detected",
    "block_table_consistency",
    "request_latency_ms",
    "response_bytes",
    "notes",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_anchor_probe(events: list[dict[str, Any]], requests: list[dict[str, Any]], model: str) -> dict[str, Any]:
    event = next((row for row in events if row.get("event") == "contractkv_anchor_recompute"), {})
    request_completed = any(bool(row.get("success")) for row in requests)
    response_bytes = max([int(row.get("response_bytes") or 0) for row in requests] or [0])
    request_latency_ms = max([float(row.get("latency_ms") or 0.0) for row in requests] or [0.0])
    anchor_token_end = int(event.get("anchor_token_end") or 0)
    recompute_start_token = int(event.get("recompute_start_token") or 0)
    boundary_guard_tokens = int(event.get("boundary_guard_tokens") or 0)
    prefix_blocks_retained = int(event.get("prefix_blocks_retained") or 0)
    suffix_blocks_freed = int(event.get("suffix_blocks_freed") or 0)
    free_gpu_blocks_delta = int(event.get("free_gpu_blocks_delta") or 0)
    num_computed_tokens_after = int(event.get("num_computed_tokens_after") or 0)
    prefix_exact = bool(event.get("prefix_blocks_retained_exact"))
    suffix_exact = bool(event.get("suffix_blocks_freed_exact"))
    duplicate = bool(event.get("duplicate_block_id_detected"))
    consistency = bool(event.get("block_table_consistency"))
    success = (
        prefix_exact
        and suffix_exact
        and free_gpu_blocks_delta >= suffix_blocks_freed > 0
        and num_computed_tokens_after == anchor_token_end > 0
        and request_completed
        and response_bytes > 0
        and not duplicate
        and consistency
    )
    return {
        "model": model,
        "anchored_recompute_success": success,
        "request_completed": request_completed,
        "anchor_token_end": anchor_token_end,
        "recompute_start_token": recompute_start_token,
        "boundary_guard_tokens": boundary_guard_tokens,
        "prefix_blocks_retained": prefix_blocks_retained,
        "suffix_blocks_freed": suffix_blocks_freed,
        "free_gpu_blocks_delta": free_gpu_blocks_delta,
        "num_computed_tokens_after": num_computed_tokens_after,
        "prefix_blocks_retained_exact": prefix_exact,
        "suffix_blocks_freed_exact": suffix_exact,
        "duplicate_block_id_detected": duplicate,
        "block_table_consistency": consistency,
        "request_latency_ms": round(request_latency_ms, 6),
        "response_bytes": response_bytes,
        "notes": "anchored_suffix_recompute_success" if success else "anchored_probe_invariant_failed",
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
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/anchored_recompute_poc_v0.csv"))
    args = parser.parse_args()
    row = summarize_anchor_probe(load_jsonl(args.events), load_jsonl(args.requests), args.model)
    write_csv(args.output, [row])
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0 if row["anchored_recompute_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
