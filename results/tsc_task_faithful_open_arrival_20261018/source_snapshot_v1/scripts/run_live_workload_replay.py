#!/usr/bin/env python3
"""Run Phase 7 live vLLM workload replay with ContractKV policy sidecar."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_policy_runtime import ContractKVRuntime


POLICY_COPY_MODE = {
    "No-Contract": "no_copy",
    "ContractKV-Indep": "critical_path",
    "ContractKV-Joint": "slack_window",
}

RAW_FIELDS = [
    "request_id",
    "policy",
    "copy_mode",
    "dataset",
    "sample_id",
    "arrival_time_ms",
    "prompt_tokens",
    "tool_slack_ms",
    "slo_ttft_ms",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "controller_overhead_ms",
    "copy_residual_stall_ms",
    "estimated_risk",
    "admitted",
    "slo_violation",
    "quality_budget_violation",
    "error_type",
    "error_message",
]

SUMMARY_FIELDS = [
    "policy",
    "copy_mode",
    "dataset",
    "num_requests",
    "admission_rate",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_tpot_ms",
    "mean_total_latency_ms",
    "quality_budget_violation_rate",
    "slo_violation_rate",
    "mean_copy_residual_stall_ms",
    "mean_controller_overhead_ms",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def compute_copy_stall(copy_ms: float, tool_slack_ms: float, copy_mode: str) -> float:
    if copy_mode == "no_copy":
        return 0.0
    if copy_mode == "slack_window":
        return max(0.0, copy_ms - tool_slack_ms)
    return copy_ms


def load_copy_ms(path: Path, default_size_mb: int = 512) -> float:
    if not path.exists():
        return 0.0
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    exact = [row for row in rows if row.get("mode") == "copy_on_critical_path" and int(float(row.get("kv_size_mb", 0))) == default_size_mb]
    if exact:
        return float(exact[0]["copy_ms"])
    values = [float(row["copy_ms"]) for row in rows if row.get("mode") == "copy_on_critical_path"]
    return statistics.mean(values) if values else 0.0


def build_prompt(trace: dict[str, Any], max_live_chars: int) -> str:
    parts = [f"Dataset: {trace['dataset']}", f"Task: {trace.get('task', '')}", "Segments:"]
    for segment in trace.get("segments", []):
        text = str(segment.get("text", ""))
        parts.append(f"[{segment.get('type', 'UNKNOWN')} tokens={segment.get('token_count', 0)}]\n{text[:max_live_chars]}")
    prompt = "\n\n".join(parts)
    if len(prompt) > max_live_chars:
        prompt = prompt[:max_live_chars] + "\n\n[ContractKV replay prompt truncated for live serving-path measurement.]"
    return prompt


def stream_chat(base_url: str, model: str, prompt: str, max_tokens: int, timeout: float) -> tuple[float, float, float, int, str, str]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    first_token = None
    last_token = None
    output_tokens = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    now = time.perf_counter()
                    if first_token is None:
                        first_token = now
                    last_token = now
                    output_tokens += 1
        ended = time.perf_counter()
        if first_token is None:
            return 0.0, 0.0, (ended - started) * 1000, 0, "bad_output", "no streamed content"
        ttft = (first_token - started) * 1000
        total = (ended - started) * 1000
        tpot = ((last_token - first_token) * 1000 / max(output_tokens - 1, 1)) if output_tokens > 1 and last_token else 0.0
        return ttft, tpot, total, output_tokens, "none", ""
    except Exception as exc:
        ended = time.perf_counter()
        return 0.0, 0.0, (ended - started) * 1000, 0, type(exc).__name__, str(exc)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize_live_replay(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["policy"], row.get("copy_mode", ""), row.get("dataset", ""))
        groups.setdefault(key, []).append(row)
    out = []
    for (policy, copy_mode, dataset), group in sorted(groups.items()):
        ttft = [float(r["ttft_ms"]) for r in group]
        tpot = [float(r["tpot_ms"]) for r in group]
        total = [float(r["total_latency_ms"]) for r in group]
        stall = [float(r["copy_residual_stall_ms"]) for r in group]
        overhead = [float(r.get("controller_overhead_ms", 0.0)) for r in group]
        out.append(
            {
                "policy": policy,
                "copy_mode": copy_mode,
                "dataset": dataset,
                "num_requests": len(group),
                "admission_rate": round(sum(bool(r["admitted"]) for r in group) / len(group), 6),
                "mean_ttft_ms": round(statistics.mean(ttft), 6),
                "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
                "mean_tpot_ms": round(statistics.mean(tpot), 6),
                "mean_total_latency_ms": round(statistics.mean(total), 6),
                "quality_budget_violation_rate": round(sum(bool(r["quality_budget_violation"]) for r in group) / len(group), 6),
                "slo_violation_rate": round(sum(bool(r["slo_violation"]) for r in group) / len(group), 6),
                "mean_copy_residual_stall_ms": round(statistics.mean(stall), 6),
                "mean_controller_overhead_ms": round(statistics.mean(overhead), 6),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--raw-csv", type=Path, default=Path("results/workload/live_replay_raw_v0.csv"))
    parser.add_argument("--summary-csv", type=Path, default=Path("results/workload/live_replay_summary_v0.csv"))
    parser.add_argument("--copy-proxy", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    parser.add_argument("--policies", default="No-Contract,ContractKV-Indep,ContractKV-Joint")
    parser.add_argument("--quality-budget", type=float, default=0.02)
    parser.add_argument("--slo-budget-ms", type=float, default=200.0)
    parser.add_argument("--max-live-chars", type=int, default=4000)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    traces = load_jsonl(args.trace)
    copy_ms = load_copy_ms(args.copy_proxy)
    runtimes = {
        "ContractKV-Indep": ContractKVRuntime(policy="ContractKV-Indep", quality_budget=args.quality_budget, slo_budget_ms=args.slo_budget_ms),
        "ContractKV-Joint": ContractKVRuntime(policy="ContractKV-Joint", quality_budget=args.quality_budget, slo_budget_ms=args.slo_budget_ms),
    }
    rows = []
    for policy in [p for p in args.policies.split(",") if p]:
        for trace in traces:
            copy_mode = POLICY_COPY_MODE[policy]
            started = time.perf_counter()
            if policy == "No-Contract":
                estimated_risk = 0.0
                admitted = True
                controller_ms = 0.0
            else:
                decision, _ = runtimes[policy].decide_sample(
                    {
                        "dataset": trace["dataset"],
                        "task": trace.get("task", ""),
                        "sample_id": trace["sample_id"],
                        "segments": trace["segments"],
                        "total_prompt_tokens": trace["prompt_tokens"],
                        "metadata": {},
                    }
                )
                estimated_risk = float(decision["total_estimated_risk"])
                admitted = bool(decision["admitted"])
                controller_ms = (time.perf_counter() - started) * 1000
            stall = compute_copy_stall(copy_ms, float(trace["tool_slack_ms"]), copy_mode)
            prompt = build_prompt(trace, args.max_live_chars)
            ttft, tpot, total, _, error_type, error_message = stream_chat(args.base_url, args.model, prompt, args.max_tokens, args.timeout)
            observed_ttft = ttft + stall
            slo_violation = observed_ttft > float(trace["slo_ttft_ms"])
            quality_violation = estimated_risk > args.quality_budget
            if error_type != "none":
                admitted = False
                slo_violation = True
            rows.append(
                {
                    "request_id": f"{policy}-{trace['trace_id']}",
                    "policy": policy,
                    "copy_mode": copy_mode,
                    "dataset": trace["dataset"],
                    "sample_id": trace["sample_id"],
                    "arrival_time_ms": trace["arrival_time_ms"],
                    "prompt_tokens": trace["prompt_tokens"],
                    "tool_slack_ms": trace["tool_slack_ms"],
                    "slo_ttft_ms": trace["slo_ttft_ms"],
                    "ttft_ms": round(observed_ttft, 6),
                    "tpot_ms": round(tpot, 6),
                    "total_latency_ms": round(total + stall, 6),
                    "controller_overhead_ms": round(controller_ms, 6),
                    "copy_residual_stall_ms": round(stall, 6),
                    "estimated_risk": round(estimated_risk, 6),
                    "admitted": admitted,
                    "slo_violation": slo_violation,
                    "quality_budget_violation": quality_violation,
                    "error_type": error_type,
                    "error_message": error_message[:200],
                }
            )
    write_csv(args.raw_csv, RAW_FIELDS, rows)
    write_csv(args.summary_csv, SUMMARY_FIELDS, summarize_live_replay(rows))
    print(f"raw_rows={len(rows)}")
    return 0 if all(row["error_type"] == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
