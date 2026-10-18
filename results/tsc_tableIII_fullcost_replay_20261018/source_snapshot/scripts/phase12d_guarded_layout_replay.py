#!/usr/bin/env python3
"""Run and aggregate Phase 12D guarded POSC layout replay."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any

from scripts.phase12_posc_layout_compiler import compile_layout
from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream


POLICIES = ["raw-order", "canonical-all", "boolean-guarded", "posc", "posc-anchors"]
DEFAULT_SLO_BUCKETS = [100.0, 200.0, 500.0, 700.0, 1000.0]

RAW_FIELDS = [
    "workload",
    "trace_id",
    "case_type",
    "policy",
    "layout_decision",
    "success",
    "quality_score",
    "quality_sanity",
    "ttft_ms",
    "tpot_ms",
    "total_latency_ms",
    "slo_ttft_ms",
    "prompt_tokens",
    "output_tokens",
    "expected_answer",
    "output_text",
    "error_type",
    "error_message",
    "topological_order",
    "violated_edges",
    "canonicalized_tokens",
    "expected_prefix_gain_tokens",
    "structural_anchor_tokens_added",
]

SUMMARY_FIELDS = [
    "workload",
    "policy",
    "slo_ttft_ms",
    "num_requests",
    "completed_requests",
    "completion_rate",
    "quality_score_mean",
    "raw_quality_score_mean",
    "quality_drop_vs_raw",
    "max_quality_drop_flag",
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_total_latency_ms",
    "slo_compliant_requests",
    "slo_compliant_req_per_sec",
    "canonicalized_fraction",
    "guarded_fallback_fraction",
    "mean_canonicalized_tokens",
    "mean_structural_anchor_tokens_added",
    "claim_boundary",
]

QUALITY_FIELDS = [
    "workload",
    "case_type",
    "policy",
    "num_requests",
    "quality_score_mean",
    "raw_quality_score_mean",
    "quality_drop_vs_raw",
    "violated_edge_cases",
    "canonicalized_fraction",
    "mean_canonicalized_tokens",
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


def _messages_for_case(case: dict[str, Any], compiled_text: str) -> list[dict[str, str]]:
    system = "You are a deterministic layout sanity evaluator. Follow dependency-order instructions exactly. /no_think"
    return [{"role": "system", "content": system}, {"role": "user", "content": compiled_text}]


def _score_output(output: str, expected: str, unsafe_answer: str) -> tuple[bool, float]:
    if expected and expected in output:
        return True, 1.0
    if unsafe_answer and unsafe_answer in output:
        return False, 0.0
    return False, 0.0


def run_replay(
    cases: list[dict[str, Any]],
    base_url: str,
    model: str,
    policies: list[str],
    max_tokens: int,
    timeout: float,
    slo_ttft_ms: float,
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        for policy in policies:
            compiled = compile_layout(case["segments"], policy=policy, structural_anchors=(policy == "posc-anchors"))
            result = send_chat_stream(
                base_url,
                model,
                _messages_for_case(case, compiled["compiled_text"]),
                max_tokens,
                timeout,
                f"phase12d-{case['trace_id']}-{policy}",
            )
            quality_sanity, quality_score = _score_output(result.get("output_text", ""), case.get("expected_answer", ""), case.get("unsafe_answer", "ORDER_ERROR"))
            if compiled["violated_edges"]:
                quality_sanity = False
                quality_score = 0.0
            row = {
                "workload": "Mixed-Agent",
                "trace_id": case["trace_id"],
                "case_type": case.get("case_type", ""),
                "policy": policy,
                "layout_decision": compiled["layout_decision"],
                "success": result.get("success", False),
                "quality_score": quality_score,
                "quality_sanity": quality_sanity,
                "ttft_ms": result.get("ttft_ms", 0.0),
                "tpot_ms": result.get("tpot_ms", 0.0),
                "total_latency_ms": result.get("total_latency_ms", 0.0),
                "slo_ttft_ms": slo_ttft_ms,
                "prompt_tokens": sum(int(segment.get("token_count") or 0) for segment in case["segments"]) + int(compiled.get("structural_anchor_tokens_added") or 0),
                "output_tokens": result.get("output_tokens", 0),
                "expected_answer": case.get("expected_answer", ""),
                "output_text": result.get("output_text", ""),
                "error_type": result.get("error_type", ""),
                "error_message": result.get("error_message", ""),
                "topological_order": json.dumps(compiled["topological_order"]),
                "violated_edges": json.dumps(compiled["violated_edges"]),
                "canonicalized_tokens": compiled["canonicalized_tokens"],
                "expected_prefix_gain_tokens": compiled["expected_prefix_gain_tokens"],
                "structural_anchor_tokens_added": compiled["structural_anchor_tokens_added"],
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            print(json.dumps(rows[-1], ensure_ascii=False))
    return rows


def aggregate_phase12d_results(rows: list[dict[str, Any]], slo_buckets_ms: list[float] | None = None) -> list[dict[str, Any]]:
    slo_buckets_ms = slo_buckets_ms or DEFAULT_SLO_BUCKETS
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["workload"]), str(row["policy"])), []).append(row)
    raw_scores: dict[str, float] = {}
    for (workload, policy), group in groups.items():
        if policy == "raw-order":
            scores = [_float(row.get("quality_score")) for row in group if _bool(row.get("success"))]
            raw_scores[workload] = statistics.mean(scores) if scores else 0.0

    out = []
    for (workload, policy), group in sorted(groups.items()):
        successes = [row for row in group if _bool(row.get("success"))]
        scores = [_float(row.get("quality_score")) for row in successes]
        ttft = [_float(row.get("ttft_ms")) for row in successes]
        latency = [_float(row.get("total_latency_ms")) for row in successes]
        raw_score = raw_scores.get(workload, statistics.mean(scores) if scores else 0.0)
        mean_score = statistics.mean(scores) if scores else 0.0
        quality_drop = max(0.0, raw_score - mean_score)
        total_latency_sec = max(sum(latency) / 1000.0, 1e-9)
        canonicalized = [
            row for row in group
            if str(row.get("layout_decision")) in {"partial_canonical", "partial_canonical_anchored"}
        ]
        fallback = [row for row in group if str(row.get("layout_decision")).startswith("raw_order")]
        for slo in slo_buckets_ms:
            compliant = [row for row in group if _bool(row.get("success")) and _float(row.get("ttft_ms")) <= float(slo)]
            record = {
                "workload": workload,
                "policy": policy,
                "slo_ttft_ms": int(slo) if float(slo).is_integer() else slo,
                "num_requests": len(group),
                "completed_requests": len(successes),
                "completion_rate": round(len(successes) / len(group), 6) if group else 0.0,
                "quality_score_mean": round(mean_score, 6),
                "raw_quality_score_mean": round(raw_score, 6),
                "quality_drop_vs_raw": round(quality_drop, 6),
                "max_quality_drop_flag": quality_drop > 0.03,
                "mean_ttft_ms": round(statistics.mean(ttft), 6) if ttft else 0.0,
                "p95_ttft_ms": round(percentile(ttft, 0.95), 6),
                "mean_total_latency_ms": round(statistics.mean(latency), 6) if latency else 0.0,
                "slo_compliant_requests": len(compliant),
                "slo_compliant_req_per_sec": round(len(compliant) / total_latency_sec, 6),
                "canonicalized_fraction": round(len(canonicalized) / len(group), 6) if group else 0.0,
                "guarded_fallback_fraction": round(len(fallback) / len(group), 6) if group else 0.0,
                "mean_canonicalized_tokens": round(statistics.mean(_float(row.get("canonicalized_tokens")) for row in group), 6) if group else 0.0,
                "mean_structural_anchor_tokens_added": round(statistics.mean(_float(row.get("structural_anchor_tokens_added")) for row in group), 6) if group else 0.0,
                "claim_boundary": "Phase 12D mixed-agent sanity; quality is marker/order sanity, not benchmark scoring.",
            }
            out.append({field: record.get(field, "") for field in SUMMARY_FIELDS})
    return out


def aggregate_quality_by_case_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["workload"]), str(row["case_type"]), str(row["policy"])), []).append(row)
    raw_scores: dict[tuple[str, str], float] = {}
    for (workload, case_type, policy), group in groups.items():
        if policy == "raw-order":
            raw_scores[(workload, case_type)] = statistics.mean(_float(row.get("quality_score")) for row in group)
    out = []
    for (workload, case_type, policy), group in sorted(groups.items()):
        mean_quality = statistics.mean(_float(row.get("quality_score")) for row in group)
        raw_quality = raw_scores.get((workload, case_type), mean_quality)
        canonicalized = [
            row for row in group
            if str(row.get("layout_decision")) in {"partial_canonical", "partial_canonical_anchored"}
        ]
        record = {
            "workload": workload,
            "case_type": case_type,
            "policy": policy,
            "num_requests": len(group),
            "quality_score_mean": round(mean_quality, 6),
            "raw_quality_score_mean": round(raw_quality, 6),
            "quality_drop_vs_raw": round(max(0.0, raw_quality - mean_quality), 6),
            "violated_edge_cases": sum(1 for row in group if json.loads(str(row.get("violated_edges", "[]")))),
            "canonicalized_fraction": round(len(canonicalized) / len(group), 6) if group else 0.0,
            "mean_canonicalized_tokens": round(statistics.mean(_float(row.get("canonicalized_tokens")) for row in group), 6) if group else 0.0,
        }
        out.append({field: record.get(field, "") for field in QUALITY_FIELDS})
    return out


def _parse_slos(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("results/prefix_cache/phase12d_mixed_agent_cases_v0.jsonl"))
    parser.add_argument("--base-url")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--policies", default="raw-order,canonical-all,boolean-guarded,posc,posc-anchors")
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--slo-buckets-ms", default="100,200,500,700,1000")
    parser.add_argument("--raw-output", type=Path, default=Path("results/prefix_cache/phase12d_guarded_replay_raw_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/prefix_cache/phase12d_guarded_replay_summary_v0.csv"))
    parser.add_argument("--quality-summary-output", type=Path, default=Path("results/prefix_cache/phase12d_posc_quality_summary_v0.csv"))
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if args.summarize_only:
        rows = load_jsonl(args.raw_output)
    else:
        if not args.base_url:
            raise SystemExit("--base-url is required unless --summarize-only is set")
        rows = run_replay(
            load_jsonl(args.cases),
            args.base_url,
            args.model,
            [item.strip() for item in args.policies.split(",") if item.strip()],
            args.max_tokens,
            args.timeout,
            700.0,
        )
        write_jsonl(args.raw_output, rows)
    summary = aggregate_phase12d_results(rows, _parse_slos(args.slo_buckets_ms))
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    quality_summary = aggregate_quality_by_case_type(rows)
    write_csv(args.quality_summary_output, quality_summary, QUALITY_FIELDS)
    print(f"rows={len(rows)} summary_rows={len(summary)} quality_rows={len(quality_summary)}")
    return 0 if rows and all(str(row.get("error_type")) == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
