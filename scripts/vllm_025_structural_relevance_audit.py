#!/usr/bin/env python3
"""Run a small real-serving structural relevance audit on vLLM 0.25.1."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any


RAW_FIELDS = [
    "timestamp",
    "runtime_version",
    "fresh_repeat",
    "dataset",
    "task",
    "sample_id",
    "layout",
    "request_id",
    "success",
    "quality_score",
    "quality_pass",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "usage_cached_tokens",
    "metric_prefix_queries",
    "metric_prefix_hits",
    "metric_local_compute_tokens",
    "metric_local_cache_hit_tokens",
    "metric_cached_prompt_tokens",
    "observed_new_prefill_tokens",
    "prefix_hit_ratio",
    "answer",
    "output_text",
    "cache_salt",
    "server_log_path",
    "error_type",
    "error_message",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "runtime_version",
    "dataset",
    "task",
    "layout",
    "fresh_processes",
    "requests",
    "completion_rate",
    "quality_pass_rate",
    "mean_quality_score",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "mean_total_latency_ms",
    "mean_prompt_tokens",
    "mean_prefix_hit_tokens",
    "mean_new_prefill_tokens",
    "mean_prefix_hit_ratio",
    "ttft_reduction_vs_raw_pct",
    "new_prefill_reduction_vs_raw_pct",
    "paired_output_equal_rate",
    "mean_quality_delta_vs_raw",
    "min_quality_delta_vs_raw",
    "claim_boundary",
]


def _normalise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def token_f1(prediction: str, reference: str) -> float:
    pred = _normalise(prediction)
    ref = _normalise(reference)
    if not pred or not ref:
        return float(pred == ref)
    common: dict[str, int] = {}
    for token in pred:
        common[token] = min(pred.count(token), ref.count(token))
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def answer_references(answer: Any) -> list[str]:
    if isinstance(answer, list):
        return [str(item) for item in answer if str(item)]
    if answer is None:
        return []
    return [str(answer)]


def quality_score(dataset: str, output: str, answer: Any) -> float:
    references = answer_references(answer)
    if not references:
        return 0.0
    if dataset == "RULER":
        normalised_output = " ".join(_normalise(output))
        return max(
            float(" ".join(_normalise(reference)) in normalised_output)
            for reference in references
        )
    return max(token_f1(output, reference) for reference in references)


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _metric_key(name: str, labels: str) -> str:
    if name == "vllm:prompt_tokens_by_source_total":
        match = re.search(r'source="([^"]+)"', labels)
        if match:
            return f"{name}:{match.group(1)}"
    return name


def parse_prometheus_metrics(text: str) -> dict[str, float]:
    wanted = {
        "vllm:prefix_cache_queries_total",
        "vllm:prefix_cache_hits_total",
        "vllm:prompt_tokens_cached_total",
        "vllm:prompt_tokens_by_source_total",
    }
    values: dict[str, float] = {}
    pattern = re.compile(
        r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+"
        r"(?P<value>[-+0-9.eE]+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match or match.group("name") not in wanted:
            continue
        key = _metric_key(match.group("name"), match.group("labels") or "")
        values[key] = values.get(key, 0.0) + float(match.group("value"))
    return values


def fetch_metrics(base_url: str, timeout: float) -> dict[str, float]:
    root = base_url.split("/v1", 1)[0].rstrip("/")
    with urllib.request.urlopen(root + "/metrics", timeout=timeout) as response:
        return parse_prometheus_metrics(
            response.read().decode("utf-8", errors="replace")
        )


def _metric_delta(before: dict[str, float], after: dict[str, float], key: str) -> int:
    return max(0, round(after.get(key, 0.0) - before.get(key, 0.0)))


def _iter_sse(response: Any):
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        yield json.loads(payload)


def send_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float,
    request_id: str,
    cache_salt: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 1,
        "seed": 2501,
        "stream": True,
        "stream_options": {"include_usage": True},
        "cache_salt": cache_salt,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
        },
        method="POST",
    )
    started = time.perf_counter()
    token_times: list[float] = []
    output: list[str] = []
    usage: dict[str, Any] = {}
    response_id = request_id
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for chunk in _iter_sse(response):
                response_id = str(chunk.get("id") or response_id)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                content = choices[0].get("delta", {}).get("content") if choices else ""
                if content:
                    token_times.append(time.perf_counter())
                    output.append(content)
        ended = time.perf_counter()
        first = token_times[0] if token_times else None
        last = token_times[-1] if token_times else None
        details = usage.get("prompt_tokens_details") or {}
        return {
            "request_id": response_id,
            "success": bool(output),
            "output_text": "".join(output),
            "ttft_ms": (first - started) * 1000 if first else 0.0,
            "tpot_ms": (
                (last - first) * 1000 / max(len(token_times) - 1, 1)
                if first and last and len(token_times) > 1
                else 0.0
            ),
            "total_latency_ms": (ended - started) * 1000,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or len(output)),
            "usage_cached_tokens": int(details.get("cached_tokens") or 0),
            "error_type": "none" if output else "bad_output",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "request_id": request_id,
            "success": False,
            "output_text": "",
            "ttft_ms": 0.0,
            "tpot_ms": 0.0,
            "total_latency_ms": (time.perf_counter() - started) * 1000,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "usage_cached_tokens": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        }


def _segments(sample: dict[str, Any]) -> tuple[str, str, str]:
    system: list[str] = []
    stable: list[str] = []
    query: list[str] = []
    for segment in sample["segments"]:
        segment_type = str(segment["type"])
        text = str(segment["text"])
        if segment_type == "SYS_PROMPT":
            system.append(text)
        elif segment_type == "USER_QUERY":
            query.append(text)
        else:
            stable.append(text)
    return "\n".join(system), "\n".join(stable), "\n".join(query)


def trim_context_around_answer(
    tokenizer: Any, context: str, answer: str, target_tokens: int
) -> str:
    token_ids = tokenizer.encode(context, add_special_tokens=False)
    if len(token_ids) <= target_tokens:
        return context
    answer_ids = tokenizer.encode(answer, add_special_tokens=False)
    position = -1
    if answer_ids:
        for index in range(len(token_ids) - len(answer_ids) + 1):
            if token_ids[index : index + len(answer_ids)] == answer_ids:
                position = index
                break
    if position < 0:
        start = 0
    else:
        start = max(0, position - target_tokens // 2)
        start = min(start, len(token_ids) - target_tokens)
    return tokenizer.decode(token_ids[start : start + target_tokens])


def build_messages(
    sample: dict[str, Any],
    layout: str,
    repeat: int,
    tokenizer: Any,
    context_target_tokens: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    system, stable, query = _segments(sample)
    references = answer_references(sample.get("answer"))
    answer = references[0] if references else ""
    stable = trim_context_around_answer(
        tokenizer, stable, answer, context_target_tokens
    )
    system_message = (
        "/no_think\n"
        + system
        + "\nAnswer concisely using only information from the supplied context."
    )
    dynamic = (
        f"[TOOL_OBSERVATION]\nRuntime audit observation {repeat}: "
        "the retrieval tool completed successfully."
    )
    warm = [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": f"[STABLE_CONTEXT]\n{stable}\n[WARMUP]\nContext registered.",
        },
    ]
    if layout == "compiled":
        body = (
            f"[STABLE_CONTEXT]\n{stable}\n{dynamic}\n"
            f"[USER_QUERY]\n{query}\n[OUTPUT_CONTRACT]\n"
            "Return only the shortest answer span. Do not explain."
        )
    elif layout == "raw":
        body = (
            f"{dynamic}\n[STABLE_CONTEXT]\n{stable}\n"
            f"[USER_QUERY]\n{query}\n[OUTPUT_CONTRACT]\n"
            "Return only the shortest answer span. Do not explain."
        )
    else:
        raise ValueError(f"unsupported layout: {layout}")
    measured = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": body},
    ]
    return warm, measured


def load_samples(path: Path, cases_per_source: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts = {"RULER": 0, "hotpotqa": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("dataset") == "RULER" and counts["RULER"] < cases_per_source:
            selected.append(row)
            counts["RULER"] += 1
        elif row.get("task") == "hotpotqa" and counts["hotpotqa"] < cases_per_source:
            selected.append(row)
            counts["hotpotqa"] += 1
        if all(value >= cases_per_source for value in counts.values()):
            break
    if any(value < cases_per_source for value in counts.values()):
        raise ValueError(f"insufficient samples: {counts}")
    return selected


def run_audit(args: argparse.Namespace) -> list[dict[str, Any]]:
    from transformers import AutoTokenizer
    import vllm

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = load_samples(args.samples, args.cases_per_source)
    layouts = ["raw", "compiled"]
    if args.fresh_repeat % 2 == 0:
        layouts.reverse()
    rows: list[dict[str, Any]] = []
    for sample in samples:
        for layout in layouts:
            sample_id = str(sample["sample_id"])
            dataset = str(sample["dataset"])
            task = str(sample["task"])
            salt = (
                f"v0251-r{args.fresh_repeat}-{dataset}-{task}-{sample_id}-{layout}"
            )
            warm, measured = build_messages(
                sample,
                layout,
                args.fresh_repeat,
                tokenizer,
                args.context_target_tokens,
            )
            warm_result = send_chat(
                args.base_url,
                args.model,
                warm,
                1,
                args.timeout,
                salt + "-warm",
                salt,
            )
            if not warm_result["success"]:
                result = warm_result
                before = after = {}
            else:
                before = fetch_metrics(args.base_url, args.timeout)
                result = send_chat(
                    args.base_url,
                    args.model,
                    measured,
                    args.max_tokens,
                    args.timeout,
                    salt + "-measured",
                    salt,
                )
                after = fetch_metrics(args.base_url, args.timeout)
            queries = _metric_delta(
                before, after, "vllm:prefix_cache_queries_total"
            )
            hits = _metric_delta(before, after, "vllm:prefix_cache_hits_total")
            local_compute = _metric_delta(
                before,
                after,
                "vllm:prompt_tokens_by_source_total:local_compute",
            )
            local_hit = _metric_delta(
                before,
                after,
                "vllm:prompt_tokens_by_source_total:local_cache_hit",
            )
            cached = _metric_delta(
                before, after, "vllm:prompt_tokens_cached_total"
            )
            observed_new_prefill = local_compute or max(
                0, int(result["prompt_tokens"]) - hits
            )
            answer_value = sample.get("answer")
            references = answer_references(answer_value)
            answer = json.dumps(references, ensure_ascii=False)
            score = quality_score(dataset, str(result["output_text"]), answer_value)
            row = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "runtime_version": vllm.__version__,
                "fresh_repeat": args.fresh_repeat,
                "dataset": dataset,
                "task": task,
                "sample_id": sample_id,
                "layout": layout,
                **result,
                "quality_score": round(score, 6),
                "quality_pass": score >= args.quality_threshold,
                "metric_prefix_queries": queries,
                "metric_prefix_hits": hits,
                "metric_local_compute_tokens": local_compute,
                "metric_local_cache_hit_tokens": local_hit,
                "metric_cached_prompt_tokens": cached,
                "observed_new_prefill_tokens": observed_new_prefill,
                "prefix_hit_ratio": round(hits / queries, 6) if queries else 0.0,
                "answer": answer,
                "cache_salt": salt,
                "server_log_path": args.server_log_path,
                "claim_boundary": (
                    "real vLLM 0.25.1 APC; frozen compiled layout only; "
                    "no online certificate or PSTP"
                ),
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            print(json.dumps(row, ensure_ascii=False))
    return rows


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["dataset"]), str(row["task"]), str(row["layout"]))
        groups.setdefault(key, []).append(row)
    raw_means: dict[tuple[str, str], tuple[float, float]] = {}
    raw_by_pair: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for (dataset, task, layout), group in groups.items():
        if layout != "raw":
            continue
        raw_means[(dataset, task)] = (
            statistics.mean(_as_float(row["ttft_ms"]) for row in group),
            statistics.mean(
                _as_float(row["observed_new_prefill_tokens"]) for row in group
            ),
        )
        for row in group:
            pair_key = (
                str(row["fresh_repeat"]),
                dataset,
                task,
                str(row["sample_id"]),
            )
            raw_by_pair[pair_key] = row
    output: list[dict[str, Any]] = []
    for (dataset, task, layout), group in sorted(groups.items()):
        ttft = [_as_float(row["ttft_ms"]) for row in group if _as_bool(row["success"])]
        new_prefill = [
            _as_float(row["observed_new_prefill_tokens"]) for row in group
        ]
        mean_ttft = statistics.mean(ttft) if ttft else 0.0
        mean_new = statistics.mean(new_prefill) if new_prefill else 0.0
        raw_ttft, raw_new = raw_means.get((dataset, task), (0.0, 0.0))
        paired_rows = []
        if layout == "compiled":
            for row in group:
                pair_key = (
                    str(row["fresh_repeat"]),
                    dataset,
                    task,
                    str(row["sample_id"]),
                )
                if pair_key in raw_by_pair:
                    paired_rows.append((raw_by_pair[pair_key], row))
        quality_deltas = [
            _as_float(candidate["quality_score"]) - _as_float(raw["quality_score"])
            for raw, candidate in paired_rows
        ]
        item = {
            "runtime_version": str(group[0]["runtime_version"]),
            "dataset": dataset,
            "task": task,
            "layout": layout,
            "fresh_processes": len({str(row["fresh_repeat"]) for row in group}),
            "requests": len(group),
            "completion_rate": round(
                sum(_as_bool(row["success"]) for row in group) / len(group), 6
            ),
            "quality_pass_rate": round(
                sum(_as_bool(row["quality_pass"]) for row in group) / len(group), 6
            ),
            "mean_quality_score": round(
                statistics.mean(_as_float(row["quality_score"]) for row in group),
                6,
            ),
            "mean_ttft_ms": round(mean_ttft, 6),
            "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
            "mean_tpot_ms": round(
                statistics.mean(_as_float(row["tpot_ms"]) for row in group), 6
            ),
            "mean_total_latency_ms": round(
                statistics.mean(
                    _as_float(row["total_latency_ms"]) for row in group
                ),
                6,
            ),
            "mean_prompt_tokens": round(
                statistics.mean(_as_float(row["prompt_tokens"]) for row in group),
                6,
            ),
            "mean_prefix_hit_tokens": round(
                statistics.mean(
                    _as_float(row["metric_prefix_hits"]) for row in group
                ),
                6,
            ),
            "mean_new_prefill_tokens": round(mean_new, 6),
            "mean_prefix_hit_ratio": round(
                statistics.mean(_as_float(row["prefix_hit_ratio"]) for row in group),
                6,
            ),
            "ttft_reduction_vs_raw_pct": (
                round((raw_ttft - mean_ttft) / raw_ttft * 100, 6)
                if layout != "raw" and raw_ttft
                else 0.0
            ),
            "new_prefill_reduction_vs_raw_pct": (
                round((raw_new - mean_new) / raw_new * 100, 6)
                if layout != "raw" and raw_new
                else 0.0
            ),
            "paired_output_equal_rate": (
                round(
                    sum(
                        str(raw["output_text"]) == str(candidate["output_text"])
                        for raw, candidate in paired_rows
                    )
                    / len(paired_rows),
                    6,
                )
                if paired_rows
                else ""
            ),
            "mean_quality_delta_vs_raw": (
                round(statistics.mean(quality_deltas), 6) if quality_deltas else ""
            ),
            "min_quality_delta_vs_raw": (
                round(min(quality_deltas), 6) if quality_deltas else ""
            ),
            "claim_boundary": (
                "real vLLM 0.25.1 APC; frozen compiled layout only; "
                "no online certificate or PSTP"
            ),
        }
        output.append({field: item.get(field, "") for field in SUMMARY_FIELDS})
    return output


def read_jsonl_files(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


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
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:9251/v1")
    parser.add_argument("--model", default="qwen3-8b-v0251")
    parser.add_argument("--model-path", required=False, default="")
    parser.add_argument(
        "--samples",
        type=Path,
        default=Path("results/datasets/sample_prompts.jsonl"),
    )
    parser.add_argument("--fresh-repeat", type=int, default=1)
    parser.add_argument("--cases-per-source", type=int, default=5)
    parser.add_argument("--context-target-tokens", type=int, default=18000)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--quality-threshold", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--server-log-path", default="")
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=Path("results/appendix/vllm_025_structural_audit_raw.jsonl"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("results/appendix/vllm_025_structural_audit_summary.csv"),
    )
    parser.add_argument("--summarize-input", type=Path, nargs="*")
    args = parser.parse_args()

    if args.summarize_input:
        rows = read_jsonl_files(args.summarize_input)
    else:
        if not args.model_path:
            parser.error("--model-path is required for a live run")
        rows = run_audit(args)
        write_jsonl(args.raw_output, rows)
    summary = summarize(rows)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    failures = [row for row in rows if not _as_bool(row.get("success"))]
    print(f"rows={len(rows)} summary_rows={len(summary)} failures={len(failures)}")
    return 0 if rows and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
