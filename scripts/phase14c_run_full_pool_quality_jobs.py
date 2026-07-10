#!/usr/bin/env python3
"""Run and summarize Phase 14C full-pool fresh quality jobs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import approximate_prompt_tokens, send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import _compile, build_case


RAW_FIELDS = [
    "timestamp",
    "job_id",
    "sample_key",
    "partition",
    "dataset",
    "task",
    "sample_id",
    "policy",
    "model",
    "selected_layout_policy",
    "layout_decision",
    "topological_order",
    "dependency_edges",
    "violated_edges",
    "prompt_hash",
    "prompt_tokens",
    "success",
    "score",
    "contains_answer",
    "exact_match",
    "token_f1",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "output_tokens",
    "answer",
    "output_text",
    "request_id",
    "error_type",
    "error_message",
    "claim_boundary",
]

LABEL_FIELDS = [
    "sample_key",
    "partition",
    "dataset",
    "task",
    "sample_id",
    "raw_score",
    "candidate_score",
    "quality_drop_vs_raw",
    "unsafe_quality_drop",
    "qc_prelabel_fallback",
    "safe_optimization",
    "false_safe",
    "raw_success",
    "candidate_success",
    "raw_request_id",
    "candidate_request_id",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "split",
    "dataset",
    "task",
    "requests",
    "labeled_pairs",
    "unsafe_requests",
    "fallback_rate",
    "false_safe_rate",
    "safe_optimization_coverage",
    "unsafe_caught_rate",
    "mean_quality_drop",
    "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def sample_key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset','')}::{sample.get('task','')}::{sample.get('sample_id','')}"


def index_samples(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {sample_key(sample): sample for sample in samples}


def completed_job_ids(raw_rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("job_id", "")) for row in raw_rows if row.get("job_id")}


def select_pending_jobs(
    jobs: list[dict[str, Any]],
    done: set[str],
    partitions: set[str] | None = None,
    policies: set[str] | None = None,
    max_jobs: int | None = None,
) -> list[dict[str, Any]]:
    selected = []
    for job in jobs:
        if str(job.get("job_id", "")) in done:
            continue
        if partitions and str(job.get("partition", "")) not in partitions:
            continue
        if policies and str(job.get("policy", "")) not in policies:
            continue
        selected.append(job)
        if max_jobs is not None and len(selected) >= max_jobs:
            break
    return selected


def _score_float(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.0
    try:
        return float(row.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _success(row: dict[str, Any] | None) -> bool:
    return row is not None and (row.get("success") is True or str(row.get("success", "")).lower() == "true")


def quality_messages(case: dict[str, Any], compiled_text: str) -> list[dict[str, str]]:
    namespace = f"PHASE14C:{case['dataset']}:{case['task']}:{case['sample_id']}"
    system = "/no_think Answer the task using only the provided context. Return the shortest correct answer or code completion."
    return [{"role": "system", "content": namespace + "\n" + system}, {"role": "user", "content": compiled_text}]


def build_output_row(
    job: dict[str, Any],
    sample: dict[str, Any],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    stable_word_limit: int,
) -> dict[str, Any]:
    case = build_case(sample, stable_word_limit=stable_word_limit)
    compiled = _compile(str(job["policy"]), case, SegmentPrefixLedger())
    text = _ordered_text(compiled["topological_order"], case["segments"])
    messages = quality_messages(case, text)
    prompt_hash = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    result = send_chat_stream(
        base_url,
        model,
        messages,
        max_tokens,
        timeout,
        f"phase14c-{job['job_id']}-{job['policy']}",
    )
    scores = score_answer(result.get("output_text", ""), sample.get("answer", ""), str(sample.get("dataset", "")))
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job.get("job_id", ""),
        "sample_key": job.get("sample_key", sample_key(sample)),
        "partition": job.get("partition", ""),
        "dataset": job.get("dataset", sample.get("dataset", "")),
        "task": job.get("task", sample.get("task", "")),
        "sample_id": str(job.get("sample_id", sample.get("sample_id", ""))),
        "policy": job.get("policy", ""),
        "model": model,
        "selected_layout_policy": compiled.get("selected_policy", job.get("policy", "")),
        "layout_decision": compiled.get("layout_decision", ""),
        "topological_order": json.dumps(compiled.get("topological_order", [])),
        "dependency_edges": json.dumps(compiled.get("dependency_edges", [])),
        "violated_edges": json.dumps(compiled.get("violated_edges", [])),
        "prompt_hash": prompt_hash,
        "prompt_tokens": approximate_prompt_tokens(messages),
        "success": result.get("success", False),
        **scores,
        "ttft_ms": result.get("ttft_ms", 0.0),
        "tpot_ms": result.get("tpot_ms", 0.0),
        "total_latency_ms": result.get("total_latency_ms", 0.0),
        "output_tokens": result.get("output_tokens", 0),
        "answer": sample.get("answer", ""),
        "output_text": result.get("output_text", ""),
        "request_id": result.get("request_id", ""),
        "error_type": result.get("error_type", ""),
        "error_message": result.get("error_message", ""),
        "claim_boundary": "Fresh Qwen3-8B paired task-sanity label for Phase 14C QC calibration; not official benchmark scoring.",
    }
    return {field: row.get(field, "") for field in RAW_FIELDS}


def run_jobs(
    full_pool: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    existing_raw: list[dict[str, Any]],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    stable_word_limit: int,
    partitions: set[str] | None = None,
    policies: set[str] | None = None,
    max_jobs: int | None = None,
) -> list[dict[str, Any]]:
    samples = index_samples(full_pool)
    pending = select_pending_jobs(jobs, completed_job_ids(existing_raw), partitions, policies, max_jobs)
    rows = []
    for index, job in enumerate(pending, start=1):
        key = str(job.get("sample_key", ""))
        if key not in samples:
            rows.append(
                {
                    **{field: "" for field in RAW_FIELDS},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_id": job.get("job_id", ""),
                    "sample_key": key,
                    "partition": job.get("partition", ""),
                    "dataset": job.get("dataset", ""),
                    "task": job.get("task", ""),
                    "sample_id": job.get("sample_id", ""),
                    "policy": job.get("policy", ""),
                    "model": model,
                    "success": False,
                    "error_type": "sample_missing",
                    "error_message": "sample_key not found in full pool",
                    "claim_boundary": "Failed before model call.",
                }
            )
            continue
        started = time.perf_counter()
        row = build_output_row(job, samples[key], base_url, model, max_tokens, timeout, stable_word_limit)
        row["claim_boundary"] += f" runner_index={index}; runner_wall_ms={(time.perf_counter() - started) * 1000.0:.3f}"
        rows.append(row)
    return rows


def iter_job_rows(
    full_pool: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    existing_raw: list[dict[str, Any]],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    stable_word_limit: int,
    partitions: set[str] | None = None,
    policies: set[str] | None = None,
    max_jobs: int | None = None,
):
    samples = index_samples(full_pool)
    pending = select_pending_jobs(jobs, completed_job_ids(existing_raw), partitions, policies, max_jobs)
    for index, job in enumerate(pending, start=1):
        key = str(job.get("sample_key", ""))
        if key not in samples:
            yield {
                **{field: "" for field in RAW_FIELDS},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "job_id": job.get("job_id", ""),
                "sample_key": key,
                "partition": job.get("partition", ""),
                "dataset": job.get("dataset", ""),
                "task": job.get("task", ""),
                "sample_id": job.get("sample_id", ""),
                "policy": job.get("policy", ""),
                "model": model,
                "success": False,
                "error_type": "sample_missing",
                "error_message": "sample_key not found in full pool",
                "claim_boundary": "Failed before model call.",
            }
            continue
        started = time.perf_counter()
        row = build_output_row(job, samples[key], base_url, model, max_tokens, timeout, stable_word_limit)
        row["claim_boundary"] += f" runner_index={index}; runner_wall_ms={(time.perf_counter() - started) * 1000.0:.3f}"
        yield row


def _feature_by_key(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("sample_key", "")): row for row in features}


def build_labels(raw_rows: list[dict[str, Any]], features: list[dict[str, Any]], eps: float = 0.03) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in raw_rows:
        grouped[str(row.get("sample_key", ""))][str(row.get("policy", ""))] = row
    features_by_key = _feature_by_key(features)
    output = []
    for key, policies in sorted(grouped.items()):
        raw = policies.get("raw-order")
        candidate = policies.get("contractkv-caposc")
        if raw is None or candidate is None:
            continue
        feature = features_by_key.get(key, {})
        raw_score = _score_float(raw)
        candidate_score = _score_float(candidate)
        drop = max(0.0, raw_score - candidate_score)
        fallback = feature.get("qc_prelabel_fallback") is True or str(feature.get("qc_prelabel_fallback", "")).lower() == "true"
        unsafe = drop > eps
        row = {
            "sample_key": key,
            "partition": raw.get("partition", feature.get("partition", "")),
            "dataset": raw.get("dataset", feature.get("dataset", "")),
            "task": raw.get("task", feature.get("task", "")),
            "sample_id": raw.get("sample_id", feature.get("sample_id", "")),
            "raw_score": round(raw_score, 6),
            "candidate_score": round(candidate_score, 6),
            "quality_drop_vs_raw": round(drop, 6),
            "unsafe_quality_drop": unsafe,
            "qc_prelabel_fallback": fallback,
            "safe_optimization": (not fallback) and (not unsafe) and _success(raw) and _success(candidate),
            "false_safe": (not fallback) and unsafe,
            "raw_success": _success(raw),
            "candidate_success": _success(candidate),
            "raw_request_id": raw.get("request_id", ""),
            "candidate_request_id": candidate.get("request_id", ""),
            "claim_boundary": "Paired fresh Qwen3-8B task-sanity label; not official benchmark scoring.",
        }
        output.append({field: row.get(field, "") for field in LABEL_FIELDS})
    return output


def summarize_labels(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {("all", "all", "all"): labels}
    for row in labels:
        groups.setdefault((str(row["partition"]), "all", "all"), []).append(row)
        groups.setdefault((str(row["partition"]), str(row["dataset"]), str(row["task"])), []).append(row)
    output = []
    for (split, dataset, task), group in sorted(groups.items()):
        if not group:
            continue
        unsafe = [row for row in group if row["unsafe_quality_drop"] is True or str(row["unsafe_quality_drop"]).lower() == "true"]
        accepted = [row for row in group if not (row["qc_prelabel_fallback"] is True or str(row["qc_prelabel_fallback"]).lower() == "true")]
        safe = [row for row in group if not (row["unsafe_quality_drop"] is True or str(row["unsafe_quality_drop"]).lower() == "true")]
        quality_drops = []
        for row in group:
            try:
                quality_drops.append(float(row["quality_drop_vs_raw"]))
            except (TypeError, ValueError):
                pass
        output.append(
            {
                "split": split,
                "dataset": dataset,
                "task": task,
                "requests": len(group),
                "labeled_pairs": sum(bool(row["raw_success"]) and bool(row["candidate_success"]) for row in group),
                "unsafe_requests": len(unsafe),
                "fallback_rate": round(sum(bool(row["qc_prelabel_fallback"]) for row in group) / len(group), 6),
                "false_safe_rate": round(sum(bool(row["false_safe"]) for row in group) / max(1, len(accepted)), 6),
                "safe_optimization_coverage": round(sum(bool(row["safe_optimization"]) for row in group) / max(1, len(safe)), 6),
                "unsafe_caught_rate": round(sum(bool(row["qc_prelabel_fallback"]) for row in unsafe) / max(1, len(unsafe)), 6),
                "mean_quality_drop": round(sum(quality_drops) / len(quality_drops), 6) if quality_drops else 0.0,
                "claim_boundary": "Phase 14C QC summary over completed paired fresh labels only.",
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, default=Path("results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl"))
    parser.add_argument("--features", type=Path, default=Path("results/end_to_end/phase14c_full_pool_qc_features_v0.csv"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--partitions", default="")
    parser.add_argument("--policies", default="")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--flush-every", type=int, default=10)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_quality_raw_v0.jsonl"))
    parser.add_argument("--labels-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_quality_labels_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_qc_calibration_summary_v0.csv"))
    args = parser.parse_args()
    existing = load_jsonl(args.raw_output)
    partitions = {item.strip() for item in args.partitions.split(",") if item.strip()} or None
    policies = {item.strip() for item in args.policies.split(",") if item.strip()} or None
    full_pool = load_jsonl(args.full_pool)
    jobs = load_jsonl(args.jobs)
    new_rows: list[dict[str, Any]] = []
    all_rows = existing.copy()
    features = list(csv.DictReader(args.features.open("r", encoding="utf-8", newline=""))) if args.features.exists() else []
    for row in iter_job_rows(
        full_pool,
        jobs,
        existing,
        args.base_url,
        args.model,
        args.max_tokens,
        args.timeout,
        args.stable_word_limit,
        partitions=partitions,
        policies=policies,
        max_jobs=args.max_jobs or None,
    ):
        write_jsonl(args.raw_output, [row], append=True)
        new_rows.append(row)
        all_rows.append(row)
        if args.flush_every > 0 and len(new_rows) % args.flush_every == 0:
            labels = build_labels(all_rows, features)
            write_csv(args.labels_output, labels, LABEL_FIELDS)
            write_csv(args.summary_output, summarize_labels(labels), SUMMARY_FIELDS)
    labels = build_labels(all_rows, features)
    write_csv(args.labels_output, labels, LABEL_FIELDS)
    write_csv(args.summary_output, summarize_labels(labels), SUMMARY_FIELDS)
    print(f"new_rows={len(new_rows)} total_rows={len(all_rows)} paired_labels={len(labels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
