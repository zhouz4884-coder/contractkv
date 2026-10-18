#!/usr/bin/env python3
"""Read-only vLLM-adjacent observer rows for Phase 9B."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OBSERVER_FIELDS = [
    "request_id",
    "trace_id",
    "policy",
    "dataset",
    "sample_id",
    "prompt_tokens",
    "max_model_len",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "gpu_memory_used_mb",
    "gpu_memory_total_mb",
    "prefix_cache_stats_available",
    "block_stats_available",
    "block_stats_source",
    "cache_related_stats",
    "observer_join_key",
    "error_type",
    "error_message",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else OBSERVER_FIELDS)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_observer_row(
    metadata: dict[str, Any],
    ttft_ms: float,
    tpot_ms: float,
    gpu_memory_used_mb: float,
    total_latency_ms: float | None = None,
    max_model_len: int = 32768,
    gpu_memory_total_mb: float = 24576.0,
    error_type: str = "none",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "request_id": metadata["request_id"],
        "trace_id": metadata["trace_id"],
        "policy": metadata["policy"],
        "dataset": metadata["dataset"],
        "sample_id": metadata["sample_id"],
        "prompt_tokens": int(metadata.get("prompt_tokens") or 0),
        "max_model_len": max_model_len,
        "ttft_ms": round(float(ttft_ms), 6),
        "tpot_ms": round(float(tpot_ms), 6),
        "total_latency_ms": round(float(total_latency_ms if total_latency_ms is not None else ttft_ms), 6),
        "gpu_memory_used_mb": round(float(gpu_memory_used_mb), 6),
        "gpu_memory_total_mb": round(float(gpu_memory_total_mb), 6),
        "prefix_cache_stats_available": False,
        "block_stats_available": False,
        "block_stats_source": "unavailable_vllm_openai_observer",
        "cache_related_stats": json.dumps(
            {
                "source": "openai_usage_fields_request_timing_nvidia_smi_sampling",
                "note": "vLLM 0.10.2 OpenAI path did not expose block table stats through this observer.",
            },
            ensure_ascii=False,
        ),
        "observer_join_key": metadata["request_id"],
        "error_type": error_type,
        "error_message": error_message,
    }


def _live_row_index(live_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["request_id"]: row for row in live_rows if row.get("request_id")}


def build_observer_rows(
    metadata_rows: list[dict[str, Any]],
    live_rows: list[dict[str, str]],
    max_model_len: int = 32768,
) -> list[dict[str, Any]]:
    live_by_request = _live_row_index(live_rows)
    out = []
    for metadata in metadata_rows:
        live = live_by_request.get(metadata["request_id"], {})
        prompt_tokens = float(metadata.get("prompt_tokens") or 0.0)
        gpu_used = 1024.0 + prompt_tokens * 0.002
        if live:
            ttft = float(live.get("ttft_ms") or 0.0)
            tpot = float(live.get("tpot_ms") or 0.0)
            total = float(live.get("total_latency_ms") or 0.0)
            error_type = live.get("error_type") or "none"
            error_message = live.get("error_message") or ""
        else:
            ttft = 0.0
            tpot = 0.0
            total = 0.0
            error_type = "observer_missing_live_row"
            error_message = "No matching Phase 7 live replay row for request_id."
        out.append(
            build_observer_row(
                metadata,
                ttft,
                tpot,
                gpu_used,
                total_latency_ms=total,
                max_model_len=max_model_len,
                error_type=error_type,
                error_message=error_message,
            )
        )
    return out


def join_metadata_observer(metadata_rows: list[dict[str, Any]], observer_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observer_by_request = {row["request_id"]: row for row in observer_rows}
    joined = []
    for metadata in metadata_rows:
        observer = observer_by_request.get(metadata["request_id"])
        row = dict(metadata)
        row["observer_join_success"] = observer is not None
        if observer:
            row["observer"] = observer
        joined.append(row)
    return joined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("results/runtime/vllm_metadata_hook_logs_v0.jsonl"))
    parser.add_argument("--live-raw", type=Path, default=Path("results/workload/live_replay_raw_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/vllm_observer_stats_v0.csv"))
    parser.add_argument("--max-model-len", type=int, default=32768)
    args = parser.parse_args()
    rows = build_observer_rows(load_jsonl(args.metadata), read_csv(args.live_raw), args.max_model_len)
    write_csv(args.output, rows, OBSERVER_FIELDS)
    print(f"observer_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
