#!/usr/bin/env python3
"""Analyze the 400-row Phase 13C fresh quality replay."""

from __future__ import annotations

import argparse
import ast
import csv
import difflib
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


POLICIES = ["raw-order", "canonical-all", "static-posc", "contractkv-caposc"]
RAW_FIELDS = [
    "dataset", "task", "sample_id", "policy", "score", "raw_score", "signed_quality_delta",
    "paired_outcome", "violated_edges", "python_parse_success", "python_compile_success",
    "edit_similarity", "output_text", "answer", "prompt_hash", "prompt_tokens", "success",
    "claim_boundary",
]
SUMMARY_FIELDS = [
    "dataset", "task", "policy", "num_samples", "successful_samples", "mean_score", "raw_mean_score",
    "mean_signed_quality_delta", "quality_drop", "quality_drop_le_0_03", "paired_wins", "paired_ties",
    "paired_losses", "bootstrap_ci_low", "bootstrap_ci_high", "violated_edge_rows", "python_parse_rate",
    "python_compile_rate", "mean_edit_similarity", "claim_boundary",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _code_metrics(output: str, answer: str) -> tuple[bool, bool, float]:
    text = re.sub(r"<think>.*?</think>", "", str(output), flags=re.DOTALL | re.IGNORECASE).strip()
    target = str(answer).strip()
    try:
        ast.parse(text)
        parse_ok = True
    except (SyntaxError, ValueError, TypeError):
        parse_ok = False
    compile_ok = False
    if parse_ok:
        try:
            compile(text, "<phase13c-output>", "exec")
            compile_ok = True
        except (SyntaxError, ValueError, TypeError):
            compile_ok = False
    similarity = difflib.SequenceMatcher(None, text, target).ratio() if target else 0.0
    return parse_ok, compile_ok, round(similarity, 6)


def _bootstrap(values: list[float], seed: int = 13, repeats: int = 2000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = []
    for _ in range(repeats):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.mean(sample))
    means.sort()
    return round(means[int(0.025 * (len(means) - 1))], 6), round(means[int(0.975 * (len(means) - 1))], 6)


def analyze(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_sample: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_sample[(str(row["dataset"]), str(row["task"]), str(row["sample_id"]))][str(row["policy"])] = row
    raw_scores = {
        key: _float(policy_rows.get("raw-order", {}).get("score"))
        for key, policy_rows in by_sample.items()
    }
    enriched = []
    for key, policy_rows in sorted(by_sample.items()):
        raw_score = raw_scores[key]
        for policy in POLICIES:
            source = policy_rows.get(policy)
            if source is None:
                continue
            score = _float(source.get("score"))
            delta = score - raw_score
            outcome = "win" if delta > 1e-9 else "loss" if delta < -1e-9 else "tie"
            parse_ok = compile_ok = False
            edit_similarity = 0.0
            if key[0] == "RepoBench":
                parse_ok, compile_ok, edit_similarity = _code_metrics(source.get("output_text", ""), source.get("answer", ""))
            enriched.append({
                "dataset": key[0], "task": key[1], "sample_id": key[2], "policy": policy,
                "score": round(score, 6), "raw_score": round(raw_score, 6), "signed_quality_delta": round(delta, 6),
                "paired_outcome": "baseline" if policy == "raw-order" else outcome,
                "violated_edges": source.get("violated_edges", "[]"),
                "python_parse_success": parse_ok if key[0] == "RepoBench" else "",
                "python_compile_success": compile_ok if key[0] == "RepoBench" else "",
                "edit_similarity": edit_similarity if key[0] == "RepoBench" else "",
                "output_text": source.get("output_text", ""), "answer": source.get("answer", ""),
                "prompt_hash": source.get("prompt_hash", ""), "prompt_tokens": source.get("prompt_tokens", ""),
                "success": source.get("success", False),
                "claim_boundary": "Fresh Qwen3-8B quality sanity; not official benchmark scoring.",
            })
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        groups[(row["dataset"], row["task"], row["policy"])].append(row)
    summary = []
    for (dataset, task, policy), group in sorted(groups.items()):
        good = [row for row in group if _bool(row["success"])]
        deltas = [_float(row["signed_quality_delta"]) for row in good if policy != "raw-order"]
        scores = [_float(row["score"]) for row in good]
        raw = statistics.mean([_float(row["raw_score"]) for row in group]) if group else 0.0
        mean_score = statistics.mean(scores) if scores else 0.0
        wins = sum(row["paired_outcome"] == "win" for row in group)
        ties = sum(row["paired_outcome"] == "tie" for row in group)
        losses = sum(row["paired_outcome"] == "loss" for row in group)
        parse_rows = [row for row in group if row["python_parse_success"] != ""]
        compile_rows = [row for row in group if row["python_compile_success"] != ""]
        summary.append({
            "dataset": dataset, "task": task, "policy": policy, "num_samples": len(group),
            "successful_samples": len(good), "mean_score": round(mean_score, 6), "raw_mean_score": round(raw, 6),
            "mean_signed_quality_delta": round(statistics.mean(deltas), 6) if deltas else 0.0,
            "quality_drop": round(max(0.0, raw - mean_score), 6), "quality_drop_le_0_03": max(0.0, raw - mean_score) <= 0.03,
            "paired_wins": wins, "paired_ties": ties, "paired_losses": losses,
            "bootstrap_ci_low": _bootstrap(deltas)[0] if deltas else 0.0,
            "bootstrap_ci_high": _bootstrap(deltas)[1] if deltas else 0.0,
            "violated_edge_rows": sum(bool(json.loads(row["violated_edges"])) for row in group),
            "python_parse_rate": round(sum(_bool(row["python_parse_success"]) for row in parse_rows) / len(parse_rows), 6) if parse_rows else "",
            "python_compile_rate": round(sum(_bool(row["python_compile_success"]) for row in compile_rows) / len(compile_rows), 6) if compile_rows else "",
            "mean_edit_similarity": round(statistics.mean(_float(row["edit_similarity"]) for row in parse_rows), 6) if parse_rows else "",
            "claim_boundary": "Fresh Qwen3-8B quality sanity; paired task metric, not official benchmark scoring.",
        })
    return enriched, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/end_to_end/phase13c_quality_raw_v0.jsonl"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13c_quality_enriched_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13c_quality_enriched_summary_v0.csv"))
    args = parser.parse_args()
    enriched, summary = analyze(read_jsonl(args.input))
    write_jsonl(args.raw_output, enriched)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"enriched_rows={len(enriched)} summary_rows={len(summary)}")
    return 0 if enriched else 1


if __name__ == "__main__":
    raise SystemExit(main())
