#!/usr/bin/env python3
"""Merge an offline ContractKV dataset bundle into lightweight repo results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


READINESS_FIELDS = [
    "dataset",
    "source_zip",
    "source_present",
    "repo_extracted",
    "data_available",
    "prepare_method",
    "sample_count",
    "status",
    "source_note",
    "hf_cache_dir",
    "error_type",
    "error_message",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_sample(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if "total_prompt_tokens" not in normalized:
        normalized["total_prompt_tokens"] = normalized.pop("total_prompt_tokens_approx", None)
    normalized.setdefault("metadata", {})
    normalized.setdefault("answer", "")
    for segment in normalized.get("segments", []):
        segment.setdefault("token_count", 0)
    return normalized


def build_readiness(existing_path: Path, offline_rows: list[dict[str, Any]], hf_cache_dir: str) -> list[dict[str, Any]]:
    existing = {}
    if existing_path.exists():
        with existing_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                existing[row["dataset"]] = row

    result = []
    if "RULER" in existing:
        result.append(existing["RULER"])

    counts: dict[str, int] = {}
    for row in offline_rows:
        counts[row["dataset"]] = counts.get(row["dataset"], 0) + 1

    result.append(
        {
            "dataset": "LongBench",
            "source_zip": "contractkv_datasets.zip",
            "source_present": True,
            "repo_extracted": True,
            "data_available": counts.get("LongBench", 0) > 0,
            "prepare_method": "offline_bundle_huggingface_THUDM_LongBench",
            "sample_count": counts.get("LongBench", 0),
            "status": "ready" if counts.get("LongBench", 0) else "download_unavailable",
            "source_note": "LongBench loaded locally via HuggingFace THUDM/LongBench and uploaded as contractkv_datasets.zip",
            "hf_cache_dir": hf_cache_dir,
            "error_type": "none" if counts.get("LongBench", 0) else "download_unavailable",
            "error_message": "",
        }
    )
    result.append(
        {
            "dataset": "RepoBench",
            "source_zip": "contractkv_datasets.zip",
            "source_present": True,
            "repo_extracted": True,
            "data_available": counts.get("RepoBench", 0) > 0,
            "prepare_method": "offline_bundle_huggingface_tianyang_repobench_python_v1.1",
            "sample_count": counts.get("RepoBench", 0),
            "status": "ready" if counts.get("RepoBench", 0) else "download_unavailable",
            "source_note": "RepoBench loaded locally via HuggingFace tianyang/repobench_python_v1.1 and uploaded as contractkv_datasets.zip",
            "hf_cache_dir": hf_cache_dir,
            "error_type": "none" if counts.get("RepoBench", 0) else "download_unavailable",
            "error_message": "",
        }
    )
    result.append(
        {
            "dataset": "BFCL",
            "source_zip": "",
            "source_present": False,
            "repo_extracted": False,
            "data_available": False,
            "prepare_method": "not_downloaded",
            "sample_count": 0,
            "status": "missing_optional",
            "source_note": "BFCL missing_optional",
            "hf_cache_dir": hf_cache_dir,
            "error_type": "missing_optional",
            "error_message": "BFCL is not part of characterization_batch_001",
        }
    )
    return result


def write_readiness(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=READINESS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-outputs", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, default=Path("results/datasets"))
    parser.add_argument("--hf-cache-dir", required=True)
    args = parser.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)
    existing_samples = [r for r in load_jsonl(args.results_dir / "sample_prompts.jsonl") if r.get("dataset") == "RULER"]
    offline_samples = [normalize_sample(r) for r in load_jsonl(args.bundle_outputs / "sample_prompts.jsonl")]
    combined = existing_samples + offline_samples
    write_jsonl(args.results_dir / "sample_prompts.jsonl", combined)
    write_jsonl(args.results_dir / "longbench_samples.jsonl", [r for r in offline_samples if r.get("dataset") == "LongBench"])
    write_jsonl(args.results_dir / "repobench_samples.jsonl", [r for r in offline_samples if r.get("dataset") == "RepoBench"])

    existing_examples = load_jsonl(args.results_dir / "segment_examples.jsonl")
    offline_examples = [normalize_sample(r) for r in load_jsonl(args.bundle_outputs / "segment_examples.jsonl")]
    seen = set()
    examples = []
    for row in existing_examples + offline_examples:
        key = (row.get("dataset"), row.get("task"), str(row.get("sample_id")))
        if key in seen:
            continue
        seen.add(key)
        examples.append(row)
    write_jsonl(args.results_dir / "segment_examples.jsonl", examples)

    readiness = build_readiness(args.results_dir / "dataset_readiness.csv", offline_samples, args.hf_cache_dir)
    write_readiness(args.results_dir / "dataset_readiness.csv", readiness)
    write_readiness(args.results_dir / "longbench_readiness.csv", [r for r in readiness if r["dataset"] == "LongBench"])
    write_readiness(args.results_dir / "repobench_readiness.csv", [r for r in readiness if r["dataset"] == "RepoBench"])

    print(f"samples={len(combined)}")
    print(f"longbench={sum(1 for r in combined if r.get('dataset') == 'LongBench')}")
    print(f"repobench={sum(1 for r in combined if r.get('dataset') == 'RepoBench')}")
    print(f"examples={len(examples)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
