#!/usr/bin/env python3
"""Build a proxy quality-risk ledger from unified segment samples."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


LEDGER_FIELDS = [
    "dataset",
    "task",
    "sample_id",
    "segment_index",
    "segment_type",
    "segment_token_count",
    "total_prompt_tokens",
    "action",
    "baseline_score",
    "action_score",
    "quality_drop",
    "risk_class",
    "evidence_type",
    "evaluation_ready",
    "note",
]

ACTIONS = [
    "fp16_baseline",
    "segment_eviction",
    "context_truncation",
    "shifted_position_proxy",
    "boundary_corruption",
    "boundary_repair_proxy",
]

SEGMENT_RISK_WEIGHT = {
    "SYS_PROMPT": 0.75,
    "USER_QUERY": 0.95,
    "ANSWER": 0.9,
    "RAG_CHUNK": 0.8,
    "HAYSTACK": 0.85,
    "NEEDLE": 1.0,
    "REPO_CONTEXT": 0.7,
    "CODE_PREFIX": 0.9,
}

ACTION_DROP = {
    "fp16_baseline": 0.0,
    "segment_eviction": 0.7,
    "context_truncation": 0.55,
    "shifted_position_proxy": 0.28,
    "boundary_corruption": 0.38,
    "boundary_repair_proxy": 0.12,
}


def risk_class(drop: float) -> str:
    if drop >= 0.45:
        return "high"
    if drop >= 0.2:
        return "medium"
    return "low"


def proxy_drop(action: str, segment_type: str, token_count: int, total_tokens: int) -> float:
    if action == "fp16_baseline":
        return 0.0
    weight = SEGMENT_RISK_WEIGHT.get(segment_type, 0.65)
    token_fraction = min(1.0, token_count / max(total_tokens, 1))
    size_modifier = 0.75 + 0.5 * token_fraction
    return min(1.0, ACTION_DROP[action] * weight * size_modifier)


def iter_samples(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_ledger(samples: list[dict[str, Any]], max_samples_per_dataset: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for sample in samples:
        dataset = sample["dataset"]
        if counts.get(dataset, 0) >= max_samples_per_dataset:
            continue
        counts[dataset] = counts.get(dataset, 0) + 1
        total_tokens = int(sample.get("total_prompt_tokens") or 0)
        metadata = sample.get("metadata", {})
        evaluation_ready = bool(metadata.get("evaluation_ready", dataset != "RepoBench"))
        for index, segment in enumerate(sample.get("segments", [])):
            token_count = int(segment.get("token_count") or 0)
            segment_type = segment.get("type", "UNKNOWN")
            for action in ACTIONS:
                drop = proxy_drop(action, segment_type, token_count, total_tokens)
                rows.append(
                    {
                        "dataset": dataset,
                        "task": sample.get("task", ""),
                        "sample_id": str(sample.get("sample_id", "")),
                        "segment_index": index,
                        "segment_type": segment_type,
                        "segment_token_count": token_count,
                        "total_prompt_tokens": total_tokens,
                        "action": action,
                        "baseline_score": 1.0,
                        "action_score": round(1.0 - drop, 4),
                        "quality_drop": round(drop, 4),
                        "risk_class": risk_class(drop),
                        "evidence_type": "proxy_heuristic_v0",
                        "evaluation_ready": evaluation_ready,
                        "note": "Proxy risk ledger for experiment design; not an official benchmark score.",
                    }
                )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/risk_ledger/quality_risk_ledger_v0.csv"))
    parser.add_argument("--max-samples-per-dataset", type=int, default=20)
    args = parser.parse_args()

    rows = build_ledger(iter_samples(args.samples), args.max_samples_per_dataset)
    write_csv(args.output, rows)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
