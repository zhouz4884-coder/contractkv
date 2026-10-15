#!/usr/bin/env python3
"""Fresh policy-aligned quality replay for Phase 13B.

This separates unrestricted canonical-all from the actual ContractKV compiler.
It is a task-sanity replay, not an official LongBench or RepoBench benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_posc_layout_compiler import compile_layout
from scripts.phase12_prefix_cache_ab import approximate_prompt_tokens, send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import compile_for_real_replay, _ordered_text


POLICIES = ["raw-order", "canonical-all", "static-posc", "contractkv-caposc"]
TASKS = ["niah_single_1", "hotpotqa", "qasper", "narrativeqa", "python_repository_completion"]

RAW_FIELDS = [
    "dataset", "task", "sample_id", "policy", "selected_layout_policy", "layout_decision",
    "topological_order", "dependency_edges", "violated_edges", "prompt_hash", "prompt_tokens",
    "success", "score", "contains_answer", "exact_match", "token_f1", "ttft_ms", "tpot_ms",
    "total_latency_ms", "output_tokens", "answer", "output_text", "error_type", "error_message",
    "fresh_generation_id", "claim_boundary",
]

SUMMARY_FIELDS = [
    "dataset", "task", "policy", "num_samples", "successful_samples", "success_rate",
    "mean_score", "raw_mean_score", "quality_drop_vs_raw", "quality_drop_le_0_01",
    "quality_drop_le_0_03", "mean_ttft_ms", "p95_ttft_ms", "violated_edge_rows",
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


def _seg(sample: dict[str, Any], index: int, segment: dict[str, Any], context_ids: list[str]) -> dict[str, Any]:
    sid = f"s{index}"
    stype = str(segment.get("type", "CONTEXT"))
    deps: list[str] = []
    if stype == "SYS_PROMPT":
        deps = []
    elif stype == "USER_QUERY":
        deps = context_ids.copy()
    else:
        deps = ["s0"] if index else []
        if sample.get("dataset") == "RepoBench" and context_ids:
            # Repository context is an ordered supernode.  The dynamic tool
            # observation must stay before it for this conservative case.
            deps = [context_ids[-1]] if context_ids else deps
    return {
        "segment_id": sid,
        "segment_type": stype,
        "text": str(segment.get("text", "")),
        "token_count": int(segment.get("token_count") or max(1, len(str(segment.get("text", "")).split()))),
        "dependencies": deps,
        "volatility": 0.0 if stype in {"SYS_PROMPT", "REPO_CONTEXT", "REPO_IMPORT", "REPO_CLASS", "REPO_FUNCTION", "SYNTHETIC_CONTEXT", "RAG_CHUNK"} else 1.0,
        "cache_stability": 1.0 if stype not in {"TOOL_OBS", "USER_QUERY"} else 0.0,
        "reuse_probability": 1.0 if stype not in {"TOOL_OBS", "USER_QUERY"} else 0.0,
        "boundary_risk": 0.0,
    }


def build_case(sample: dict[str, Any], stable_word_limit: int = 2600) -> dict[str, Any]:
    original = sample.get("segments", [])
    base: list[dict[str, Any]] = []
    context_ids: list[str] = []
    for index, segment in enumerate(original):
        if segment.get("type") in {"SYS_PROMPT", "USER_QUERY"}:
            continue
        text = str(segment.get("text", ""))
        if stable_word_limit > 0:
            remaining = max(0, stable_word_limit - sum(len(str(item.get("text", "")).split()) for item in base))
            text = " ".join(text.split()[:remaining])
        segment = dict(segment)
        segment["text"] = text
        converted = _seg(sample, len(base) + (1 if any(item.get("type") == "SYS_PROMPT" for item in original) else 0), segment, context_ids)
        base.append(converted)
        context_ids.append(converted["segment_id"])
    system = next((item for item in original if item.get("type") == "SYS_PROMPT"), {"text": ""})
    query = next((item for item in original if item.get("type") == "USER_QUERY"), {"text": ""})
    sys_segment = {
        "segment_id": "s0",
        "segment_type": "SYS_PROMPT",
        "text": str(system.get("text", "")),
        "token_count": int(system.get("token_count") or 1),
        "dependencies": [],
        "volatility": 0.0,
        "cache_stability": 1.0,
        "reuse_probability": 1.0,
        "boundary_risk": 0.0,
    }
    # Re-index context IDs after reserving s0 for the system segment.
    for index, segment in enumerate(base, start=1):
        old = segment["segment_id"]
        segment["segment_id"] = f"s{index}"
        segment["dependencies"] = [f"s{int(dep[1:]) + 1}" if dep != "s0" else "s0" for dep in segment.get("dependencies", [])]
        if old in context_ids:
            context_ids[context_ids.index(old)] = segment["segment_id"]
    query_segment = {
        "segment_id": f"s{len(base) + 1}",
        "segment_type": "USER_QUERY",
        "text": str(query.get("text", "")),
        "token_count": int(query.get("token_count") or 1),
        "dependencies": context_ids.copy(),
        "volatility": 1.0,
        "cache_stability": 0.0,
        "reuse_probability": 0.0,
        "boundary_risk": 0.0,
    }
    tool = {
        "segment_id": f"s{len(base) + 2}",
        "segment_type": "TOOL_OBS",
        "text": "[TOOL_OBS_DYNAMIC] No extra evidence is provided.",
        "token_count": 9,
        "dependencies": ["s0"],
        "volatility": 1.0,
        "cache_stability": 0.0,
        "reuse_probability": 0.0,
        "boundary_risk": 0.0,
    }
    # Raw input is intentionally the agent-like middle insertion.  The
    # compiler can move this only when the dependency contract allows it.
    segments = [sys_segment, tool] + base + [query_segment]
    query_segment["dependencies"] = list(dict.fromkeys(query_segment["dependencies"] + [tool["segment_id"]]))
    if sample.get("dataset") == "RepoBench":
        tool["dependencies"] = ["s0"]
        for index, context in enumerate(base):
            context["dependencies"] = ["s0"] if index == 0 else [base[index - 1]["segment_id"]]
        query_segment["dependencies"] = ([base[-1]["segment_id"]] if base else ["s0"]) + [tool["segment_id"]]
    return {
        "trajectory_id": f"{sample.get('dataset', '')}:{sample.get('task', '')}:{sample.get('sample_id', '')}",
        "turn_id": 0,
        "tool_slack_ms": 100,
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "answer": sample.get("answer", ""),
        "segments": segments,
    }


def _messages(case: dict[str, Any], compiled_text: str, policy: str) -> list[dict[str, str]]:
    namespace = f"PHASE13BQ:{case['dataset']}:{case['task']}:{case['sample_id']}:{policy}"
    system = "/no_think Answer the task using only the provided context. Return the shortest correct answer or code completion."
    return [{"role": "system", "content": namespace + "\n" + system}, {"role": "user", "content": compiled_text}]


def _compile(policy: str, case: dict[str, Any], ledger: SegmentPrefixLedger) -> dict[str, Any]:
    if policy == "contractkv-caposc":
        return compile_for_real_replay("cache-aware-posc", case, ledger)
    if policy == "static-posc":
        return compile_layout(case["segments"], policy="posc")
    return compile_layout(case["segments"], policy=policy)


def run(samples: list[dict[str, Any]], base_url: str, model: str, samples_per_task: int, max_tokens: int, timeout: float, stable_word_limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for task in TASKS:
        selected.extend([item for item in samples if item.get("task") == task][:samples_per_task])
    cases = [build_case(sample, stable_word_limit=stable_word_limit) for sample in selected]
    ledgers = {policy: SegmentPrefixLedger() for policy in POLICIES}
    rows: list[dict[str, Any]] = []
    for case in cases:
        for policy in POLICIES:
            started = time.perf_counter()
            compiled = _compile(policy, case, ledgers[policy])
            compile_ms = (time.perf_counter() - started) * 1000.0
            text = _ordered_text(compiled["topological_order"], case["segments"])
            prompt_hash = hashlib.sha256(json.dumps(_messages(case, text, policy), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
            result = send_chat_stream(base_url, model, _messages(case, text, policy), max_tokens, timeout, f"phase13bq-{case['dataset']}-{case['task']}-{case['sample_id']}-{policy}")
            scores = score_answer(result.get("output_text", ""), case["answer"], case["dataset"])
            row = {
                "dataset": case["dataset"], "task": case["task"], "sample_id": case["sample_id"], "policy": policy,
                "selected_layout_policy": compiled.get("selected_policy", policy), "layout_decision": compiled.get("layout_decision", ""),
                "topological_order": json.dumps(compiled.get("topological_order", [])),
                "dependency_edges": json.dumps(compiled.get("dependency_edges", [])),
                "violated_edges": json.dumps(compiled.get("violated_edges", [])), "prompt_hash": prompt_hash,
                "prompt_tokens": approximate_prompt_tokens(_messages(case, text, policy)), "success": result.get("success", False),
                **scores, "ttft_ms": result.get("ttft_ms", 0.0), "tpot_ms": result.get("tpot_ms", 0.0),
                "total_latency_ms": result.get("total_latency_ms", 0.0), "output_tokens": result.get("output_tokens", 0),
                "answer": case["answer"], "output_text": result.get("output_text", ""), "error_type": result.get("error_type", ""),
                "error_message": result.get("error_message", ""), "fresh_generation_id": result.get("request_id", ""),
                "claim_boundary": f"Fresh Qwen3-8B task sanity; compiler_ms={compile_ms:.6f}; not official benchmark scoring.",
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            if policy == "contractkv-caposc":
                ledgers[policy].update(case["dataset"] + ":" + case["task"] + ":" + case["sample_id"], 0, case["segments"], compiled["topological_order"], policy=policy)
    return rows


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["dataset"]), str(row["task"]), str(row["policy"])), []).append(row)
    baseline: dict[tuple[str, str], float] = {}
    for (dataset, task, policy), group in grouped.items():
        if policy == "raw-order":
            values = [_float(row["score"]) for row in group if str(row["success"]).lower() == "true"]
            baseline[(dataset, task)] = sum(values) / len(values) if values else 0.0
    output: list[dict[str, Any]] = []
    for (dataset, task, policy), group in sorted(grouped.items()):
        good = [row for row in group if str(row["success"]).lower() == "true"]
        values = [_float(row["score"]) for row in good]
        mean = sum(values) / len(values) if values else 0.0
        raw = baseline.get((dataset, task), mean)
        drop = max(0.0, raw - mean) if policy != "raw-order" else 0.0
        ttfts = sorted(_float(row["ttft_ms"]) for row in good)
        p95 = ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.95))] if ttfts else 0.0
        record = {
            "dataset": dataset, "task": task, "policy": policy, "num_samples": len(group), "successful_samples": len(good),
            "success_rate": round(len(good) / len(group), 6) if group else 0.0, "mean_score": round(mean, 6),
            "raw_mean_score": round(raw, 6), "quality_drop_vs_raw": round(drop, 6), "quality_drop_le_0_01": drop <= 0.01,
            "quality_drop_le_0_03": drop <= 0.03, "mean_ttft_ms": round(sum(ttfts) / len(ttfts), 6) if ttfts else 0.0,
            "p95_ttft_ms": round(p95, 6), "violated_edge_rows": sum(bool(json.loads(row["violated_edges"])) for row in group),
            "claim_boundary": "Fresh Qwen3-8B task sanity, not official LongBench or RepoBench scoring.",
        }
        output.append({field: record.get(field, "") for field in SUMMARY_FIELDS})
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--samples-per-task", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--raw-output", type=Path, default=Path("results/end_to_end/phase13bq_fresh_quality_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase13bq_fresh_quality_summary_v0.csv"))
    args = parser.parse_args()
    rows = run(load_jsonl(args.samples), args.base_url, args.model, args.samples_per_task, args.max_tokens, args.timeout, args.stable_word_limit)
    write_jsonl(args.raw_output, rows)
    write_csv(args.summary_output, summarize(rows), SUMMARY_FIELDS)
    print(f"fresh_quality_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
