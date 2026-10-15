#!/usr/bin/env python3
"""Run Phase 12C real-task quality sanity for canonical-slot layout."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.phase12_prefix_cache_ab import approximate_prompt_tokens, percentile, send_chat_stream


LAYOUTS = ["raw-order", "canonical-slot"]
DEFAULT_TASKS = ["niah_single_1", "hotpotqa", "qasper", "narrativeqa", "python_repository_completion"]

RAW_FIELDS = [
    "layout",
    "dataset",
    "task",
    "sample_id",
    "success",
    "score",
    "contains_answer",
    "exact_match",
    "token_f1",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "prompt_tokens",
    "output_tokens",
    "answer",
    "output_text",
    "error_type",
    "error_message",
    "position_policy",
    "evaluation_ready",
    "notes",
]

SUMMARY_FIELDS = [
    "dataset",
    "task",
    "layout",
    "num_samples",
    "success_rate",
    "mean_score",
    "raw_mean_score",
    "quality_drop_vs_raw",
    "quality_drop_le_0_01",
    "quality_drop_le_0_03",
    "contains_answer_rate",
    "exact_match_rate",
    "token_f1_mean",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_total_latency_ms",
    "ttft_reduction_vs_raw_pct",
    "layout_guard",
    "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def score_answer(output: str, answer: Any, dataset: str) -> dict[str, float]:
    norm_output = normalize_text(output)
    answers = answer if isinstance(answer, list) else [answer]
    norm_answers = [normalize_text(item) for item in answers if normalize_text(item)]
    contains = 1.0 if any(ans and ans in norm_output for ans in norm_answers) else 0.0
    exact = 1.0 if norm_output in set(norm_answers) and norm_output else 0.0
    f1 = max((token_f1(output, ans) for ans in answers), default=0.0)
    score = contains if dataset == "RULER" else max(contains, f1)
    return {
        "score": round(score, 6),
        "contains_answer": contains,
        "exact_match": exact,
        "token_f1": round(f1, 6),
    }


def _stable_context(sample: dict[str, Any], stable_word_limit: int) -> str:
    parts = [
        f"[{segment.get('type', 'CONTEXT')}]\n{segment.get('text', '')}"
        for segment in sample.get("segments", [])
        if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}
    ]
    text = "\n\n".join(parts)
    words = text.split()
    if stable_word_limit > 0 and len(words) > stable_word_limit:
        text = " ".join(words[:stable_word_limit])
    return text


def _query_text(sample: dict[str, Any]) -> str:
    for segment in sample.get("segments", []):
        if segment.get("type") == "USER_QUERY":
            return str(segment.get("text", ""))
    return "Answer the benchmark query from the provided context."


def select_quality_subset(samples: list[dict[str, Any]], tasks: list[str], samples_per_task: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for task in tasks:
        count = 0
        for sample in samples:
            if sample.get("task") != task:
                continue
            selected.append(sample)
            count += 1
            if count >= samples_per_task:
                break
    return selected


def build_task_quality_prompt_case(
    sample: dict[str, Any],
    layout: str,
    stable_word_limit: int = 2600,
) -> dict[str, Any]:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    stable = _stable_context(sample, stable_word_limit)
    query = _query_text(sample)
    system = (
        "/no_think You answer benchmark tasks using only the provided context. "
        "Return the shortest correct answer or code completion."
    )
    warm_query = "Warm the stable context. Reply with OK."
    tool_obs = "[TOOL_OBS_DYNAMIC]\nNo extra evidence is provided; use the stable context and original query."
    stable_block = f"[STABLE_CONTEXT]\n{stable}"
    turn1_user = f"{stable_block}\n[WARMUP_QUERY]\n{warm_query}"
    if layout == "canonical-slot":
        turn2_user = f"{stable_block}\n{tool_obs}\n[USER_QUERY]\n{query}"
        position_policy = "canonical_slot_same_prefix"
    else:
        turn2_user = f"{tool_obs}\n{stable_block}\n[USER_QUERY]\n{query}"
        position_policy = "raw_order_middle_insert"
    turn1_messages = [{"role": "system", "content": system}, {"role": "user", "content": turn1_user}]
    turn2_messages = [{"role": "system", "content": system}, {"role": "user", "content": turn2_user}]
    return {
        "layout": layout,
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "answer": sample.get("answer", ""),
        "evaluation_ready": sample.get("metadata", {}).get("evaluation_ready", ""),
        "turn1_messages": turn1_messages,
        "turn2_messages": turn2_messages,
        "position_policy": position_policy,
        "prompt_tokens": approximate_prompt_tokens(turn2_messages),
    }


def run_quality_sanity(
    samples: list[dict[str, Any]],
    base_url: str,
    model: str,
    tasks: list[str],
    samples_per_task: int,
    stable_word_limit: int,
    max_tokens: int,
    timeout: float,
) -> list[dict[str, Any]]:
    selected = select_quality_subset(samples, tasks, samples_per_task)
    rows: list[dict[str, Any]] = []
    for sample in selected:
        for layout in LAYOUTS:
            case = build_task_quality_prompt_case(sample, layout, stable_word_limit)
            send_chat_stream(base_url, model, case["turn1_messages"], 8, timeout, f"phase12c-warm-{layout}-{case['sample_id']}")
            result = send_chat_stream(base_url, model, case["turn2_messages"], max_tokens, timeout, f"phase12c-{layout}-{case['sample_id']}")
            scores = score_answer(result.get("output_text", ""), case["answer"], case["dataset"])
            row = {
                "layout": layout,
                "dataset": case["dataset"],
                "task": case["task"],
                "sample_id": case["sample_id"],
                "success": result.get("success", False),
                **scores,
                "ttft_ms": result.get("ttft_ms", 0.0),
                "tpot_ms": result.get("tpot_ms", 0.0),
                "total_latency_ms": result.get("total_latency_ms", 0.0),
                "prompt_tokens": case["prompt_tokens"],
                "output_tokens": result.get("output_tokens", 0),
                "answer": case["answer"],
                "output_text": result.get("output_text", ""),
                "error_type": result.get("error_type", ""),
                "error_message": result.get("error_message", ""),
                "position_policy": case["position_policy"],
                "evaluation_ready": case["evaluation_ready"],
                "notes": "RepoBench score is a sanity proxy, not official RepoBench scoring.",
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            print(json.dumps(rows[-1], ensure_ascii=False))
    return rows


def aggregate_quality_sanity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["dataset"]), str(row["task"]), str(row["layout"])), []).append(row)

    raw_baselines: dict[tuple[str, str], tuple[float, float]] = {}
    for (dataset, task, layout), group in groups.items():
        if layout == "raw-order":
            scores = [_float(row["score"]) for row in group if _bool(row["success"])]
            ttft = [_float(row["ttft_ms"]) for row in group if _bool(row["success"])]
            raw_baselines[(dataset, task)] = (
                statistics.mean(scores) if scores else 0.0,
                statistics.mean(ttft) if ttft else 0.0,
            )

    out: list[dict[str, Any]] = []
    for (dataset, task, layout), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row["success"])]
        scores = [_float(row["score"]) for row in successes]
        ttft = [_float(row["ttft_ms"]) for row in successes]
        latency = [_float(row["total_latency_ms"]) for row in successes]
        raw_score, raw_ttft = raw_baselines.get((dataset, task), (0.0, 0.0))
        mean_score = statistics.mean(scores) if scores else 0.0
        quality_drop = max(0.0, raw_score - mean_score) if layout != "raw-order" else 0.0
        record = {
            "dataset": dataset,
            "task": task,
            "layout": layout,
            "num_samples": len(group),
            "success_rate": round(len(successes) / len(group), 6) if group else 0.0,
            "mean_score": round(mean_score, 6),
            "raw_mean_score": round(raw_score if layout != "raw-order" else mean_score, 6),
            "quality_drop_vs_raw": round(quality_drop, 6),
            "quality_drop_le_0_01": quality_drop <= 0.01,
            "quality_drop_le_0_03": quality_drop <= 0.03,
            "contains_answer_rate": round(statistics.mean(_float(row.get("contains_answer")) for row in group), 6) if group else 0.0,
            "exact_match_rate": round(statistics.mean(_float(row.get("exact_match")) for row in group), 6) if group else 0.0,
            "token_f1_mean": round(statistics.mean(_float(row.get("token_f1")) for row in group), 6) if group else 0.0,
            "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
            "ttft_reduction_vs_raw_pct": round((raw_ttft - statistics.mean(ttft)) / raw_ttft * 100.0, 6) if layout != "raw-order" and raw_ttft > 0 and ttft else 0.0,
            "layout_guard": "canonicalize only when segment contract allows reordering; otherwise preserve raw order",
            "claim_boundary": "Phase 12C task sanity, not official LongBench/RepoBench benchmark scoring.",
        }
        out.append({field: record.get(field, "") for field in SUMMARY_FIELDS})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--samples-per-task", type=int, default=3)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12c_task_quality_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12c_task_quality_summary_v0.csv"))
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        rows = load_jsonl(args.raw_output)
    else:
        rows = run_quality_sanity(
            load_jsonl(args.samples),
            args.base_url,
            args.model,
            [item.strip() for item in args.tasks.split(",") if item.strip()],
            args.samples_per_task,
            args.stable_word_limit,
            args.max_tokens,
            args.timeout,
        )
        write_jsonl(args.raw_output, rows)

    summary = aggregate_quality_sanity(rows)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"rows={len(rows)} summary_rows={len(summary)}")
    return 0 if rows and all(str(row.get("error_type")) == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
