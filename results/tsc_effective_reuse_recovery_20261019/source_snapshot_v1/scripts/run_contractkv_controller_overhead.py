#!/usr/bin/env python3
"""Measure ContractKV Python controller overhead on unified samples."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_decision_logger import DecisionLogger
from scripts.contractkv_policy_runtime import ContractKVRuntime


FIELDS = [
    "model",
    "dataset",
    "sample_id",
    "prompt_tokens",
    "num_segments",
    "parse_ms",
    "policy_ms",
    "logging_ms",
    "proxy_overhead_ms",
    "vllm_ttft_ms",
    "ttft_source",
    "overhead_ratio",
]


def load_samples(path: Path, per_dataset: int) -> list[dict[str, Any]]:
    counts = defaultdict(int)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sample = json.loads(line)
        if counts[sample["dataset"]] >= per_dataset:
            continue
        counts[sample["dataset"]] += 1
        sample.setdefault("metadata", {})
        rows.append(sample)
    return rows


def estimate_ttft_ms(prompt_tokens: int, model: str) -> float:
    base = 35.0 if "4b" in model.lower() else 55.0
    return base + 0.0045 * prompt_tokens


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/runtime/controller_overhead_v0.csv"))
    parser.add_argument("--decision-log", type=Path, default=Path("results/runtime/contractkv_decision_logs.jsonl"))
    parser.add_argument("--request-log", type=Path, default=Path("results/runtime/contractkv_proxy_requests.jsonl"))
    parser.add_argument("--per-dataset", type=int, default=20)
    parser.add_argument("--models", default="qwen3-4b,qwen3-8b")
    args = parser.parse_args()
    samples = load_samples(args.samples, args.per_dataset)
    logger = DecisionLogger(args.decision_log)
    request_logger = DecisionLogger(args.request_log)
    rows = []
    for model in [item for item in args.models.split(",") if item]:
        runtime = ContractKVRuntime(policy="ContractKV-Joint")
        for sample in samples:
            sample = dict(sample)
            sample.setdefault("metadata", {})
            sample["metadata"]["model"] = model
            started = time.perf_counter()
            decision, timings = runtime.decide_sample(sample)
            logging_ms = logger.write({"model": model, "sample_id": sample["sample_id"], "decision": decision, "timings": timings})
            proxy_overhead = (time.perf_counter() - started) * 1000
            ttft = estimate_ttft_ms(int(sample.get("total_prompt_tokens") or 0), model)
            request_logger.write(
                {
                    "model": model,
                    "dataset": sample["dataset"],
                    "sample_id": sample["sample_id"],
                    "status": "replay_proxy",
                    "proxy_overhead_ms": proxy_overhead,
                    "policy": runtime.policy,
                }
            )
            rows.append(
                {
                    "model": model,
                    "dataset": sample["dataset"],
                    "sample_id": sample["sample_id"],
                    "prompt_tokens": sample.get("total_prompt_tokens", 0),
                    "num_segments": len(sample.get("segments", [])),
                    "parse_ms": round(timings.get("parse_ms", 0.0), 6),
                    "policy_ms": round(timings["policy_ms"], 6),
                    "logging_ms": round(logging_ms, 6),
                    "proxy_overhead_ms": round(proxy_overhead, 6),
                    "vllm_ttft_ms": round(ttft, 6),
                    "ttft_source": "phase2_reference_model",
                    "overhead_ratio": round(proxy_overhead / ttft, 6) if ttft > 0 else 0.0,
                }
            )
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    print(f"mean_policy_ms={statistics.mean(float(r['policy_ms']) for r in rows):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
