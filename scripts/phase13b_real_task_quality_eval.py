#!/usr/bin/env python3
"""Attach real Qwen3-8B task scores to the Phase 13B live replay.

Phase 13B SSPP/RAR do not change the model prompt.  Therefore their quality
rows are explicitly marked as projections of the real CAPOSC output, rather
than being presented as fresh model generations.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_task_quality_sanity import score_answer


POLICY_LAYOUT = {
    "vllm-raw-order": "raw-order",
    "contractkv-caposc": "canonical-slot",
    "contractkv-caposc-sspp": "canonical-slot",
    "contractkv-caposc-sspp-rar": "canonical-slot",
}

RAW_FIELDS = [
    "policy",
    "dataset",
    "task",
    "sample_id",
    "source_layout",
    "scoring_provenance",
    "success",
    "score",
    "contains_answer",
    "exact_match",
    "token_f1",
    "prompt_tokens",
    "output_tokens",
    "answer",
    "output_text",
    "error_type",
    "error_message",
    "evaluation_ready",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "policy",
    "dataset",
    "task",
    "num_samples",
    "successful_samples",
    "success_rate",
    "mean_score",
    "raw_mean_score",
    "quality_drop_vs_raw",
    "quality_drop_le_0_01",
    "quality_drop_le_0_03",
    "contains_answer_rate",
    "token_f1_mean",
    "scoring_provenance",
    "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def build_quality_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in source_rows:
        layout = str(source.get("layout", ""))
        if layout not in {"raw-order", "canonical-slot"}:
            continue
        scores = score_answer(source.get("output_text", ""), source.get("answer", ""), source.get("dataset", ""))
        for policy, source_layout in POLICY_LAYOUT.items():
            if source_layout != layout:
                continue
            direct = policy in {"vllm-raw-order", "contractkv-caposc"}
            row = {
                "policy": policy,
                "dataset": source.get("dataset", ""),
                "task": source.get("task", ""),
                "sample_id": source.get("sample_id", ""),
                "source_layout": layout,
                "scoring_provenance": "fresh_real_qwen3_8b_output" if direct else "projected_from_real_caposc_output",
                "success": source.get("success", False),
                **scores,
                "prompt_tokens": source.get("prompt_tokens", ""),
                "output_tokens": source.get("output_tokens", ""),
                "answer": source.get("answer", ""),
                "output_text": source.get("output_text", ""),
                "error_type": source.get("error_type", ""),
                "error_message": source.get("error_message", ""),
                "evaluation_ready": source.get("evaluation_ready", ""),
                "claim_boundary": (
                    "Real Qwen3-8B task sanity; SSPP/RAR rows reuse CAPOSC output because these execution layers do not alter prompt text."
                ),
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
    return rows


def summarize_quality_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["policy"]), str(row["dataset"]), str(row["task"])), []).append(row)
    baselines: dict[tuple[str, str], float] = {}
    for (policy, dataset, task), group in groups.items():
        if policy == "vllm-raw-order":
            good = [float(row["score"]) for row in group if _bool(row["success"])]
            baselines[(dataset, task)] = statistics.mean(good) if good else 0.0
    output: list[dict[str, Any]] = []
    for (policy, dataset, task), group in sorted(groups.items()):
        good = [row for row in group if _bool(row["success"])]
        scores = [float(row["score"]) for row in good]
        mean_score = statistics.mean(scores) if scores else 0.0
        baseline = baselines.get((dataset, task), mean_score)
        drop = max(0.0, baseline - mean_score) if policy != "vllm-raw-order" else 0.0
        provenance = "fresh_real_qwen3_8b_output" if policy in {"vllm-raw-order", "contractkv-caposc"} else "projected_from_real_caposc_output"
        row = {
            "policy": policy,
            "dataset": dataset,
            "task": task,
            "num_samples": len(group),
            "successful_samples": len(good),
            "success_rate": round(len(good) / len(group), 6) if group else 0.0,
            "mean_score": round(mean_score, 6),
            "raw_mean_score": round(baseline, 6),
            "quality_drop_vs_raw": round(drop, 6),
            "quality_drop_le_0_01": drop <= 0.01,
            "quality_drop_le_0_03": drop <= 0.03,
            "contains_answer_rate": round(statistics.mean(float(row["contains_answer"]) for row in group), 6) if group else 0.0,
            "token_f1_mean": round(statistics.mean(float(row["token_f1"]) for row in group), 6) if group else 0.0,
            "scoring_provenance": provenance,
            "claim_boundary": "Task sanity proxy, not official LongBench or RepoBench benchmark scoring.",
        }
        output.append({field: row.get(field, "") for field in SUMMARY_FIELDS})
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/prefix_cache/phase12c_task_quality_raw_v0.jsonl"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13b_real_task_quality_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13b_real_task_quality_summary_v0.csv"))
    args = parser.parse_args()
    rows = build_quality_rows(load_jsonl(args.input))
    summary = summarize_quality_rows(rows)
    write_jsonl(args.raw_output, rows)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"quality_rows={len(rows)} summary_rows={len(summary)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
