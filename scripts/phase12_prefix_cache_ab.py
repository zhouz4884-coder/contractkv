#!/usr/bin/env python3
"""Run Phase 12A real vLLM prefix-cache A/B prompt layout evaluation."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any


LAYOUTS = ["raw-order", "canonical-slot", "cold-raw"]

RAW_FIELDS = [
    "layout",
    "repeat_id",
    "request_id",
    "success",
    "quality_sanity",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "prompt_tokens",
    "cached_tokens",
    "cached_tokens_observable",
    "finish_reason",
    "output_tokens",
    "output_text",
    "error_type",
    "error_message",
    "answer_marker",
    "position_policy",
    "server_log_path",
    "notes",
]

SUMMARY_FIELDS = [
    "layout",
    "num_requests",
    "success_rate",
    "quality_sanity_rate",
    "slo_ttft_ms",
    "slo_compliant_rate",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "p95_tpot_ms",
    "mean_total_latency_ms",
    "mean_prompt_tokens",
    "cached_tokens_observable",
    "mean_cached_tokens",
    "ttft_reduction_vs_raw_pct",
    "p95_ttft_reduction_vs_raw_pct",
    "claim_boundary",
]


def approximate_prompt_tokens(messages: list[dict[str, str]]) -> int:
    text = "\n".join(str(message.get("content", "")) for message in messages)
    return len(text.split())


def _stable_context(stable_words: int, marker: str) -> str:
    chunk = (
        "repository module cache lifecycle segment contract scheduler "
        "prefix block table stable context "
    ).split()
    words = (chunk * ((stable_words // len(chunk)) + 2))[:stable_words]
    middle = max(1, len(words) // 2)
    words.insert(middle, f"The required phase twelve marker is {marker}.")
    return " ".join(words)


def build_phase12_prompt_case(layout: str, stable_words: int = 2500, repeat_index: int = 0) -> dict[str, Any]:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout: {layout}")
    marker = f"PHASE12_MARKER_{repeat_index}"
    stable = _stable_context(stable_words, marker)
    system = "/no_think You answer with only the requested marker."
    query1 = "Warm the stable context. Reply with the marker only."
    query2 = "Using the stable context, reply with the phase twelve marker only."
    tool_obs = f"[TOOL_OBS] dynamic observation id={repeat_index}: previous tool returned status=ok."
    stable_block = f"[STABLE_CONTEXT]\n{stable}"
    turn1_user = f"{stable_block}\n[QUERY_1]\n{query1}"
    if layout == "canonical-slot":
        turn2_user = f"{stable_block}\n{tool_obs}\n[QUERY_2]\n{query2}"
        position_policy = "canonical_slot_same_prefix"
    else:
        turn2_user = f"{tool_obs}\n{stable_block}\n[QUERY_2]\n{query2}"
        position_policy = "raw_order_middle_insert" if layout == "raw-order" else "cold_raw_no_warm_prefix"
    return {
        "layout": layout,
        "repeat_id": repeat_index,
        "answer_marker": marker,
        "expected_answer": marker,
        "turn1_messages": [{"role": "system", "content": system}, {"role": "user", "content": turn1_user}],
        "turn2_messages": [{"role": "system", "content": system}, {"role": "user", "content": turn2_user}],
        "position_policy": position_policy,
        "prompt_tokens": approximate_prompt_tokens([{"role": "system", "content": system}, {"role": "user", "content": turn2_user}]),
    }


def _iter_sse(response: Any):
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        yield json.loads(payload)


def _extract_cached_tokens(usage: dict[str, Any] | None) -> tuple[str, bool]:
    if not usage:
        return "", False
    details = usage.get("prompt_tokens_details") or usage.get("prompt_token_details") or {}
    for key in ["cached_tokens", "cached_prompt_tokens"]:
        if key in details:
            return str(details[key]), True
        if key in usage:
            return str(usage[key]), True
    return "", False


def chunk_delta_content(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("delta", {}).get("content") or ""


def send_chat_stream(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float,
    request_tag: str,
    seed: int = 14014,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 1,
        "seed": seed,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    chunks: list[dict[str, Any]] = []
    token_times: list[float] = []
    usage: dict[str, Any] | None = None
    finish_reason = ""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for chunk in _iter_sse(response):
                if chunk.get("usage"):
                    usage = chunk.get("usage")
                content = chunk_delta_content(chunk)
                choices = chunk.get("choices") or []
                if choices and choices[0].get("finish_reason"):
                    finish_reason = str(choices[0]["finish_reason"])
                if content:
                    chunks.append(chunk)
                    token_times.append(time.perf_counter())
        ended = time.perf_counter()
        output = "".join(chunk_delta_content(chunk) for chunk in chunks)
        output_tokens = len(chunks)
        first = token_times[0] if token_times else None
        last = token_times[-1] if token_times else None
        cached, observable = _extract_cached_tokens(usage)
        return {
            "request_id": chunks[0].get("id", request_tag) if chunks else request_tag,
            "success": bool(output),
            "ttft_ms": round((first - started) * 1000.0, 6) if first is not None else 0.0,
            "tpot_ms": round(((last - first) * 1000.0 / max(output_tokens - 1, 1)), 6) if first and last and output_tokens > 1 else 0.0,
            "total_latency_ms": round((ended - started) * 1000.0, 6),
            "output_tokens": output_tokens,
            "output_text": output,
            "cached_tokens": cached,
            "cached_tokens_observable": observable,
            "finish_reason": finish_reason,
            "error_type": "none" if output else "bad_output",
            "error_message": "",
        }
    except Exception as exc:
        ended = time.perf_counter()
        return {
            "request_id": request_tag,
            "success": False,
            "ttft_ms": 0.0,
            "tpot_ms": 0.0,
            "total_latency_ms": round((ended - started) * 1000.0, 6),
            "output_tokens": 0,
            "output_text": "",
            "cached_tokens": "",
            "cached_tokens_observable": False,
            "finish_reason": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:300],
        }


def quality_sanity(output_text: str, expected_answer: str) -> bool:
    return expected_answer in output_text


def run_case(
    base_url: str,
    model: str,
    layout: str,
    repeat_id: int,
    stable_words: int,
    max_tokens: int,
    timeout: float,
    server_log_path: str,
) -> dict[str, Any]:
    case = build_phase12_prompt_case(layout, stable_words, repeat_id)
    if layout != "cold-raw":
        send_chat_stream(base_url, model, case["turn1_messages"], max_tokens, timeout, f"{layout}-{repeat_id}-warm")
    result = send_chat_stream(base_url, model, case["turn2_messages"], max_tokens, timeout, f"{layout}-{repeat_id}-turn2")
    result.update(
        {
            "layout": layout,
            "repeat_id": repeat_id,
            "quality_sanity": quality_sanity(result.get("output_text", ""), case["expected_answer"]),
            "prompt_tokens": case["prompt_tokens"],
            "answer_marker": case["answer_marker"],
            "position_policy": case["position_policy"],
            "server_log_path": server_log_path,
            "notes": "cached_tokens blank means vLLM/OpenAI stream did not expose cached-token usage; do not infer hit rate from it.",
        }
    )
    return {field: result.get(field, "") for field in RAW_FIELDS}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * pct
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    frac = index - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def summarize_phase12_rows(rows: list[dict[str, Any]], slo_ttft_ms: float = 2500.0) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["layout"]), []).append(row)
    raw_mean = None
    raw_p95 = None
    if "raw-order" in groups:
        raw_ttft = [_float(row["ttft_ms"]) for row in groups["raw-order"] if _bool(row["success"])]
        raw_mean = statistics.mean(raw_ttft) if raw_ttft else 0.0
        raw_p95 = percentile(raw_ttft, 0.95)
    out = []
    for layout, group in sorted(groups.items()):
        successes = [row for row in group if _bool(row["success"])]
        ttft = [_float(row["ttft_ms"]) for row in successes]
        tpot = [_float(row["tpot_ms"]) for row in successes]
        latency = [_float(row["total_latency_ms"]) for row in successes]
        prompt_tokens = [_float(row["prompt_tokens"]) for row in group]
        cached_values = [_float(row["cached_tokens"]) for row in group if str(row.get("cached_tokens", "")) != ""]
        mean_ttft = statistics.mean(ttft) if ttft else 0.0
        p95_ttft = percentile(ttft, 0.95)
        row = {
            "layout": layout,
            "num_requests": len(group),
            "success_rate": round(len(successes) / len(group), 6) if group else 0.0,
            "quality_sanity_rate": round(sum(_bool(item.get("quality_sanity")) for item in group) / len(group), 6) if group else 0.0,
            "slo_ttft_ms": slo_ttft_ms,
            "slo_compliant_rate": round(sum(_bool(item["success"]) and _float(item["ttft_ms"]) <= slo_ttft_ms for item in group) / len(group), 6) if group else 0.0,
            "mean_ttft_ms": round(mean_ttft, 6),
            "p95_ttft_ms": round(p95_ttft, 6),
            "mean_tpot_ms": round(statistics.mean(tpot), 6) if tpot else 0.0,
            "p95_tpot_ms": round(percentile(tpot, 0.95), 6),
            "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
            "mean_prompt_tokens": round(statistics.mean(prompt_tokens), 6) if prompt_tokens else 0.0,
            "cached_tokens_observable": bool(cached_values),
            "mean_cached_tokens": round(statistics.mean(cached_values), 6) if cached_values else "",
            "ttft_reduction_vs_raw_pct": 0.0,
            "p95_ttft_reduction_vs_raw_pct": 0.0,
            "claim_boundary": "real vLLM prefix-cache A/B; cached-token hit rate only claimed if usage/logs expose it",
        }
        if layout != "raw-order" and raw_mean and raw_mean > 0:
            row["ttft_reduction_vs_raw_pct"] = round((raw_mean - mean_ttft) / raw_mean * 100.0, 6)
        if layout != "raw-order" and raw_p95 and raw_p95 > 0:
            row["p95_ttft_reduction_vs_raw_pct"] = round((raw_p95 - p95_ttft) / raw_p95 * 100.0, 6)
        out.append({field: row.get(field, "") for field in SUMMARY_FIELDS})
    return out


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--layouts", default="raw-order,canonical-slot,cold-raw")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--stable-words", type=int, default=2500)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--slo-ttft-ms", type=float, default=2500.0)
    parser.add_argument("--server-log-path", default="")
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12_prefix_cache_ab_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12_prefix_cache_ab_summary_v0.csv"))
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        rows = load_jsonl(args.raw_output)
    else:
        layouts = [item.strip() for item in args.layouts.split(",") if item.strip()]
        jobs = [(layout, repeat) for layout in layouts for repeat in range(args.repeats)]
        rows = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [
                pool.submit(run_case, args.base_url, args.model, layout, repeat, args.stable_words, args.max_tokens, args.timeout, args.server_log_path)
                for layout, repeat in jobs
            ]
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False))
        rows.sort(key=lambda item: (str(item["layout"]), int(item["repeat_id"])))
        write_jsonl(args.raw_output, rows)
    summary = summarize_phase12_rows(rows, args.slo_ttft_ms)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    print(f"rows={len(rows)} summary_rows={len(summary)}")
    return 0 if rows and all(str(row.get("error_type")) == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
