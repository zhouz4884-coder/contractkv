#!/usr/bin/env python3
"""Build Phase 10.5C Tier1 repeat tables and SLO sweep summaries."""

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

from scripts.build_phase10_5c_tier0_eval import build_policy_row
from scripts.run_recompute_policy_pressure_eval import aggregate_pressure_metrics, write_csv


POLICY_FILES = {
    "vllm-default": {
        "stream": "phase10_5c2_default_repeat_qwen3_8b.jsonl",
        "event": None,
    },
    "full-recompute": {
        "stream": "phase10_5c2_full_recompute_repeat_qwen3_8b.jsonl",
        "event": "phase10_5c2_full_recompute_events_qwen3_8b.jsonl",
    },
    "greedy-rar-exact": {
        "stream": "phase10_5c2_greedy_rar_exact_repeat_qwen3_8b.jsonl",
        "event": "phase10_5c2_greedy_rar_exact_events_qwen3_8b.jsonl",
    },
    "contractkv-rar-exact": {
        "stream": "phase10_5c2_rar_exact_repeat_qwen3_8b.jsonl",
        "event": "phase10_5c2_rar_exact_events_qwen3_8b.jsonl",
    },
}


RAW_FIELDS = [
    "policy",
    "run_id",
    "dataset",
    "trace_id",
    "model",
    "configured_max_model_len",
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


SLO_SWEEP_FIELDS = [
    "slo_ttft_ms",
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
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_repeat_rows(
    policy: str,
    streams: list[dict[str, Any]],
    events: list[dict[str, Any]],
    model: str,
    slo_ttft_ms: float,
) -> list[dict[str, Any]]:
    rows = []
    for index, stream in enumerate(streams):
        event = events[index] if index < len(events) else {}
        row = build_policy_row(policy, stream, event, model, slo_ttft_ms)
        row["run_id"] = index
        rows.append(row)
    return rows


def compute_slo_sweep_rows(raw_rows: list[dict[str, Any]], slo_values: list[int], duration_sec: float) -> list[dict[str, Any]]:
    out = []
    for slo in slo_values:
        adjusted = []
        for row in raw_rows:
            copy = dict(row)
            completed = str(copy.get("completed", "")).lower() in {"1", "true", "yes"}
            ttft = float(copy.get("ttft_ms") or 0.0)
            copy["slo_violation"] = (not completed) or ttft > float(slo)
            adjusted.append(copy)
        for summary in aggregate_pressure_metrics(adjusted, duration_sec):
            item = {"slo_ttft_ms": slo}
            item.update(summary)
            out.append(item)
    return out


def write_raw_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in RAW_FIELDS} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("results/hard_systems"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_repeat_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_repeat_summary_v0.csv"))
    parser.add_argument("--slo-sweep-output", type=Path, default=Path("results/hard_systems/contractkv_recompute_policy_slo_sweep_v0.csv"))
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--slo-ttft-ms", type=float, default=2500.0)
    parser.add_argument("--slo-values", default="2000,2500,3000")
    parser.add_argument("--duration-sec", type=float, default=10.0)
    args = parser.parse_args()
    rows = []
    for policy, files in POLICY_FILES.items():
        streams = load_jsonl(args.input_dir / files["stream"])
        events = load_jsonl(args.input_dir / files["event"]) if files["event"] else []
        rows.extend(build_repeat_rows(policy, streams, events, args.model, args.slo_ttft_ms))
    write_raw_csv(args.raw_output, rows)
    write_csv(args.summary_output, aggregate_pressure_metrics(rows, args.duration_sec), [
        field for field in SLO_SWEEP_FIELDS if field != "slo_ttft_ms"
    ])
    slo_values = [int(item) for item in args.slo_values.split(",") if item.strip()]
    write_csv(args.slo_sweep_output, compute_slo_sweep_rows(rows, slo_values, args.duration_sec), SLO_SWEEP_FIELDS)
    print(f"repeat_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
