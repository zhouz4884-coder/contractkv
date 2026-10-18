#!/usr/bin/env python3
"""Untouched task-bearing canary certification and future-turn replay."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, compile_static_policy
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_metrics

RAW_FIELDS = [
    "session_id", "source_group_id", "dataset", "task", "sample_id", "turn_id",
    "certificate_issued", "certificate_active", "certificate_revoked", "certificate_type", "output_contract_match", "deployed_policy",
    "raw_request_id", "candidate_request_id", "raw_success", "candidate_success",
    "raw_score", "candidate_score", "quality_drop", "future_contract_match",
    "raw_ttft_ms", "candidate_ttft_ms", "deployed_ttft_ms", "deployed_tpot_ms",
    "deployed_latency_ms", "raw_new_prefill_tokens", "deployed_new_prefill_tokens", "candidate_new_prefill_tokens",
    "candidate_selected_layout", "violated_edges", "shadow_runtime_ms",
    "hidden_at_100ms", "hidden_at_500ms", "hidden_at_2000ms", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized_text(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    return " ".join(text.lower().split())


def ast_key(text: str) -> str | None:
    cleaned = re.sub(r"^```(?:python)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return ast.dump(ast.parse(cleaned), include_attributes=False)
    except SyntaxError:
        return None


def output_contract(dataset: str, task: str, left: str, right: str, answer: Any) -> tuple[bool, str]:
    if dataset == "RepoBench":
        left_ast, right_ast = ast_key(left), ast_key(right)
        if left_ast is not None and right_ast is not None:
            return left_ast == right_ast, "python_ast_equivalence"
        return normalized_text(left) == normalized_text(right), "exact_code_fallback"
    if dataset == "RULER":
        marker = normalized_text(str(answer))
        return marker in normalized_text(left) and marker in normalized_text(right), "normalized_extractive_answer"
    # Open document answers remain strict and fail closed.
    return normalized_text(left) == normalized_text(right), "strict_normalized_output"


def select_sessions(samples: list[dict[str, Any]], per_family: int) -> list[dict[str, Any]]:
    families = {
        "qasper": lambda row: row.get("dataset") == "LongBench" and row.get("task") == "qasper",
        "repobench": lambda row: row.get("dataset") == "RepoBench",
        "ruler": lambda row: row.get("dataset") == "RULER",
    }
    selected: list[dict[str, Any]] = []
    for family, predicate in families.items():
        candidates = [
            row for row in samples
            if predicate(row) and row.get("metadata", {}).get("phase14_partition") == "live_serving"
        ]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"phase15d:{family}:{row.get('metadata', {}).get('source_group_id')}:{row.get('sample_id')}".encode()
        ).hexdigest())
        seen_groups: set[str] = set()
        family_rows = []
        for row in candidates:
            group = str(row.get("metadata", {}).get("source_group_id", ""))
            if not group or group in seen_groups:
                continue
            seen_groups.add(group)
            family_rows.append(row)
            if len(family_rows) == per_family:
                break
        if len(family_rows) != per_family:
            raise ValueError(f"insufficient untouched source groups for {family}: {len(family_rows)}")
        selected.extend(family_rows)
    return selected


def turn_case(sample: dict[str, Any], turn_id: int, stable_word_limit: int) -> dict[str, Any]:
    case = build_case(sample, stable_word_limit=stable_word_limit)
    case["turn_id"] = turn_id
    for segment in case["segments"]:
        if segment.get("segment_type") == "TOOL_OBS":
            segment["text"] = f"[TOOL_OBS_DYNAMIC] turn={turn_id}; no extra evidence is provided."
    return case


def messages(case: dict[str, Any], order: list[str]) -> list[dict[str, str]]:
    result = quality_messages(case, _ordered_text(order, case["segments"]))
    result[0]["content"] = f"[PHASE15D:{case['trajectory_id']}]\n" + result[0]["content"]
    return result


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    samples = select_sessions(load_jsonl(args.full_pool), args.sessions_per_family)
    rows: list[dict[str, Any]] = []
    candidate_ledger = SegmentPrefixLedger()
    for session_index, sample in enumerate(samples):
        session_id = f"{sample['dataset']}:{sample['task']}:{sample['sample_id']}"
        certificate = False
        certificate_active = False
        certificate_type = "not_evaluated"
        for turn in range(args.turns):
            case = turn_case(sample, turn, args.stable_word_limit)
            raw = compile_static_policy(case["segments"], "raw-order")
            candidate = cache_aware_posc_compile(
                case["segments"], candidate_ledger, session_id, turn, args.tool_slack_ms,
            )
            raw_result = send_chat_stream(
                args.base_url, args.model, messages(case, raw["topological_order"]),
                args.max_tokens, args.timeout, f"phase15d-{session_index}-{turn}-raw",
            )
            candidate_result = send_chat_stream(
                args.base_url, args.model, messages(case, candidate["topological_order"]),
                args.max_tokens, args.timeout, f"phase15d-{session_index}-{turn}-candidate",
            )
            raw_scores = score_answer(raw_result.get("output_text", ""), sample.get("answer", ""), str(sample.get("dataset", "")))
            candidate_scores = score_answer(candidate_result.get("output_text", ""), sample.get("answer", ""), str(sample.get("dataset", "")))
            contract_match, contract_type = output_contract(
                str(sample.get("dataset", "")), str(sample.get("task", "")),
                str(raw_result.get("output_text", "")), str(candidate_result.get("output_text", "")),
                sample.get("answer", ""),
            )
            if turn == 0:
                certificate = bool(
                    raw_result.get("success") and candidate_result.get("success")
                    and contract_match and not candidate.get("violated_edges")
                )
                certificate_active = certificate
                certificate_type = contract_type if certificate else "raw_fallback"
            active_before = certificate_active
            deployed = candidate_result if active_before else raw_result
            revoked = bool(turn > 0 and active_before and not contract_match)
            rows.append({
                "session_id": session_id,
                "source_group_id": sample.get("metadata", {}).get("source_group_id", ""),
                "dataset": sample.get("dataset", ""), "task": sample.get("task", ""),
                "sample_id": sample.get("sample_id", ""), "turn_id": turn,
                "certificate_issued": certificate, "certificate_active": active_before,
                "certificate_revoked": revoked, "certificate_type": certificate_type,
                "output_contract_match": contract_match,
                "deployed_policy": "contractkv-caposc" if active_before else "raw-order",
                "raw_request_id": raw_result.get("request_id", ""),
                "candidate_request_id": candidate_result.get("request_id", ""),
                "raw_success": raw_result.get("success", False),
                "candidate_success": candidate_result.get("success", False),
                "raw_score": raw_scores.get("score", 0), "candidate_score": candidate_scores.get("score", 0),
                "quality_drop": max(0.0, float(raw_scores.get("score", 0)) - float(candidate_scores.get("score", 0))),
                "future_contract_match": contract_match if turn > 0 and certificate else "",
                "raw_ttft_ms": raw_result.get("ttft_ms", 0), "candidate_ttft_ms": candidate_result.get("ttft_ms", 0),
                "deployed_ttft_ms": deployed.get("ttft_ms", 0), "deployed_tpot_ms": deployed.get("tpot_ms", 0),
                "deployed_latency_ms": deployed.get("total_latency_ms", 0),
                "candidate_selected_layout": candidate.get("selected_policy", ""),
                "violated_edges": json.dumps(candidate.get("violated_edges", [])),
                "shadow_runtime_ms": candidate_result.get("total_latency_ms", 0),
                "hidden_at_100ms": float(candidate_result.get("total_latency_ms", 0)) <= 100,
                "hidden_at_500ms": float(candidate_result.get("total_latency_ms", 0)) <= 500,
                "hidden_at_2000ms": float(candidate_result.get("total_latency_ms", 0)) <= 2000,
                "claim_boundary": "Fresh untouched task-bearing canary plus future raw shadow; task-sanity metrics, not full official benchmark scoring.",
            })
            if revoked:
                certificate_active = False
            candidate_ledger.update(session_id, turn, case["segments"], candidate["topological_order"], policy="cache-aware-posc")
            args.raw_output.parent.mkdir(parents=True, exist_ok=True)
            args.raw_output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return rows


def join_metrics(rows: list[dict[str, Any]], events_path: Path) -> None:
    if not events_path.exists():
        return
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = {str(row.get("request_id")): row for row in summarize_metrics(events)}
    for row in rows:
        deployed_id = row["candidate_request_id"] if row["deployed_policy"] == "contractkv-caposc" else row["raw_request_id"]
        deployed = metrics.get(str(deployed_id), {})
        raw = metrics.get(str(row["raw_request_id"]), {})
        candidate = metrics.get(str(row["candidate_request_id"]), {})
        row["raw_new_prefill_tokens"] = raw.get("new_prefill_tokens", "")
        row["deployed_new_prefill_tokens"] = deployed.get("new_prefill_tokens", "")
        row["candidate_new_prefill_tokens"] = candidate.get("new_prefill_tokens", "")


def wilson_upper(failures: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 1.0
    p = failures / total
    denominator = 1 + z * z / total
    return min(1.0, (p + z*z/(2*total) + z*((p*(1-p)+z*z/(4*total))/total)**.5) / denominator)


def apply_revoke_policy(rows: list[dict[str, Any]]) -> None:
    """Reconstruct fail-closed deployment state from stored shadow outcomes."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["session_id"])].append(row)
    for group in grouped.values():
        group.sort(key=lambda row: int(row["turn_id"]))
        issued = bool(group[0].get("certificate_issued"))
        active = issued
        for row in group:
            row["certificate_issued"] = issued
            row["certificate_active"] = active
            row["deployed_policy"] = "contractkv-caposc" if active else "raw-order"
            revoked = bool(int(row["turn_id"]) > 0 and active and not bool(row.get("output_contract_match")))
            row["certificate_revoked"] = revoked
            if revoked:
                active = False


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    apply_revoke_policy(rows)
    sessions = {row["session_id"] for row in rows}
    certified_sessions = {row["session_id"] for row in rows if int(row["turn_id"]) == 0 and row["certificate_issued"]}
    future = [row for row in rows if int(row["turn_id"]) > 0 and row["session_id"] in certified_sessions]
    mismatches = sum(not bool(row["future_contract_match"]) for row in future)
    deployed = [row for row in rows if row["raw_success"] and row["candidate_success"]]
    warm = [row for row in deployed if int(row["turn_id"]) > 0]
    canaries = [row for row in rows if int(row["turn_id"]) == 0]
    for row in deployed:
        use_candidate = row["deployed_policy"] == "contractkv-caposc"
        row["deployed_ttft_ms"] = row["candidate_ttft_ms"] if use_candidate else row["raw_ttft_ms"]
        row["deployed_new_prefill_tokens"] = row["candidate_new_prefill_tokens"] if use_candidate else row["raw_new_prefill_tokens"]
    raw_warm_ttft = [float(row["raw_ttft_ms"]) for row in warm]
    deployed_warm_ttft = [float(row["deployed_ttft_ms"]) for row in warm]
    raw_prefill = [float(row["raw_new_prefill_tokens"] or 0) for row in warm]
    deployed_prefill = [float(row["deployed_new_prefill_tokens"] or 0) for row in warm]
    summary = {
        "sessions": len(sessions), "future_pairs": len(future),
        "certificate_issue_rate": len(certified_sessions) / len(sessions) if sessions else 0.0,
        "future_mismatch_rate": mismatches / len(future) if future else 0.0,
        "future_mismatch_wilson95_upper": wilson_upper(mismatches, len(future)),
        "certificate_revocations": sum(bool(row.get("certificate_revoked")) for row in rows),
        "mean_quality_drop": statistics.mean(float(row["quality_drop"]) for row in future) if future else 0.0,
        "max_quality_drop": max((float(row["quality_drop"]) for row in future), default=0.0),
        "mean_deployed_ttft_ms": statistics.mean(float(row["deployed_ttft_ms"]) for row in deployed),
        "p95_deployed_ttft_ms": percentile([float(row["deployed_ttft_ms"]) for row in deployed], .95),
        "mean_deployed_new_prefill_tokens": statistics.mean(float(row["deployed_new_prefill_tokens"] or 0) for row in deployed),
        "warm_raw_mean_ttft_ms": statistics.mean(raw_warm_ttft),
        "warm_deployed_mean_ttft_ms": statistics.mean(deployed_warm_ttft),
        "warm_ttft_reduction_fraction": 1 - statistics.mean(deployed_warm_ttft) / statistics.mean(raw_warm_ttft),
        "warm_raw_mean_new_prefill_tokens": statistics.mean(raw_prefill),
        "warm_deployed_mean_new_prefill_tokens": statistics.mean(deployed_prefill),
        "warm_new_prefill_reduction_fraction": 1 - statistics.mean(deployed_prefill) / statistics.mean(raw_prefill),
        "hidden_fraction_100ms": statistics.mean(bool(row["hidden_at_100ms"]) for row in canaries),
        "hidden_fraction_500ms": statistics.mean(bool(row["hidden_at_500ms"]) for row in canaries),
        "hidden_fraction_2000ms": statistics.mean(bool(row["hidden_at_2000ms"]) for row in canaries),
        "violated_edge_rows": sum(bool(json.loads(row["violated_edges"])) for row in rows),
        "claim_boundary": "Untouched live-serving split with actual Qwen3-8B canary/future outputs; not integrated teacher forcing inside vLLM and not full official benchmark scoring.",
    }
    return [summary]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--sessions-per-family", type=int, default=20)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tool-slack-ms", type=float, default=500)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--postprocess-existing", action="store_true")
    args = parser.parse_args()
    rows = load_jsonl(args.raw_output) if args.postprocess_existing else run(args)
    join_metrics(rows, args.metrics_events)
    apply_revoke_policy(rows)
    write_csv(args.raw_output.with_suffix(".csv"), rows, RAW_FIELDS)
    write_csv(args.summary_output, summarize(rows))
    print(json.dumps(summarize(rows)[0], indent=2))
    return 0 if len(rows) == args.sessions_per_family * 3 * args.turns else 1


if __name__ == "__main__":
    raise SystemExit(main())
