#!/usr/bin/env python3
"""Build Phase 10.5C tier0 policy table from stream probes and actuator events."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_recompute_policy_pressure_eval import RAW_FIELDS, aggregate_pressure_metrics, write_csv


POLICY_FILES = {
    "vllm-default": {
        "stream": "phase10_5c_default_stream_long_qwen3_8b.jsonl",
        "event": None,
    },
    "full-recompute": {
        "stream": "phase10_5c_full_recompute_stream_long_qwen3_8b.jsonl",
        "event": "phase10_5c_full_recompute_events_qwen3_8b.jsonl",
    },
    "greedy-rar-exact": {
        "stream": "phase10_5c_greedy_rar_exact_stream_long_qwen3_8b.jsonl",
        "event": "phase10_5c_greedy_rar_exact_events_qwen3_8b.jsonl",
    },
    "contractkv-rar-exact": {
        "stream": "phase10_5c_rar_exact_stream_long_qwen3_8b.jsonl",
        "event": "phase10_5c_rar_exact_events_qwen3_8b.jsonl",
    },
}


def load_first_jsonl(path: Path) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return json.loads(line)
    return {}


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def build_policy_row(
    policy: str,
    stream: dict[str, Any],
    event: dict[str, Any],
    model: str,
    slo_ttft_ms: float,
) -> dict[str, Any]:
    completed = bool(stream.get("success")) and str(stream.get("error_type", "none")) == "none"
    anchor_token_end = _int(event.get("anchor_token_end"))
    boundary_guard_tokens = _int(event.get("boundary_guard_tokens"))
    if event.get("event") == "contractkv_forced_recompute_preemption":
        full_recompute_tokens = _int(event.get("before_block_table_length")) * 16
        anchored_recompute_tokens = full_recompute_tokens
        blocks_freed = _int(event.get("free_gpu_blocks_delta"))
    elif event:
        blocks_freed = _int(event.get("suffix_blocks_freed") or event.get("free_gpu_blocks_delta"))
        full_recompute_tokens = (_int(event.get("prefix_blocks_retained")) + _int(event.get("suffix_blocks_freed"))) * _int(event.get("block_size", 16))
        anchored_recompute_tokens = max(0, full_recompute_tokens - anchor_token_end)
    else:
        blocks_freed = 0
        full_recompute_tokens = 0
        anchored_recompute_tokens = 0
    saved = max(0, full_recompute_tokens - anchored_recompute_tokens)
    ttft_ms = float(stream.get("ttft_ms") or 0.0)
    return {
        "policy": policy,
        "dataset": "phase10_5_long_probe",
        "trace_id": "phase10_5_long_context_probe",
        "model": model,
        "configured_max_model_len": 8192,
        "max_num_seqs": 2,
        "completed": completed,
        "slo_violation": ttft_ms > float(slo_ttft_ms) or not completed,
        "latency_ms": float(stream.get("total_latency_ms") or 0.0),
        "ttft_ms": ttft_ms,
        "tpot_ms": float(stream.get("tpot_ms") or 0.0),
        "blocks_freed": blocks_freed,
        "free_gpu_blocks_before": _int(event.get("before_free_gpu_blocks")),
        "free_gpu_blocks_after": _int(event.get("after_free_gpu_blocks")),
        "full_recompute_tokens": full_recompute_tokens,
        "anchored_recompute_tokens": anchored_recompute_tokens,
        "recompute_tokens_saved_vs_full": saved,
        "recompute_events": 1 if event else 0,
        "error_type": stream.get("error_type", "none"),
        "error_message": stream.get("error_message", ""),
        "boundary_guard_tokens": boundary_guard_tokens,
    }


def write_raw_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(RAW_FIELDS)
    for extra in ["recompute_tokens_saved_vs_full", "boundary_guard_tokens"]:
        if extra not in fields:
            fields.append(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("results/hard_systems"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_events_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_eval_v0.csv"))
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--slo-ttft-ms", type=float, default=200.0)
    parser.add_argument("--duration-sec", type=float, default=1.0)
    args = parser.parse_args()
    rows = []
    for policy, files in POLICY_FILES.items():
        stream = load_first_jsonl(args.input_dir / files["stream"])
        event = load_first_jsonl(args.input_dir / files["event"]) if files["event"] else {}
        rows.append(build_policy_row(policy, stream, event, args.model, args.slo_ttft_ms))
    write_raw_csv(args.raw_output, rows)
    write_csv(args.summary_output, aggregate_pressure_metrics(rows, args.duration_sec), [
        "policy",
        "attempted_requests",
        "completed_requests",
        "slo_compliant_requests",
        "capacity_failures",
        "completion_rate",
        "slo_compliant_req_per_sec",
        "mean_ttft_ms",
        "p95_ttft_ms",
        "mean_tpot_ms",
        "p95_tpot_ms",
        "total_blocks_freed",
        "mean_block_headroom_gain",
        "total_recompute_tokens_saved_vs_full",
        "completion_lift_vs_default",
        "capacity_failure_reduction",
        "slo_goodput_delta_vs_default",
    ])
    print(f"tier0_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
