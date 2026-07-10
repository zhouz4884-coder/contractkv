#!/usr/bin/env python3
"""Run Phase 14R fresh-process prefix-cache isolation replications."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


RAW_FIELDS = [
    "replicate_id", "run_order", "policy", "runtime_policy", "request_id",
    "trajectory_id", "turn_id", "case_type", "success", "quality_sanity",
    "real_ttft_ms", "real_tpot_ms", "real_latency_ms", "prompt_tokens",
    "prefix_hit_tokens", "observed_new_prefill_tokens", "join_success",
    "server_log", "metrics_log", "claim_boundary",
]

SUMMARY_FIELDS = [
    "policy", "cells", "requests", "completion_rate", "quality_sanity_rate",
    "join_success_rate", "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms",
    "mean_observed_new_prefill_tokens", "ttft_reduction_vs_raw_pct",
    "p95_ttft_reduction_vs_raw_pct", "new_prefill_reduction_vs_raw_pct",
    "direction_consistent_replicates", "claim_boundary",
]


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def join_cell(
    plan_row: dict[str, str],
    runtime_policy: str,
    live_rows: list[dict[str, Any]],
    metric_events: list[dict[str, Any]],
    server_log: Path,
    metrics_log: Path,
) -> list[dict[str, Any]]:
    initial = {
        str(row.get("request_id", "")): row
        for row in metric_events
        if row.get("initial_prefill_observation") is True
    }
    output = []
    for live in live_rows:
        metric = initial.get(str(live.get("request_id", "")), {})
        output.append(
            {
                "replicate_id": plan_row["replicate_id"],
                "run_order": plan_row["run_order"],
                "policy": plan_row["policy"],
                "runtime_policy": runtime_policy,
                "request_id": live.get("request_id", ""),
                "trajectory_id": live.get("trajectory_id", ""),
                "turn_id": live.get("turn_id", ""),
                "case_type": live.get("case_type", ""),
                "success": live.get("success", False),
                "quality_sanity": live.get("quality_sanity", False),
                "real_ttft_ms": live.get("real_ttft_ms", 0),
                "real_tpot_ms": live.get("real_tpot_ms", 0),
                "real_latency_ms": live.get("real_latency_ms", 0),
                "prompt_tokens": metric.get("prompt_tokens", ""),
                "prefix_hit_tokens": metric.get("prefix_hit_tokens", ""),
                "observed_new_prefill_tokens": metric.get("new_prefill_tokens_this_iteration", ""),
                "join_success": bool(metric),
                "server_log": str(server_log),
                "metrics_log": str(metrics_log),
                "claim_boundary": "Fresh vLLM process and empty prefix cache per cell; read-only scheduler prefix metrics.",
            }
        )
    return output


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    replicate_means: dict[tuple[str, str], float] = {}
    for row in rows:
        groups[str(row["policy"])].append(row)
    for (policy, replicate), group in _group(rows, "policy", "replicate_id").items():
        replicate_means[(policy, replicate)] = statistics.mean(_float(row["real_ttft_ms"]) for row in group)
    raw = groups.get("raw-order", [])
    raw_ttft = [_float(row["real_ttft_ms"]) for row in raw if _bool(row["success"])]
    raw_new = [_float(row["observed_new_prefill_tokens"]) for row in raw if row.get("observed_new_prefill_tokens") != ""]
    raw_mean = statistics.mean(raw_ttft) if raw_ttft else 0.0
    raw_p95 = _percentile(raw_ttft, 0.95)
    raw_new_mean = statistics.mean(raw_new) if raw_new else 0.0
    output = []
    for policy, group in sorted(groups.items()):
        success = [row for row in group if _bool(row["success"])]
        ttft = [_float(row["real_ttft_ms"]) for row in success]
        tpot = [_float(row["real_tpot_ms"]) for row in success]
        new_prefill = [_float(row["observed_new_prefill_tokens"]) for row in group if row.get("observed_new_prefill_tokens") != ""]
        mean_ttft = statistics.mean(ttft) if ttft else 0.0
        p95_ttft = _percentile(ttft, 0.95)
        mean_new = statistics.mean(new_prefill) if new_prefill else 0.0
        replicates = sorted({str(row["replicate_id"]) for row in group})
        consistent = sum(
            replicate_means.get((policy, replicate), float("inf")) < replicate_means.get(("raw-order", replicate), float("-inf"))
            for replicate in replicates
        ) if policy != "raw-order" else len(replicates)
        output.append(
            {
                "policy": policy,
                "cells": len({(row["replicate_id"], row["run_order"]) for row in group}),
                "requests": len(group),
                "completion_rate": round(len(success) / max(1, len(group)), 6),
                "quality_sanity_rate": round(sum(_bool(row["quality_sanity"]) for row in group) / max(1, len(group)), 6),
                "join_success_rate": round(sum(_bool(row["join_success"]) for row in group) / max(1, len(group)), 6),
                "mean_ttft_ms": round(mean_ttft, 6),
                "p95_ttft_ms": round(p95_ttft, 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
                "mean_observed_new_prefill_tokens": round(mean_new, 6),
                "ttft_reduction_vs_raw_pct": round((raw_mean - mean_ttft) / raw_mean * 100, 6) if policy != "raw-order" and raw_mean else 0.0,
                "p95_ttft_reduction_vs_raw_pct": round((raw_p95 - p95_ttft) / raw_p95 * 100, 6) if policy != "raw-order" and raw_p95 else 0.0,
                "new_prefill_reduction_vs_raw_pct": round((raw_new_mean - mean_new) / raw_new_mean * 100, 6) if policy != "raw-order" and raw_new_mean else 0.0,
                "direction_consistent_replicates": f"{consistent}/{len(replicates)}",
                "claim_boundary": "Real isolated vLLM prefix-cache replication; no worker-level kernel timing claim.",
            }
        )
    return output


def _group(rows: list[dict[str, Any]], *fields: str) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    output: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        output[tuple(str(row[field]) for field in fields)].append(row)
    return output


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    plan = list(csv.DictReader(args.plan.open("r", encoding="utf-8", newline="")))
    output: list[dict[str, Any]] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy_map = {"raw-order": "raw-order", "static-posc": "posc", "cache-aware-posc": "cache-aware-posc"}
    for plan_row in sorted(plan, key=lambda row: (int(row["replicate_id"]), int(row["run_order"]))):
        cell = f"r{plan_row['replicate_id']}_o{plan_row['run_order']}_{plan_row['policy']}"
        runtime_policy = policy_map[plan_row["policy"]]
        server_log = args.output_dir / f"{cell}_server.log"
        pid_path = args.output_dir / f"{cell}.pid"
        metrics_log = args.output_dir / f"{cell}_metrics.jsonl"
        live_path = args.output_dir / f"{cell}_live.jsonl"
        cell_summary = args.output_dir / f"{cell}_summary.csv"
        cell_corr = args.output_dir / f"{cell}_correlation.csv"
        for path in (metrics_log, live_path, cell_summary, cell_corr, pid_path):
            path.unlink(missing_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "CONTRACTKV_PREFIX_METRICS": "1",
                "CONTRACTKV_PREFIX_METRICS_LOG": str(metrics_log),
                "EXTRA_VLLM_ARGS": "--enable-prefix-caching",
            }
        )
        start = [
            "bash", "scripts/run_vllm_server.sh", "--phase", "phase14r-prefix-isolation",
            "--model-path", args.model_path, "--served-model-name", args.model,
            "--port", str(args.port), "--gpu-ids", args.gpu_ids,
            "--tensor-parallel-size", "1", "--dtype", "float16",
            "--max-model-len", str(args.max_model_len), "--max-num-seqs", str(args.max_num_seqs),
            "--gpu-memory-utilization", str(args.gpu_memory_utilization),
            "--log-path", str(server_log), "--pid-path", str(pid_path),
        ]
        try:
            subprocess.run(start, check=True, env=env, timeout=args.startup_timeout)
            replay = [
                sys.executable, "scripts/phase12f_real_vllm_caposc_replay.py",
                "--base-url", f"http://127.0.0.1:{args.port}/v1", "--model", args.model,
                "--policies", runtime_policy, "--trajectories-per-type", str(args.trajectories_per_type),
                "--turns", str(args.turns), "--max-tokens", str(args.max_tokens), "--quiet",
                "--raw-output", str(live_path), "--summary-output", str(cell_summary),
                "--correlation-output", str(cell_corr),
            ]
            subprocess.run(replay, check=True, timeout=args.cell_timeout)
            output.extend(join_cell(plan_row, runtime_policy, _load_jsonl(live_path), _load_jsonl(metrics_log), server_log, metrics_log))
            _write_csv(args.raw_output, output, RAW_FIELDS)
            _write_csv(args.summary_output, summarize(output), SUMMARY_FIELDS)
        finally:
            subprocess.run(["bash", "scripts/stop_vllm_server.sh", "--pid-path", str(pid_path), "--port", str(args.port)], check=False, timeout=90)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--gpu-ids", default="1")
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--max-num-seqs", type=int, default=8)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.78)
    parser.add_argument("--trajectories-per-type", type=int, default=1)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=24)
    parser.add_argument("--startup-timeout", type=float, default=480)
    parser.add_argument("--cell-timeout", type=float, default=900)
    parser.add_argument("--output-dir", type=Path, default=Path("results/prefix_cache/phase14r_isolation_cells"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase14r_prefix_isolation_raw_v1.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase14r_prefix_isolation_summary_v1.csv"))
    args = parser.parse_args()
    rows = run(args)
    print(f"prefix_isolation_rows={len(rows)} cells={len(set((row['replicate_id'], row['run_order']) for row in rows))}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
