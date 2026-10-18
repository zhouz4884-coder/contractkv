#!/usr/bin/env python3
"""Run Phase 12B concurrent canonical-slot prefix-cache replay."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from scripts.phase12_prefix_cache_ab import (
    approximate_prompt_tokens,
    percentile,
    quality_sanity,
    send_chat_stream,
)


LAYOUTS = ["raw-order", "canonical-slot", "canonical-slot-shuffled", "cold-raw"]
SOURCE_ORDER = ["RULER", "LongBench", "RepoBench"]
DEFAULT_SLO_BUCKETS = [100.0, 200.0, 500.0, 700.0, 1000.0]

RAW_FIELDS = [
    "layout",
    "prefix_cache_enabled",
    "dataset",
    "task",
    "sample_id",
    "repeat_id",
    "concurrency",
    "batch_id",
    "request_id",
    "success",
    "quality_sanity",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "batch_wall_time_ms",
    "prompt_tokens",
    "cached_tokens",
    "cached_tokens_observable",
    "output_tokens",
    "output_text",
    "error_type",
    "error_message",
    "answer_marker",
    "position_policy",
    "notes",
]

SUMMARY_FIELDS = [
    "layout",
    "prefix_cache_enabled",
    "concurrency",
    "slo_ttft_ms",
    "total_requests",
    "completed_requests",
    "completion_rate",
    "quality_sanity_rate",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "mean_total_latency_ms",
    "p95_total_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "mean_prompt_tokens",
    "cached_tokens_observable",
    "mean_cached_tokens",
    "ttft_reduction_vs_raw_pct",
    "p95_ttft_reduction_vs_raw_pct",
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


def _safe_id(text: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text))[:80]


def _segment_text(sample: dict[str, Any], stable_word_limit: int, shuffled: bool = False) -> str:
    context_segments = [
        segment
        for segment in sample.get("segments", [])
        if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}
    ]
    if shuffled:
        context_segments = list(reversed(context_segments))
    text = "\n\n".join(f"[{segment.get('type', 'CONTEXT')}]\n{segment.get('text', '')}" for segment in context_segments)
    words = text.split()
    if stable_word_limit > 0 and len(words) > stable_word_limit:
        text = " ".join(words[:stable_word_limit])
    return text


def _query_text(sample: dict[str, Any]) -> str:
    for segment in sample.get("segments", []):
        if segment.get("type") == "USER_QUERY":
            return str(segment.get("text", ""))
    return "Answer the benchmark query from the context."


def select_mixed_workload(samples: list[dict[str, Any]], cases_per_source: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for dataset in SOURCE_ORDER:
        count = 0
        for sample in samples:
            if sample.get("dataset") != dataset:
                continue
            selected.append(sample)
            count += 1
            if count >= cases_per_source:
                break
    return selected


def build_concurrent_prompt_case(
    sample: dict[str, Any],
    layout: str,
    repeat_id: int = 0,
    stable_word_limit: int = 2200,
) -> dict[str, Any]:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    marker = f"P12B_{repeat_id}"
    shuffled = layout == "canonical-slot-shuffled"
    stable = _segment_text(sample, stable_word_limit, shuffled=shuffled)
    stable = stable + f"\n\n[PHASE12B_MARKER]\nThe required replay marker is {marker}."
    system = "/no_think You answer with only the requested marker."
    query1 = "Warm the stable context. Reply with the required replay marker only."
    query2 = "Using the stable context, reply with the required replay marker only."
    tool_obs = f"[TOOL_OBS_DYNAMIC]\nDynamic tool observation for replay {repeat_id}: status=ok; do not change the marker."
    stable_block = f"[STABLE_CONTEXT]\n{stable}"
    turn1_user = f"{stable_block}\n[QUERY_1]\n{query1}"
    if layout in {"canonical-slot", "canonical-slot-shuffled"}:
        turn2_user = f"{stable_block}\n{tool_obs}\n[QUERY_2]\n{query2}"
        position_policy = "canonical_slot_same_prefix" if layout == "canonical-slot" else "canonical_slot_shuffled_sanity"
    else:
        turn2_user = f"{tool_obs}\n{stable_block}\n[QUERY_2]\n{query2}"
        position_policy = "raw_order_middle_insert" if layout == "raw-order" else "cold_raw_prefix_off"
    turn1_messages = [{"role": "system", "content": system}, {"role": "user", "content": turn1_user}]
    turn2_messages = [{"role": "system", "content": system}, {"role": "user", "content": turn2_user}]
    return {
        "layout": layout,
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "repeat_id": repeat_id,
        "answer_marker": marker,
        "expected_answer": marker,
        "turn1_messages": turn1_messages,
        "turn2_messages": turn2_messages,
        "position_policy": position_policy,
        "prompt_tokens": approximate_prompt_tokens(turn2_messages),
    }


def _run_one_turn2(
    base_url: str,
    model: str,
    case: dict[str, Any],
    layout: str,
    prefix_cache_enabled: bool,
    concurrency: int,
    batch_id: str,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    result = send_chat_stream(
        base_url,
        model,
        case["turn2_messages"],
        max_tokens,
        timeout,
        f"{layout}-{case['dataset']}-{case['sample_id']}-c{concurrency}",
    )
    result.update(
        {
            "layout": layout,
            "prefix_cache_enabled": prefix_cache_enabled,
            "dataset": case["dataset"],
            "task": case["task"],
            "sample_id": case["sample_id"],
            "repeat_id": case["repeat_id"],
            "concurrency": concurrency,
            "batch_id": batch_id,
            "quality_sanity": quality_sanity(result.get("output_text", ""), case["expected_answer"]),
            "prompt_tokens": case["prompt_tokens"],
            "answer_marker": case["answer_marker"],
            "position_policy": case["position_policy"],
            "notes": "cached_tokens blank means vLLM/OpenAI stream did not expose cached-token usage; do not infer hit rate from it.",
        }
    )
    return result


def run_concurrent_replay(
    samples: list[dict[str, Any]],
    base_url: str,
    model: str,
    layouts: list[str],
    concurrency_levels: list[int],
    cases_per_source: int,
    stable_word_limit: int,
    max_tokens: int,
    timeout: float,
    prefix_cache_enabled: bool,
) -> list[dict[str, Any]]:
    workload = select_mixed_workload(samples, cases_per_source)
    rows: list[dict[str, Any]] = []
    for layout in layouts:
        if layout not in LAYOUTS:
            raise ValueError(f"unknown layout: {layout}")
        cases = [build_concurrent_prompt_case(sample, layout, i, stable_word_limit) for i, sample in enumerate(workload)]
        for concurrency in concurrency_levels:
            for start in range(0, len(cases), concurrency):
                batch = cases[start : start + concurrency]
                batch_id = f"{layout}-pc{int(prefix_cache_enabled)}-c{concurrency}-b{start // concurrency}"
                if prefix_cache_enabled and layout != "cold-raw":
                    for case in batch:
                        send_chat_stream(base_url, model, case["turn1_messages"], max_tokens, timeout, f"{batch_id}-warm-{case['sample_id']}")
                batch_start = time.perf_counter()
                batch_rows: list[dict[str, Any]] = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
                    futures = [
                        pool.submit(
                            _run_one_turn2,
                            base_url,
                            model,
                            case,
                            layout,
                            prefix_cache_enabled,
                            concurrency,
                            batch_id,
                            max_tokens,
                            timeout,
                        )
                        for case in batch
                    ]
                    for future in concurrent.futures.as_completed(futures):
                        batch_rows.append(future.result())
                batch_wall_ms = round((time.perf_counter() - batch_start) * 1000.0, 6)
                for row in batch_rows:
                    row["batch_wall_time_ms"] = batch_wall_ms
                    rows.append({field: row.get(field, "") for field in RAW_FIELDS})
                    print(json.dumps(rows[-1], ensure_ascii=False))
    rows.sort(key=lambda item: (str(item["layout"]), int(item["concurrency"]), str(item["batch_id"]), str(item["sample_id"])))
    return rows


def _batch_wall_seconds(group: list[dict[str, Any]]) -> float:
    by_batch: dict[str, float] = {}
    for row in group:
        by_batch[str(row.get("batch_id", ""))] = max(by_batch.get(str(row.get("batch_id", "")), 0.0), _float(row.get("batch_wall_time_ms")))
    return sum(by_batch.values()) / 1000.0


def aggregate_concurrent_replay(rows: list[dict[str, Any]], slo_buckets_ms: list[float] | None = None) -> list[dict[str, Any]]:
    slo_buckets_ms = slo_buckets_ms or DEFAULT_SLO_BUCKETS
    groups: dict[tuple[str, bool, int], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["layout"]), _bool(row.get("prefix_cache_enabled")), int(row["concurrency"])), []).append(row)

    raw_baselines: dict[int, tuple[float, float]] = {}
    for (layout, prefix_enabled, concurrency), group in groups.items():
        if layout == "raw-order" and prefix_enabled:
            ttft = [_float(row["ttft_ms"]) for row in group if _bool(row["success"])]
            raw_baselines[concurrency] = (statistics.mean(ttft) if ttft else 0.0, percentile(ttft, 0.95))

    out: list[dict[str, Any]] = []
    for (layout, prefix_enabled, concurrency), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row["success"])]
        ttft = [_float(row["ttft_ms"]) for row in successes]
        tpot = [_float(row["tpot_ms"]) for row in successes]
        latency = [_float(row["total_latency_ms"]) for row in successes]
        prompt_tokens = [_float(row.get("prompt_tokens")) for row in group]
        cached_values = [_float(row["cached_tokens"]) for row in group if str(row.get("cached_tokens", "")) != ""]
        wall_seconds = max(_batch_wall_seconds(group), 1e-9)
        mean_ttft = statistics.mean(ttft) if ttft else 0.0
        p95_ttft = percentile(ttft, 0.95)
        raw_mean, raw_p95 = raw_baselines.get(concurrency, (0.0, 0.0))
        for slo in slo_buckets_ms:
            compliant = [row for row in group if _bool(row["success"]) and _float(row["ttft_ms"]) <= float(slo)]
            record = {
                "layout": layout,
                "prefix_cache_enabled": prefix_enabled,
                "concurrency": concurrency,
                "slo_ttft_ms": int(slo) if float(slo).is_integer() else slo,
                "total_requests": len(group),
                "completed_requests": len(successes),
                "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
                "quality_sanity_rate": round(sum(_bool(row.get("quality_sanity")) for row in group) / len(group), 6) if group else 0.0,
                "mean_ttft_ms": round(mean_ttft, 6),
                "p95_ttft_ms": round(p95_ttft, 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
                "p95_tpot_ms": round(percentile(tpot, 0.95), 6),
                "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
                "p95_total_latency_ms": round(percentile(latency, 0.95), 6),
                "slo_compliant_requests": len(compliant),
                "slo_compliant_req_per_sec": round(len(compliant) / wall_seconds, 6),
                "mean_prompt_tokens": round(statistics.mean(prompt_tokens), 6) if prompt_tokens else 0.0,
                "cached_tokens_observable": bool(cached_values),
                "mean_cached_tokens": round(statistics.mean(cached_values), 6) if cached_values else "",
                "ttft_reduction_vs_raw_pct": round((raw_mean - mean_ttft) / raw_mean * 100.0, 6) if layout != "raw-order" and raw_mean > 0 else 0.0,
                "p95_ttft_reduction_vs_raw_pct": round((raw_p95 - p95_ttft) / raw_p95 * 100.0, 6) if layout != "raw-order" and raw_p95 > 0 else 0.0,
                "claim_boundary": "Phase 12B real vLLM replay; prefix hit rate is claimed only if vLLM exposes cached-token stats.",
            }
            out.append({field: record.get(field, "") for field in SUMMARY_FIELDS})
    return out


def _parse_csv_numbers(text: str, cast=float) -> list[Any]:
    return [cast(item.strip()) for item in text.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--layouts", default="raw-order,canonical-slot")
    parser.add_argument("--concurrency-levels", default="1,2,4,6")
    parser.add_argument("--cases-per-source", type=int, default=5)
    parser.add_argument("--stable-word-limit", type=int, default=2200)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--prefix-cache-enabled", action="store_true")
    parser.add_argument("--slo-buckets-ms", default="100,200,500,700,1000")
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12b_concurrent_replay_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12b_concurrent_replay_summary_v0.csv"))
    parser.add_argument("--append-raw", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        rows = load_jsonl(args.raw_output)
    else:
        rows = run_concurrent_replay(
            load_jsonl(args.samples),
            args.base_url,
            args.model,
            [item.strip() for item in args.layouts.split(",") if item.strip()],
            _parse_csv_numbers(args.concurrency_levels, int),
            args.cases_per_source,
            args.stable_word_limit,
            args.max_tokens,
            args.timeout,
            args.prefix_cache_enabled,
        )
        if args.append_raw and args.raw_output.exists():
            rows = load_jsonl(args.raw_output) + rows
        write_jsonl(args.raw_output, rows)

    summary = aggregate_concurrent_replay(rows, _parse_csv_numbers(args.slo_buckets_ms, float))
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"rows={len(rows)} summary_rows={len(summary)}")
    return 0 if rows and all(str(row.get("error_type")) == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
