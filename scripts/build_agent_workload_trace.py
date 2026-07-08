#!/usr/bin/env python3
"""Build Phase 7 agent-style workload traces from unified samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SLACK_BUCKETS_MS = [0, 10, 50, 100, 200, 500]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_trace_record(
    sample: dict[str, Any],
    index: int,
    slack_ms: int,
    arrival_time_ms: int,
    slo_ttft_ms: int = 200,
    policy: str = "ContractKV-Joint",
) -> dict[str, Any]:
    return {
        "trace_id": f"{sample['dataset']}-{sample.get('sample_id', index)}-{index}",
        "dataset": sample["dataset"],
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", index)),
        "turn_id": index,
        "segments": sample.get("segments", []),
        "prompt_tokens": int(sample.get("total_prompt_tokens") or 0),
        "tool_slack_ms": slack_ms,
        "arrival_time_ms": arrival_time_ms,
        "slo_ttft_ms": slo_ttft_ms,
        "policy": policy,
        "answer": sample.get("answer", ""),
        "metadata": {
            "source": "phase7_agent_workload_trace",
            "original_dataset": sample["dataset"],
        },
    }


def build_traces(samples: list[dict[str, Any]], arrival_gap_ms: int, slo_ttft_ms: int) -> list[dict[str, Any]]:
    traces = []
    for index, sample in enumerate(samples):
        slack = SLACK_BUCKETS_MS[index % len(SLACK_BUCKETS_MS)]
        traces.append(build_trace_record(sample, index, slack, index * arrival_gap_ms, slo_ttft_ms))
    return traces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--arrival-gap-ms", type=int, default=50)
    parser.add_argument("--slo-ttft-ms", type=int, default=200)
    args = parser.parse_args()
    traces = build_traces(load_jsonl(args.samples), args.arrival_gap_ms, args.slo_ttft_ms)
    write_jsonl(args.output, traces)
    print(f"traces={len(traces)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
