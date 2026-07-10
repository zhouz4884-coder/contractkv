#!/usr/bin/env python3
"""Phase 14A: offline opportunity census over five agent workload families."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger, cache_aware_posc_compile, estimate_lcp_tokens
from scripts.phase12_posc_layout_compiler import prefix_max_topological_order, raw_order


FAMILIES = ["code_agent", "rag_agent", "structured_document_qa", "tool_function_agent", "mixed_long_history_agent"]
DISCOURSE_CUES = re.compile(r"(?i)\b(this paper|we propose|we present|our method|our approach|we evaluate|experimental results|baseline|dataset)\b")
HEADING_CUES = re.compile(r"(?im)^\s*(abstract|introduction|background|method|methods|results|discussion|conclusion|related work|experiments?)s?\b")

RAW_FIELDS = [
    "trace_id", "turn_id", "workload_family", "source_dataset", "source_task", "stable_segment_tokens",
    "volatile_segment_tokens", "raw_prefix_reuse_tokens", "best_legal_lcp_tokens", "selected_caposc_lcp_tokens",
    "caposc_expected_prefix_gain", "caposc_regret_tokens",
    "partial_canonical", "hard_order_sensitive", "hard_edge_valid", "adjacency_preservation_ratio",
    "relative_order_edit_distance", "ordered_document_cue_count", "qc_risk_bucket", "qc_decision",
    "raw_fallback", "caposc_selected_policy", "claim_boundary",
]
SUMMARY_FIELDS = [
    "workload_family", "turns", "optimization_opportunity_coverage", "safe_canonicalization_coverage",
    "median_potential_reusable_prefix_gain", "high_risk_fallback_rate", "raw_fallback_rate", "partial_canonical_rate",
    "hard_order_sensitive_fraction", "mean_stable_segment_tokens", "mean_volatile_segment_tokens", "claim_boundary",
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


def _seg(segment_id: str, segment_type: str, text: str, token_count: int, deps: list[str], volatility: float, stability: float) -> dict[str, Any]:
    return {
        "segment_id": segment_id, "segment_type": segment_type, "text": text, "token_count": max(1, int(token_count)),
        "dependencies": deps, "volatility": volatility, "cache_stability": stability, "reuse_probability": stability,
        "boundary_risk": 0.0,
    }


def _source_text(sample: dict[str, Any]) -> tuple[str, int, str, str]:
    context = [segment for segment in sample.get("segments", []) if segment.get("type") not in {"SYS_PROMPT", "USER_QUERY"}]
    text = "\n\n".join(str(segment.get("text", "")) for segment in context)
    tokens = sum(int(segment.get("token_count") or 0) for segment in context)
    query = next((str(segment.get("text", "")) for segment in sample.get("segments", []) if segment.get("type") == "USER_QUERY"), "Answer from context.")
    return text, max(tokens, 1), query, str(sample.get("answer", ""))


def _dataset_turn(sample: dict[str, Any], family: str, turn: int) -> dict[str, Any]:
    text, tokens, query, _ = _source_text(sample)
    trace_id = f"{family}:{sample['sample_id']}"
    sys = _seg("sys", "SYS_PROMPT", "Follow the segment contract and answer from the supplied context. /no_think", 16, [], 0.0, 1.0)
    tool = _seg("tool_obs", "TOOL_OBS", f"Dynamic observation at turn {turn}; no new evidence.", 12, ["sys"], 1.0, 0.0)
    if family == "code_agent":
        # The repository context is an ordered supernode: imports/classes/functions
        # stay internally ordered, but the stable component itself can legally
        # move before a volatile tool observation.
        context = _seg("repo_component", "REPO_CONTEXT", text, tokens, ["sys"], 0.0, 1.0)
        deps = ["repo_component", "tool_obs"]
        source = "RepoBench"
    elif family == "structured_document_qa":
        context = _seg("document_component", "RAG_CHUNK", text, tokens, ["sys"], 0.0, 1.0)
        deps = ["document_component", "tool_obs"]
        source = "LongBench"
    else:
        context = _seg("retrieved_context", "RAG_CHUNK", text, tokens, ["sys"], 0.0, 1.0)
        deps = ["retrieved_context", "tool_obs"]
        source = "LongBench"
    query_segment = _seg("query", "USER_QUERY", query, 24, deps, 0.5, 0.0)
    return {
        "trace_id": trace_id, "turn_id": turn, "workload_family": family, "source_dataset": source,
        "source_task": str(sample.get("task", "")), "segments": [sys, tool, context, query_segment],
    }


def _tool_function_turn(index: int, turn: int) -> dict[str, Any]:
    marker = f"TOOL_AGENT_{index}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Use the stable function schema and tool manual. /no_think", 16, [], 0.0, 1.0),
        _seg("tool_obs", "TOOL_OBS", f"Volatile tool observation for turn {turn}.", 12, ["sys"], 1.0, 0.0),
        _seg("tool_schema", "TOOL_SCHEMA", f"Stable function schema {index}: name, arguments, return type.", 160, ["sys"], 0.0, 1.0),
        _seg("tool_manual", "RAG_CHUNK", f"Stable tool manual {index} documents marker {marker}.", 220, ["sys"], 0.0, 1.0),
        _seg("query", "USER_QUERY", f"Return marker {marker}.", 20, ["tool_schema", "tool_manual", "tool_obs"], 0.5, 0.0),
    ]
    return {"trace_id": f"tool:{index}", "turn_id": turn, "workload_family": "tool_function_agent", "source_dataset": "SyntheticAgentTrace", "source_task": "tool_function", "segments": segments}


def _mixed_history_turn(index: int, turn: int) -> dict[str, Any]:
    segments = [
        _seg("sys", "SYS_PROMPT", "Answer using stable history and current observation. /no_think", 16, [], 0.0, 1.0),
        _seg("tool_obs", "TOOL_OBS", f"Volatile mixed-agent observation at turn {turn}.", 14, ["sys"], 1.0, 0.0),
        _seg("history_anchor", "CHAT_HISTORY", f"Stable long history anchor {index}.", 220, ["sys"], 0.1, 0.9),
    ]
    for history_turn in range(turn + 1):
        segments.append(_seg(f"history_{history_turn}", "CHAT_HISTORY", f"Chronological stable history {history_turn} for session {index}.", 90, ["history_anchor"] if history_turn == 0 else [f"history_{history_turn - 1}"], 0.1, 0.9))
    segments.append(_seg("query", "USER_QUERY", "Answer from the history and observation.", 20, [f"history_{turn}", "tool_obs"], 0.5, 0.0))
    return {"trace_id": f"mixed_history:{index}", "turn_id": turn, "workload_family": "mixed_long_history_agent", "source_dataset": "SyntheticAgentTrace", "source_task": "mixed_long_history", "segments": segments}


def build_traces(samples: list[dict[str, Any]], turns_per_trace: int = 5) -> list[dict[str, Any]]:
    by_task = defaultdict(list)
    for sample in samples:
        by_task[(sample.get("dataset"), sample.get("task"))].append(sample)
    rows = []
    for sample in by_task[("RepoBench", "python_repository_completion")][:20]:
        for turn in range(turns_per_trace):
            rows.append(_dataset_turn(sample, "code_agent", turn))
    for sample in by_task[("LongBench", "hotpotqa")][:20]:
        for turn in range(turns_per_trace):
            rows.append(_dataset_turn(sample, "rag_agent", turn))
    for sample in by_task[("LongBench", "qasper")][:20]:
        for turn in range(turns_per_trace):
            rows.append(_dataset_turn(sample, "structured_document_qa", turn))
    for index in range(20):
        for turn in range(turns_per_trace):
            rows.append(_tool_function_turn(index, turn))
            rows.append(_mixed_history_turn(index, turn))
    return sorted(rows, key=lambda item: (item["workload_family"], item["trace_id"], int(item["turn_id"])))


def _adjacency(raw: list[str], candidate: list[str]) -> float:
    if len(raw) < 2:
        return 1.0
    candidate_pairs = set(zip(candidate, candidate[1:]))
    return sum(pair in candidate_pairs for pair in zip(raw, raw[1:])) / (len(raw) - 1)


def _ordered_document_cues(segments: list[dict[str, Any]]) -> int:
    text = "\n".join(str(segment.get("text", "")) for segment in segments if segment.get("segment_type") in {"RAG_CHUNK", "DOC_CONTEXT"})
    return len(HEADING_CUES.findall(text)) + len(DISCOURSE_CUES.findall(text))


def _risk(segments: list[dict[str, Any]], raw: list[str], candidate: list[str]) -> tuple[str, bool, bool, float, int]:
    adjacency = _adjacency(raw, candidate)
    edit = sum(left != right for left, right in zip(raw, candidate))
    code = any(segment.get("segment_type") in {"REPO_CONTEXT", "REPO_IMPORT", "REPO_CLASS", "REPO_FUNCTION"} for segment in segments)
    cues = _ordered_document_cues(segments)
    hard_sensitive = code or cues >= 2
    if cues >= 2 and edit:
        return "high", True, hard_sensitive, adjacency, edit
    if edit:
        return "medium", False, hard_sensitive, adjacency, edit
    return "low", False, hard_sensitive, adjacency, edit


def census(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_ledgers: dict[str, SegmentPrefixLedger] = defaultdict(SegmentPrefixLedger)
    caposc_ledgers: dict[str, SegmentPrefixLedger] = defaultdict(SegmentPrefixLedger)
    output = []
    for item in traces:
        segments = item["segments"]
        raw = raw_order(segments)
        raw_lcp = estimate_lcp_tokens(raw, segments, raw_ledgers[item["trace_id"]], session_id=item["trace_id"])
        posc = prefix_max_topological_order(segments)
        caposc = cache_aware_posc_compile(segments, caposc_ledgers[item["trace_id"]], item["trace_id"], int(item["turn_id"]), 100.0)
        candidate_orders = [raw, posc, caposc["topological_order"]]
        candidate_lcps = [
            estimate_lcp_tokens(order, segments, caposc_ledgers[item["trace_id"]], session_id=item["trace_id"])["matched_tokens"]
            for order in candidate_orders
        ]
        best_legal_lcp = max(candidate_lcps)
        selected_lcp = estimate_lcp_tokens(
            caposc["topological_order"], segments, caposc_ledgers[item["trace_id"]], session_id=item["trace_id"]
        )["matched_tokens"]
        risk_bucket, fallback, hard_sensitive, adjacency, edit = _risk(segments, raw, caposc["topological_order"])
        stable = sum(int(segment.get("token_count") or 0) for segment in segments if float(segment.get("cache_stability") or 0) >= 0.5)
        volatile = sum(int(segment.get("token_count") or 0) for segment in segments if float(segment.get("volatility") or 0) >= 0.5)
        gain = max(0, selected_lcp - int(raw_lcp["matched_tokens"]))
        row = {
            "trace_id": item["trace_id"], "turn_id": item["turn_id"], "workload_family": item["workload_family"],
            "source_dataset": item["source_dataset"], "source_task": item["source_task"], "stable_segment_tokens": stable,
            "volatile_segment_tokens": volatile, "raw_prefix_reuse_tokens": raw_lcp["matched_tokens"],
            "best_legal_lcp_tokens": best_legal_lcp,
            "selected_caposc_lcp_tokens": selected_lcp,
            "caposc_expected_prefix_gain": gain,
            "caposc_regret_tokens": max(0, best_legal_lcp - selected_lcp),
            "partial_canonical": caposc["topological_order"] != raw and not caposc.get("violated_edges"), "hard_order_sensitive": hard_sensitive,
            "hard_edge_valid": not caposc.get("violated_edges"), "adjacency_preservation_ratio": round(adjacency, 6),
            "relative_order_edit_distance": edit, "ordered_document_cue_count": _ordered_document_cues(segments),
            "qc_risk_bucket": risk_bucket, "qc_decision": "raw_fallback" if fallback else caposc.get("layout_decision", ""),
            "raw_fallback": fallback, "caposc_selected_policy": caposc.get("selected_policy", ""),
            "claim_boundary": "Offline compiler census; raw and CAPOSC LCP use their own policy-state ledgers, not live vLLM cache hits.",
        }
        output.append({field: row.get(field, "") for field in RAW_FIELDS})
        raw_ledgers[item["trace_id"]].update(item["trace_id"], int(item["turn_id"]), segments, raw, policy="raw-order")
        caposc_ledgers[item["trace_id"]].update(item["trace_id"], int(item["turn_id"]), segments, caposc["topological_order"], policy="caposc")
    return output


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for row in rows:
        groups[str(row["workload_family"])].append(row)
    output = []
    for family, group in sorted(groups.items()):
        gains = [float(row["caposc_expected_prefix_gain"]) for row in group]
        opportunity = [row for row in group if float(row["caposc_expected_prefix_gain"]) > 0 and row["hard_edge_valid"]]
        safe = [row for row in opportunity if not row["raw_fallback"]]
        high = [row for row in group if row["qc_risk_bucket"] == "high"]
        output.append({
            "workload_family": family, "turns": len(group), "optimization_opportunity_coverage": round(len(opportunity) / len(group), 6),
            "safe_canonicalization_coverage": round(len(safe) / len(group), 6), "median_potential_reusable_prefix_gain": round(statistics.median(gains), 6),
            "high_risk_fallback_rate": round(sum(bool(row["raw_fallback"]) for row in high) / len(high), 6) if high else 0.0,
            "raw_fallback_rate": round(sum(bool(row["raw_fallback"]) for row in group) / len(group), 6),
            "partial_canonical_rate": round(sum(bool(row["partial_canonical"]) for row in group) / len(group), 6),
            "hard_order_sensitive_fraction": round(sum(bool(row["hard_order_sensitive"]) for row in group) / len(group), 6),
            "mean_stable_segment_tokens": round(statistics.mean(float(row["stable_segment_tokens"]) for row in group), 6),
            "mean_volatile_segment_tokens": round(statistics.mean(float(row["volatile_segment_tokens"]) for row in group), 6),
            "claim_boundary": "Offline opportunity census; safe coverage is compiler-estimated and requires held-out/live validation.",
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--turns-per-trace", type=int, default=5)
    parser.add_argument("--traces-output", type=Path, default=Path("results/workload/phase14a_agent_traces_v0.jsonl"))
    parser.add_argument("--raw-output", type=Path, default=Path("results/workload/phase14a_opportunity_census_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/workload/phase14a_opportunity_census_summary_v0.csv"))
    args = parser.parse_args()
    traces = build_traces(load_jsonl(args.samples), args.turns_per_trace)
    rows = census(traces)
    write_jsonl(args.traces_output, traces)
    write_csv(args.raw_output, rows, RAW_FIELDS)
    write_csv(args.summary_output, summarize(rows), SUMMARY_FIELDS)
    print(f"traces={len(traces)} census_rows={len(rows)}")
    return 0 if len(traces) >= 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
