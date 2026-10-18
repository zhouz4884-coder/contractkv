#!/usr/bin/env python3
"""Risk-constrained CAPOSC replay on ordered-document Qasper samples."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import approximate_prompt_tokens, send_chat_stream
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text, compile_for_real_replay
from scripts.phase13b_fresh_policy_quality_replay import build_case, load_jsonl, write_csv, write_jsonl


POLICIES = ["raw-order", "contractkv-caposc", "qc-caposc"]
HEADINGS = re.compile(r"(?im)^\s*(abstract|introduction|background|method|methods|results|discussion|conclusion|related work|experiments?)s?\b")
DISCOURSE_CUES = re.compile(r"(?i)\b(this paper|we propose|we present|our method|our approach|we evaluate|experimental results|baseline|dataset)\b")
RAW_FIELDS = [
    "sample_id", "policy", "selected_layout_policy", "layout_decision", "prompt_hash", "prompt_tokens",
    "hard_edge_valid", "adjacency_preservation_ratio", "relative_order_edit_distance",
    "evidence_query_distance_delta_tokens", "ordered_document_heading_count", "layout_risk_mean",
    "layout_risk_upper_bound", "risk_fallback", "score", "success", "output_text", "answer",
    "ttft_ms", "tpot_ms", "total_latency_ms", "claim_boundary",
]


def _adjacency(raw: list[str], candidate: list[str]) -> float:
    if len(raw) < 2:
        return 1.0
    return sum(pair in set(zip(candidate, candidate[1:])) for pair in zip(raw, raw[1:])) / (len(raw) - 1)


def _distance(raw: list[str], candidate: list[str]) -> int:
    return sum(left != right for left, right in zip(raw, candidate))


def _ordered_document_heading_count(case: dict[str, Any]) -> int:
    text = "\n".join(str(segment.get("text", "")) for segment in case["segments"] if segment.get("segment_type") == "RAG_CHUNK")
    # The feature is computed after prompt truncation.  Scientific PDFs often
    # lose explicit headings in an early context window, so discourse cues
    # provide a second, task-independent signal for an ordered component.
    return len(HEADINGS.findall(text)) + len(DISCOURSE_CUES.findall(text))


def qc_compile(case: dict[str, Any], ledger: SegmentPrefixLedger, epsilon: float) -> dict[str, Any]:
    caposc = compile_for_real_replay("cache-aware-posc", case, ledger)
    raw = [str(segment["segment_id"]) for segment in case["segments"]]
    candidate = list(caposc["topological_order"])
    headings = _ordered_document_heading_count(case)
    adjacency = _adjacency(raw, candidate)
    edit_distance = _distance(raw, candidate)
    hard_valid = not caposc.get("violated_edges")
    # A scientific document with multiple headings is an ordered discourse
    # component. Moving a volatile observation through it is a risk signal,
    # rather than a task-name-specific special case.
    risk_mean = (1.0 - adjacency) * (0.08 if headings >= 2 else 0.01)
    risk_ucb = risk_mean + (0.04 if headings >= 2 and edit_distance > 0 else 0.0)
    fallback = not hard_valid or risk_ucb > epsilon
    if fallback:
        caposc = dict(caposc)
        caposc["topological_order"] = raw
        caposc["selected_policy"] = "qc-caposc-raw-fallback"
        caposc["layout_decision"] = "raw_order_risk_fallback"
        caposc["violated_edges"] = []
    caposc.update({
        "hard_edge_valid": hard_valid,
        "adjacency_preservation_ratio": round(adjacency, 6),
        "relative_order_edit_distance": edit_distance,
        "evidence_query_distance_delta_tokens": 0,
        "ordered_document_heading_count": headings,
        "layout_risk_mean": round(risk_mean, 6),
        "layout_risk_upper_bound": round(risk_ucb, 6),
        "risk_fallback": fallback,
    })
    return caposc


def _messages(case: dict[str, Any], text: str) -> list[dict[str, str]]:
    # Policy-independent wrapper is intentional: a QC raw fallback has the
    # same prompt hash as raw-order for the same sample.
    system = "/no_think Answer the task using only the provided context. Return the shortest correct answer."
    return [{"role": "system", "content": "PHASE13D_QC\n" + system}, {"role": "user", "content": text}]


def run(samples: list[dict[str, Any]], base_url: str, model: str, epsilon: float, max_tokens: int, timeout: float) -> list[dict[str, Any]]:
    selected = [sample for sample in samples if sample.get("task") == "qasper"][:20]
    rows = []
    ledgers = {policy: SegmentPrefixLedger() for policy in POLICIES}
    for sample in selected:
        case = build_case(sample, stable_word_limit=2600)
        raw_order = [str(segment["segment_id"]) for segment in case["segments"]]
        for policy in POLICIES:
            if policy == "raw-order":
                compiled = {"topological_order": raw_order, "selected_policy": policy, "layout_decision": "raw_order", "violated_edges": [], "hard_edge_valid": True, "adjacency_preservation_ratio": 1.0, "relative_order_edit_distance": 0, "evidence_query_distance_delta_tokens": 0, "ordered_document_heading_count": _ordered_document_heading_count(case), "layout_risk_mean": 0.0, "layout_risk_upper_bound": 0.0, "risk_fallback": False}
            elif policy == "contractkv-caposc":
                compiled = compile_for_real_replay("cache-aware-posc", case, ledgers[policy])
                compiled.update({"hard_edge_valid": not compiled.get("violated_edges"), "adjacency_preservation_ratio": round(_adjacency(raw_order, compiled["topological_order"]), 6), "relative_order_edit_distance": _distance(raw_order, compiled["topological_order"]), "evidence_query_distance_delta_tokens": 0, "ordered_document_heading_count": _ordered_document_heading_count(case), "layout_risk_mean": "", "layout_risk_upper_bound": "", "risk_fallback": False})
            else:
                compiled = qc_compile(case, ledgers[policy], epsilon)
            text = _ordered_text(compiled["topological_order"], case["segments"])
            messages = _messages(case, text)
            prompt_hash = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
            result = send_chat_stream(base_url, model, messages, max_tokens, timeout, f"phase13d-qc-{sample['sample_id']}-{policy}")
            score = score_answer(result.get("output_text", ""), case["answer"], "LongBench")
            row = {
                "sample_id": sample["sample_id"], "policy": policy, "selected_layout_policy": compiled.get("selected_policy", policy), "layout_decision": compiled.get("layout_decision", ""),
                "prompt_hash": prompt_hash, "prompt_tokens": approximate_prompt_tokens(messages), "hard_edge_valid": compiled["hard_edge_valid"],
                "adjacency_preservation_ratio": compiled["adjacency_preservation_ratio"], "relative_order_edit_distance": compiled["relative_order_edit_distance"],
                "evidence_query_distance_delta_tokens": compiled["evidence_query_distance_delta_tokens"], "ordered_document_heading_count": compiled["ordered_document_heading_count"],
                "layout_risk_mean": compiled["layout_risk_mean"], "layout_risk_upper_bound": compiled["layout_risk_upper_bound"], "risk_fallback": compiled["risk_fallback"],
                "score": score["score"], "success": result.get("success", False), "output_text": result.get("output_text", ""), "answer": case["answer"],
                "ttft_ms": result.get("ttft_ms", 0.0), "tpot_ms": result.get("tpot_ms", 0.0), "total_latency_ms": result.get("total_latency_ms", 0.0),
                "claim_boundary": "Fresh QC-CAPOSC Qasper sanity replay; a generic ordered-discourse risk fallback, not official LongBench scoring.",
            }
            rows.append({field: row.get(field, "") for field in RAW_FIELDS})
            ledgers[policy].update(case["trajectory_id"], 0, case["segments"], compiled["topological_order"], policy=policy)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("results/datasets/sample_prompts.jsonl"))
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--epsilon", type=float, default=0.03)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output", type=Path, default=Path("results/end_to_end/phase13d_qc_caposc_qasper_raw_v0.jsonl"))
    args = parser.parse_args()
    rows = run(load_jsonl(args.samples), args.base_url, args.model, args.epsilon, args.max_tokens, args.timeout)
    write_jsonl(args.output, rows)
    print(f"qc_qasper_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
