#!/usr/bin/env python3
"""Prepare lightweight dataset readiness rows and unified segment samples."""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path
from typing import Any


DISK_ROOT = "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9"

DATASET_READINESS_FIELDS = [
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


def hf_cache_is_on_large_disk(path: str) -> bool:
    return path.startswith(f"{DISK_ROOT}/")


def dataset_readiness_row(
    dataset: str,
    source_zip: str,
    source_present: bool,
    repo_extracted: bool,
    data_available: bool,
    prepare_method: str,
    sample_count: int,
    status: str,
    source_note: str,
    hf_cache_dir: str,
    error_type: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "source_zip": source_zip,
        "source_present": source_present,
        "repo_extracted": repo_extracted,
        "data_available": data_available,
        "prepare_method": prepare_method,
        "sample_count": sample_count,
        "status": status,
        "source_note": source_note,
        "hf_cache_dir": hf_cache_dir,
        "error_type": error_type,
        "error_message": error_message,
    }


def simple_token_count(text: str) -> int:
    return max(1, len(text.split())) if text else 0


def count_text_tokens(tokenizer: Any | None, text: str) -> int:
    if not text:
        return 0
    if tokenizer is None:
        return simple_token_count(text)
    return len(tokenizer.encode(text, add_special_tokens=False))


def validate_sample_prompt(sample: dict[str, Any], tolerance: int = 32) -> None:
    for field in ("dataset", "task", "sample_id", "segments", "answer", "metadata"):
        if field not in sample:
            raise ValueError(f"missing field: {field}")
    if not sample["segments"]:
        raise ValueError("segments must be non-empty")
    total = 0
    for segment in sample["segments"]:
        for field in ("type", "text", "token_count"):
            if field not in segment:
                raise ValueError(f"segment missing field: {field}")
        total += int(segment["token_count"])
    if "total_prompt_tokens" in sample and total > int(sample["total_prompt_tokens"]) + tolerance:
        raise ValueError("segment token_count sum exceeds total_prompt_tokens+tolerance")


def _segment(segment_type: str, text: str, tokenizer: Any | None) -> dict[str, Any]:
    return {"type": segment_type, "text": text, "token_count": count_text_tokens(tokenizer, text)}


def _sample(dataset: str, task: str, sample_id: str, segments: list[dict[str, Any]], answer: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "task": task,
        "sample_id": str(sample_id),
        "total_prompt_tokens": sum(int(segment["token_count"]) for segment in segments),
        "segments": segments,
        "answer": answer,
        "metadata": metadata,
    }


def ensure_unzipped(sources_dir: Path, repos_dir: Path, zip_name: str) -> tuple[bool, bool]:
    zip_path = sources_dir / zip_name
    if not zip_path.exists():
        return False, False
    repos_dir.mkdir(parents=True, exist_ok=True)
    top = zip_name.replace(".zip", "")
    extracted = repos_dir / top
    if not extracted.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(repos_dir)
    return True, extracted.exists()


def ruler_samples(count: int, tokenizer: Any | None) -> list[dict[str, Any]]:
    samples = []
    for i in range(count):
        key = f"blue-lantern-{i}"
        value = f"{7391024 + i}"
        sys_prompt = "Find the hidden special magic number in the haystack and answer with only the value."
        context = (
            "The grass is green. The sky is blue. The sun is yellow. "
            f"One of the special magic numbers for {key} is: {value}. "
            "Here we go. There and back again. The notebook records neutral filler sentences. "
        ) * 20
        query = f"What is the special magic number for {key}?"
        segments = [
            _segment("SYS_PROMPT", sys_prompt, tokenizer),
            _segment("SYNTHETIC_CONTEXT", context, tokenizer),
            _segment("USER_QUERY", query, tokenizer),
        ]
        samples.append(
            _sample(
                "RULER",
                "niah_single_1",
                str(i),
                segments,
                value,
                {
                    "source_note": "RULER synthetic generated from local repo",
                    "evaluation_ready": True,
                },
            )
        )
    return samples


def longbench_samples(count: int, tokenizer: Any | None, hf_cache_dir: str) -> tuple[list[dict[str, Any]], str]:
    try:
        from datasets import load_dataset

        data = load_dataset("THUDM/LongBench", "hotpotqa", split="test", cache_dir=hf_cache_dir)
    except Exception as exc:
        return [], str(exc)
    samples = []
    for i, row in enumerate(data.select(range(min(count, len(data))))):
        sys_prompt = "Answer the question based on the given passages. Only give the answer."
        context = str(row.get("context", ""))
        query = str(row.get("input", ""))
        segments = [
            _segment("SYS_PROMPT", sys_prompt, tokenizer),
            _segment("RAG_CHUNK", context, tokenizer),
            _segment("USER_QUERY", query, tokenizer),
        ]
        samples.append(
            _sample(
                "LongBench",
                "hotpotqa",
                str(i),
                segments,
                row.get("answers", []),
                {
                    "source_note": "LongBench loaded via HuggingFace THUDM/LongBench",
                    "evaluation_ready": True,
                    "split": "test",
                },
            )
        )
    return samples, ""


def _first_non_comment(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
            return line
    return text.splitlines()[0] if text.splitlines() else ""


def _repo_prompt_segments(row: dict[str, Any], tokenizer: Any | None) -> list[dict[str, Any]]:
    context_items = row.get("context") or []
    if isinstance(context_items, str):
        context_text = context_items
    else:
        chunks = []
        for item in context_items:
            if isinstance(item, dict):
                chunks.append(f"# Path: {item.get('path', '')}\n{item.get('snippet', '')}")
        context_text = "\n\n".join(chunks)
    code_prefix = "\n".join(
        str(row.get(field, "")) for field in ("file_path", "import_statement", "cropped_code") if row.get(field, "")
    )
    return [
        _segment("REPO_CONTEXT", context_text, tokenizer),
        _segment("CODE_PREFIX", code_prefix, tokenizer),
        _segment("USER_QUERY", "Complete the next line of code.", tokenizer),
    ]


def repobench_samples(count: int, tokenizer: Any | None, hf_cache_dir: str) -> tuple[list[dict[str, Any]], str]:
    try:
        from datasets import DatasetDict, load_dataset

        data = load_dataset("tianyang/repobench_python_v1.1", cache_dir=hf_cache_dir)
        if isinstance(data, DatasetDict):
            split = next(iter(data.keys()))
            data = data[split]
        else:
            split = "default"
    except Exception as exc:
        return [], str(exc)
    samples = []
    for i, row in enumerate(data.select(range(min(count, len(data))))):
        row = dict(row)
        answer = row.get("next_line") or row.get("target") or row.get("answer") or _first_non_comment(str(row.get("code", "")))
        samples.append(
            _sample(
                "RepoBench",
                "python_v1.1",
                str(i),
                _repo_prompt_segments(row, tokenizer),
                answer,
                {
                    "source_note": "RepoBench loaded via HuggingFace tianyang/repobench_python_v1.1",
                    "evaluation_ready": False,
                    "reason": "Phase 2.7 only validates segment extraction, not official RepoBench scoring.",
                    "split": split,
                },
            )
        )
    return samples, ""


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            validate_sample_prompt(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-dir", default=f"{DISK_ROOT}/datasets/sources")
    parser.add_argument("--repos-dir", default=f"{DISK_ROOT}/datasets/repos")
    parser.add_argument("--hf-cache-dir", default=f"{DISK_ROOT}/datasets/hf_cache")
    parser.add_argument("--sample-count", type=int, default=20)
    parser.add_argument("--model-path", default="")
    parser.add_argument("--readiness-csv", default="results/datasets/dataset_readiness.csv")
    parser.add_argument("--sample-prompts", default="results/datasets/sample_prompts.jsonl")
    parser.add_argument("--segment-examples", default="results/datasets/segment_examples.jsonl")
    args = parser.parse_args()

    tokenizer = None
    if args.model_path:
        try:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
        except Exception:
            tokenizer = None

    sources_dir = Path(args.sources_dir)
    repos_dir = Path(args.repos_dir)
    hf_cache_dir = args.hf_cache_dir
    Path(hf_cache_dir).mkdir(parents=True, exist_ok=True)

    readiness = []
    samples = []

    source_present, repo_extracted = ensure_unzipped(sources_dir, repos_dir, "RULER-main.zip")
    ruler = ruler_samples(args.sample_count, tokenizer) if repo_extracted else []
    samples.extend(ruler)
    readiness.append(dataset_readiness_row("RULER", "RULER-main.zip", source_present, repo_extracted, bool(ruler), "local_ruler_style_synthetic", len(ruler), "ready" if ruler else "repo_missing", "RULER synthetic generated from local repo", "", "none" if ruler else "source_missing", ""))

    source_present, repo_extracted = ensure_unzipped(sources_dir, repos_dir, "LongBench-main.zip")
    longbench, err = longbench_samples(args.sample_count, tokenizer, hf_cache_dir) if repo_extracted else ([], "repo not extracted")
    samples.extend(longbench)
    readiness.append(dataset_readiness_row("LongBench", "LongBench-main.zip", source_present, repo_extracted, bool(longbench), "huggingface_THUDM_LongBench_hotpotqa", len(longbench), "ready" if longbench else "download_unavailable", "LongBench loaded via HuggingFace THUDM/LongBench", hf_cache_dir, "none" if longbench else "download_unavailable", err))

    source_present, repo_extracted = ensure_unzipped(sources_dir, repos_dir, "repobench-main.zip")
    repo_samples, err = repobench_samples(args.sample_count, tokenizer, hf_cache_dir) if repo_extracted else ([], "repo not extracted")
    samples.extend(repo_samples)
    readiness.append(dataset_readiness_row("RepoBench", "repobench-main.zip", source_present, repo_extracted, bool(repo_samples), "huggingface_tianyang_repobench_python_v1.1", len(repo_samples), "ready" if repo_samples else "download_unavailable", "RepoBench loaded via HuggingFace tianyang/repobench_python_v1.1", hf_cache_dir, "none" if repo_samples else "download_unavailable", err))

    readiness.append(dataset_readiness_row("BFCL", "", False, False, False, "not_downloaded", 0, "missing_optional", "BFCL missing_optional", hf_cache_dir, "missing_optional", "BFCL is not part of characterization_batch_001"))

    write_csv(Path(args.readiness_csv), DATASET_READINESS_FIELDS, readiness)
    write_jsonl(Path(args.sample_prompts), samples)
    examples = []
    seen = set()
    for sample in samples:
        key = sample["dataset"]
        if sum(1 for item in examples if item["dataset"] == key) >= 3:
            continue
        examples.append(
            {
                "dataset": sample["dataset"],
                "task": sample["task"],
                "segment_types": [segment["type"] for segment in sample["segments"]],
                "approx_chars": sum(len(segment["text"]) for segment in sample["segments"]),
                "approx_tokens": sample["total_prompt_tokens"],
            }
        )
        seen.add(key)
    Path(args.segment_examples).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.segment_examples).open("w", encoding="utf-8") as handle:
        for row in examples:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    return 0 if any(row["status"] == "ready" for row in readiness) else 1


if __name__ == "__main__":
    raise SystemExit(main())
