#!/usr/bin/env python3
"""Run real-model quality matrix conditions for Qwen3-8B."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


CONDITIONS = [
    "full_context_baseline",
    "segment_eviction",
    "context_truncation",
    "boundary_corruption",
    "boundary_repair",
    "contractkv_safe_decision",
]

MATRIX_FIELDS = [
    "dataset",
    "task",
    "condition",
    "num_samples",
    "mean_score",
    "baseline_mean_score",
    "mean_quality_drop",
    "contains_answer_rate",
    "exact_match_rate",
    "token_f1_mean",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = MATRIX_FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(text: Any) -> str:
    if isinstance(text, list):
        text = " ".join(str(item) for item in text)
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9_./#-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_f1(prediction: str, answer: Any) -> float:
    pred_tokens = normalize_text(prediction).split()
    ans_tokens = normalize_text(answer).split()
    if not pred_tokens or not ans_tokens:
        return 0.0
    overlap = Counter(pred_tokens) & Counter(ans_tokens)
    common = sum(overlap.values())
    if common == 0:
        return 0.0
    precision = common / len(pred_tokens)
    recall = common / len(ans_tokens)
    return 2 * precision * recall / (precision + recall)


def score_output(output: str, answer: Any, dataset: str) -> dict[str, float]:
    norm_output = normalize_text(output)
    answers = answer if isinstance(answer, list) else [answer]
    norm_answers = [normalize_text(item) for item in answers if normalize_text(item)]
    contains = 1.0 if any(ans and ans in norm_output for ans in norm_answers) else 0.0
    exact = 1.0 if norm_output in set(norm_answers) and norm_output else 0.0
    f1 = max((token_f1(output, ans) for ans in answers), default=0.0)
    if dataset == "RULER":
        score = contains
    elif dataset in {"LongBench", "RepoBench"}:
        score = max(contains, f1)
    else:
        score = max(contains, f1)
    return {
        "score": round(score, 6),
        "contains_answer": contains,
        "exact_match": exact,
        "token_f1": round(f1, 6),
    }


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    parts = []
    for segment in segments:
        parts.append(f"[{segment.get('type', 'UNKNOWN')}]\n{segment.get('text', '')}")
    return "\n\n".join(parts)


def _largest_context_index(segments: list[dict[str, Any]]) -> int | None:
    candidates = [
        (i, int(segment.get("token_count") or 0))
        for i, segment in enumerate(segments)
        if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[0]


def build_condition_messages(sample: dict[str, Any], condition: str) -> list[dict[str, str]]:
    segments = [dict(segment) for segment in sample.get("segments", [])]
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    if condition == "segment_eviction":
        index = _largest_context_index(segments)
        if index is not None:
            segments.pop(index)
    elif condition == "context_truncation":
        index = _largest_context_index(segments)
        if index is not None:
            text = str(segments[index].get("text", ""))
            segments[index]["text"] = text[: max(64, len(text) // 4)]
    elif condition == "boundary_corruption":
        for segment in segments:
            if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}:
                text = str(segment.get("text", ""))
                midpoint = len(text) // 2
                segment["text"] = text[:midpoint] + "\n[BOUNDARY_SHIFTED_NOISE]\n" + text[midpoint + 64 :]
                break
    elif condition == "boundary_repair":
        for segment in segments:
            if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}:
                text = str(segment.get("text", ""))
                midpoint = len(text) // 2
                segment["text"] = text[:midpoint] + "\n[REPAIR_HINT: ignore boundary noise and recover the relevant answer evidence]\n" + text[midpoint:]
                break
    elif condition == "contractkv_safe_decision":
        segments = [
            segment
            for segment in segments
            if segment.get("type") in {"SYS_PROMPT", "USER_QUERY"}
            or int(segment.get("token_count") or 0) >= 128
        ]
    prompt = (
        "You are evaluating a long-context benchmark sample. Answer the user query using only the provided context. "
        "Do not include reasoning. Return only the shortest correct answer. /no_think\n\n"
        + _segments_to_text(segments)
    )
    return [{"role": "user", "content": prompt}]


def chat_completion(base_url: str, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float) -> tuple[str, float, str, str]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - start) * 1000
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content, latency_ms, "none", ""
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return "", latency_ms, type(exc).__name__, str(exc)


def run_quality_matrix(
    samples: list[dict[str, Any]],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    max_samples: int | None = None,
) -> list[dict[str, Any]]:
    rows = []
    selected = samples[:max_samples] if max_samples is not None else samples
    for sample in selected:
        for condition in CONDITIONS:
            messages = build_condition_messages(sample, condition)
            output, latency_ms, error_type, error_message = chat_completion(base_url, model, messages, max_tokens, timeout)
            scores = score_output(output, sample.get("answer", ""), sample["dataset"])
            rows.append(
                {
                    "dataset": sample["dataset"],
                    "task": sample.get("task", ""),
                    "sample_id": str(sample.get("sample_id", "")),
                    "condition": condition,
                    "model": model,
                    "output": output,
                    "answer": sample.get("answer", ""),
                    "latency_ms": round(latency_ms, 6),
                    "error_type": error_type,
                    "error_message": error_message[:300],
                    **scores,
                }
            )
    return rows


def aggregate_quality_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["dataset"], row["task"], row["condition"]), []).append(row)
    baseline: dict[tuple[str, str], float] = {}
    for (dataset, task, condition), group in groups.items():
        if condition == "full_context_baseline":
            baseline[(dataset, task)] = statistics.mean(float(row["score"]) for row in group)
    out = []
    for (dataset, task, condition), group in sorted(groups.items()):
        mean_score = statistics.mean(float(row["score"]) for row in group)
        base = baseline.get((dataset, task), mean_score)
        out.append(
            {
                "dataset": dataset,
                "task": task,
                "condition": condition,
                "num_samples": len(group),
                "mean_score": round(mean_score, 6),
                "baseline_mean_score": round(base, 6),
                "mean_quality_drop": round(max(0.0, base - mean_score), 6),
                "contains_answer_rate": round(statistics.mean(float(row.get("contains_answer", row["score"])) for row in group), 6),
                "exact_match_rate": round(statistics.mean(float(row.get("exact_match", 0.0)) for row in group), 6),
                "token_f1_mean": round(statistics.mean(float(row.get("token_f1", row["score"])) for row in group), 6),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--outputs", type=Path, default=Path("results/hard_systems/real_quality_outputs_qwen3_8b_v0.jsonl"))
    parser.add_argument("--matrix", type=Path, default=Path("results/hard_systems/real_quality_matrix_qwen3_8b_v0.csv"))
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-samples", type=int, default=0)
    args = parser.parse_args()
    rows = run_quality_matrix(
        load_jsonl(args.samples),
        args.base_url,
        args.model,
        args.max_tokens,
        args.timeout,
        max_samples=args.max_samples if args.max_samples > 0 else None,
    )
    write_jsonl(args.outputs, rows)
    write_csv(args.matrix, aggregate_quality_matrix(rows))
    print(f"quality_rows={len(rows)}")
    return 0 if rows and all(row["error_type"] == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
