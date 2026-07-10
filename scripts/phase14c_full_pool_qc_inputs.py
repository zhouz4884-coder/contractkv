#!/usr/bin/env python3
"""Build Phase 14C full-pool QC features and fresh-scoring job manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase12_posc_layout_compiler import (
    enumerate_legal_topological_orders,
    expected_prefix_gain_tokens,
    validate_topological_order,
)
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text, compile_for_real_replay


PARTITIONS = {"calibration", "held_out_quality"}
DEFAULT_POLICIES = ("raw-order", "canonical-all", "static-posc", "contractkv-caposc")

HEADING_RE = re.compile(
    r"(?im)^\s*(abstract|introduction|background|method|methods|results|discussion|conclusion|related work|experiments?)s?\b"
)
CUE_RE = re.compile(
    r"(?i)\b(this paper|we propose|we present|our method|our approach|we evaluate|experimental results|baseline|dataset)\b"
)
CROSS_REF_RE = re.compile(r"(?i)\b(section|figure|fig\.|table|appendix|listing|theorem|lemma|class|function|import)\b")


FEATURE_FIELDS = [
    "sample_key",
    "candidate_id",
    "order_hash",
    "prompt_hash",
    "dataset",
    "task",
    "sample_id",
    "partition",
    "num_segments",
    "total_segment_tokens",
    "actual_prompt_tokens_after_chat_template",
    "max_model_len",
    "context_truncated",
    "context_segment_tokens",
    "segment_type_signature",
    "hard_edge_valid",
    "violated_edge_count",
    "adjacency_preservation",
    "relative_order_edit_distance",
    "moved_segment_count",
    "selected_policy",
    "layout_decision",
    "expected_prefix_gain",
    "estimated_lcp_tokens",
    "estimated_new_prefill_tokens",
    "heading_signal",
    "discourse_cue_signal",
    "cross_reference_signal",
    "ordered_discourse_signal",
    "low_adjacency_signal",
    "code_internal_order_changed",
    "code_component_crossings",
    "tool_code_dependency_violation",
    "risk_bucket",
    "risk_ucb",
    "qc_prelabel_fallback",
    "needs_fresh_quality_label",
    "claim_boundary",
]

JOB_FIELDS = [
    "job_id",
    "sample_key",
    "candidate_id",
    "order_hash",
    "prompt_hash",
    "partition",
    "dataset",
    "task",
    "sample_id",
    "policy",
    "candidate_policy",
    "candidate_aliases",
    "candidate_rank",
    "topological_order",
    "model",
    "full_pool_file",
    "feature_file",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "partition",
    "dataset",
    "task",
    "samples",
    "fresh_quality_jobs",
    "prelabel_fallback_rate",
    "mean_expected_prefix_gain",
    "mean_estimated_new_prefill_tokens",
    "ordered_discourse_rate",
    "low_adjacency_rate",
    "claim_boundary",
]

CANDIDATE_FEATURE_FIELDS = FEATURE_FIELDS + [
    "candidate_policy",
    "candidate_aliases",
    "candidate_rank",
    "topological_order",
    "candidate_estimated_lcp_tokens",
    "candidate_estimated_new_prefill_tokens",
]

CONTEXT_TYPES = {
    "RAG_CHUNK", "SYNTHETIC_CONTEXT", "REPO_IMPORT", "REPO_CLASS",
    "REPO_FUNCTION", "REPO_CONTEXT", "DOC_CONTEXT",
}
CODE_TYPES = {"REPO_IMPORT", "REPO_CLASS", "REPO_FUNCTION", "REPO_CONTEXT"}
DOCUMENT_TYPES = {"RAG_CHUNK", "DOC_CONTEXT"}


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


def sample_key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset','')}::{sample.get('task','')}::{sample.get('sample_id','')}"


def _partition(sample: dict[str, Any]) -> str:
    metadata = sample.get("metadata") or {}
    return str(metadata.get("phase14_partition", ""))


def _raw_order(case: dict[str, Any]) -> list[str]:
    return [str(segment["segment_id"]) for segment in case["segments"]]


def adjacency_preservation(raw_order: list[str], compiled_order: list[str]) -> float:
    compiled_pairs = set(zip(compiled_order, compiled_order[1:]))
    raw_pairs = list(zip(raw_order, raw_order[1:]))
    return sum(pair in compiled_pairs for pair in raw_pairs) / max(1, len(raw_pairs))


def _context_text(case: dict[str, Any]) -> str:
    return "\n".join(str(segment.get("text", "")) for segment in case["segments"] if segment.get("segment_type") in CONTEXT_TYPES)


def _document_text(case: dict[str, Any]) -> str:
    return "\n".join(
        str(segment.get("text", ""))
        for segment in case["segments"]
        if segment.get("segment_type") in DOCUMENT_TYPES
    )


def _quality_messages(case: dict[str, Any], compiled_text: str) -> list[dict[str, str]]:
    namespace = f"PHASE14C:{case['dataset']}:{case['task']}:{case['sample_id']}"
    system = "/no_think Answer the task using only the provided context. Return the shortest correct answer or code completion."
    return [{"role": "system", "content": namespace + "\n" + system}, {"role": "user", "content": compiled_text}]


def candidate_identity(case: dict[str, Any], order: list[str]) -> dict[str, str]:
    order_json = json.dumps(order, ensure_ascii=False, separators=(",", ":"))
    order_hash = hashlib.sha256(order_json.encode("utf-8")).hexdigest()[:16]
    text = _ordered_text(order, case["segments"])
    messages = _quality_messages(case, text)
    prompt_hash = hashlib.sha256(
        json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    identity = f"{case['dataset']}::{case['task']}::{case['sample_id']}::{order_hash}::{prompt_hash}"
    return {
        "candidate_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "order_hash": order_hash,
        "prompt_hash": prompt_hash,
    }


def _retokenize_case(
    case: dict[str, Any],
    tokenizer: Any | None,
    max_model_len: int = 8192,
    generation_reserve: int = 128,
) -> dict[str, Any]:
    if tokenizer is None:
        return case
    copied = {**case, "segments": [dict(segment) for segment in case["segments"]]}
    for segment in copied["segments"]:
        segment["token_count"] = len(
            tokenizer.encode(str(segment.get("text", "")), add_special_tokens=False)
        )
    copied["context_truncated"] = False
    target = max(1, max_model_len - generation_reserve - 32)
    raw = _raw_order(copied)
    while _actual_prompt_tokens(copied, raw, tokenizer) > target:
        candidates = [
            segment for segment in copied["segments"]
            if segment.get("segment_type") not in {"SYS_PROMPT", "USER_QUERY", "TOOL_OBS"}
            and int(segment.get("token_count") or 0) > 64
        ]
        if not candidates:
            raise ValueError(f"cannot fit sample {case.get('sample_id')} within max_model_len={max_model_len}")
        segment = max(candidates, key=lambda item: int(item.get("token_count") or 0))
        ids = tokenizer.encode(str(segment.get("text", "")), add_special_tokens=False)
        overflow = _actual_prompt_tokens(copied, raw, tokenizer) - target
        keep = max(64, len(ids) - max(overflow, 64))
        segment["text"] = tokenizer.decode(ids[:keep], skip_special_tokens=True)
        segment["token_count"] = len(tokenizer.encode(segment["text"], add_special_tokens=False))
        copied["context_truncated"] = True
    return copied


def _actual_prompt_tokens(case: dict[str, Any], order: list[str], tokenizer: Any | None) -> int:
    if tokenizer is None:
        return sum(int(segment.get("token_count") or 0) for segment in case["segments"])
    messages = _quality_messages(case, _ordered_text(order, case["segments"]))
    return len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))


def _code_structure_signals(case: dict[str, Any], raw: list[str], order: list[str]) -> tuple[int, int, int]:
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    raw_code = [sid for sid in raw if by_id[sid].get("segment_type") in CODE_TYPES]
    candidate_code = [sid for sid in order if by_id[sid].get("segment_type") in CODE_TYPES]
    internal_changed = int(raw_code != candidate_code)
    raw_position = {sid: index for index, sid in enumerate(raw)}
    new_position = {sid: index for index, sid in enumerate(order)}
    crossings = 0
    for left, right in zip(raw_code, raw_code[1:]):
        if new_position.get(left, -1) > new_position.get(right, -1):
            crossings += 1
    tool_dependency_violation = 0
    for segment in case["segments"]:
        sid = str(segment["segment_id"])
        if by_id[sid].get("segment_type") not in CODE_TYPES:
            continue
        for dep in segment.get("dependencies", []):
            dep = str(dep)
            if by_id.get(dep, {}).get("segment_type") == "TOOL_OBS" and new_position.get(dep, -1) > new_position.get(sid, -1):
                tool_dependency_violation += 1
    return internal_changed, crossings, tool_dependency_violation


def _segment_signature(case: dict[str, Any]) -> str:
    counts = Counter(str(segment.get("segment_type", "")) for segment in case["segments"])
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


def _feature_for_candidate(
    sample: dict[str, Any],
    case: dict[str, Any],
    order: list[str],
    compiled: dict[str, Any],
    tokenizer: Any | None = None,
    max_model_len: int = 8192,
) -> dict[str, Any]:
    raw = _raw_order(case)
    moved = [sid for index, sid in enumerate(order) if index >= len(raw) or raw[index] != sid]
    text = _document_text(case)
    heading = len(HEADING_RE.findall(text))
    discourse = len(CUE_RE.findall(text))
    cross_ref = len(CROSS_REF_RE.findall(text))
    adjacency = adjacency_preservation(raw, order)
    edit_distance = sum(a != b for a, b in zip(raw, order)) + abs(len(raw) - len(order))
    violated_edges = validate_topological_order(order, case["segments"])
    ordered_discourse_signal = int((heading + discourse) >= 2 and edit_distance > 0)
    low_adjacency_signal = int(adjacency < 0.75 and edit_distance > 0)
    code_internal_changed, code_crossings, tool_code_violation = _code_structure_signals(case, raw, order)
    high_risk = bool(violated_edges) or bool(ordered_discourse_signal) or bool(code_internal_changed) or bool(tool_code_violation)
    tokens = sum(int(segment.get("token_count") or 0) for segment in case["segments"])
    context_tokens = sum(
        int(segment.get("token_count") or 0)
        for segment in case["segments"]
        if segment.get("segment_type") not in {"SYS_PROMPT", "USER_QUERY", "TOOL_OBS"}
    )
    identity = candidate_identity(case, order)
    return {
        "sample_key": sample_key(sample),
        **identity,
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "partition": _partition(sample),
        "num_segments": len(case["segments"]),
        "total_segment_tokens": tokens,
        "actual_prompt_tokens_after_chat_template": _actual_prompt_tokens(case, order, tokenizer),
        "max_model_len": max_model_len,
        "context_truncated": bool(case.get("context_truncated", False)),
        "context_segment_tokens": context_tokens,
        "segment_type_signature": _segment_signature(case),
        "hard_edge_valid": not bool(violated_edges),
        "violated_edge_count": len(violated_edges),
        "adjacency_preservation": round(adjacency, 6),
        "relative_order_edit_distance": edit_distance,
        "moved_segment_count": len(moved),
        "selected_policy": compiled.get("selected_policy", "cache-aware-posc"),
        "layout_decision": compiled.get("layout_decision", ""),
        "expected_prefix_gain": expected_prefix_gain_tokens(order, case["segments"]),
        "estimated_lcp_tokens": compiled.get("estimated_lcp_tokens", 0),
        "estimated_new_prefill_tokens": compiled.get("estimated_new_prefill_tokens", tokens),
        "heading_signal": heading,
        "discourse_cue_signal": discourse,
        "cross_reference_signal": cross_ref,
        "ordered_discourse_signal": ordered_discourse_signal,
        "low_adjacency_signal": low_adjacency_signal,
        "code_internal_order_changed": code_internal_changed,
        "code_component_crossings": code_crossings,
        "tool_code_dependency_violation": tool_code_violation,
        "risk_bucket": "structural_fallback_candidate" if high_risk else "needs_label_low_structure",
        "risk_ucb": 0.05 if high_risk else 0.0,
        "qc_prelabel_fallback": high_risk,
        "needs_fresh_quality_label": True,
        "claim_boundary": "Full-pool structural QC feature only; final safety labels require fresh paired Qwen3-8B scoring.",
    }


def build_feature(sample: dict[str, Any], stable_word_limit: int = 2600, tokenizer: Any | None = None, max_model_len: int = 8192) -> dict[str, Any]:
    case = _retokenize_case(build_case(sample, stable_word_limit=stable_word_limit), tokenizer, max_model_len)
    compiled = compile_for_real_replay("cache-aware-posc", case, SegmentPrefixLedger())
    order = [str(item) for item in compiled.get("topological_order", [])]
    return _feature_for_candidate(sample, case, order, compiled, tokenizer, max_model_len)


def build_candidate_features(sample: dict[str, Any], stable_word_limit: int = 2600, tokenizer: Any | None = None, max_model_len: int = 8192) -> list[dict[str, Any]]:
    case = _retokenize_case(build_case(sample, stable_word_limit=stable_word_limit), tokenizer, max_model_len)
    compiled = compile_for_real_replay("cache-aware-posc", case, SegmentPrefixLedger())
    aliases_by_order: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for candidate in compiled.get("candidates", []):
        order = tuple(str(item) for item in candidate.get("topological_order", []))
        if order and not validate_topological_order(list(order), case["segments"]):
            aliases_by_order[order].append(str(candidate.get("policy", "")))
    legal_orders: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for order in enumerate_legal_topological_orders(case["segments"], max_orders=64):
        key = tuple(order)
        if key not in seen:
            seen.add(key)
            legal_orders.append(order)
    for order in aliases_by_order:
        if order not in seen:
            seen.add(order)
            legal_orders.append(list(order))
    rows: list[dict[str, Any]] = []
    for rank, order in enumerate(legal_orders):
        aliases = [item for item in aliases_by_order.get(tuple(order), []) if item]
        primary = aliases[0] if aliases else "legal-topological-order"
        candidate = {
            "topological_order": order,
            "selected_policy": primary,
            "layout_decision": "raw_order" if order == _raw_order(case) else "partial_canonical",
            "violated_edges": [],
            "estimated_lcp_tokens": 0,
            "estimated_new_prefill_tokens": sum(int(segment.get("token_count") or 0) for segment in case["segments"]),
        }
        row = _feature_for_candidate(sample, case, order, candidate, tokenizer, max_model_len)
        row.update(
            {
                "candidate_policy": primary,
                "candidate_aliases": json.dumps(aliases, ensure_ascii=False),
                "candidate_rank": rank,
                "topological_order": json.dumps(order, ensure_ascii=False),
                "candidate_estimated_lcp_tokens": row.get("estimated_lcp_tokens", 0),
                "candidate_estimated_new_prefill_tokens": row.get("estimated_new_prefill_tokens", 0),
                "claim_boundary": "Candidate-level QC feature; risk must be calibrated from paired labels before deployment.",
            }
        )
        rows.append(row)
    return rows


def build_features(samples: list[dict[str, Any]], stable_word_limit: int = 2600, tokenizer: Any | None = None, max_model_len: int = 8192) -> list[dict[str, Any]]:
    return [
        build_feature(sample, stable_word_limit=stable_word_limit, tokenizer=tokenizer, max_model_len=max_model_len)
        for sample in samples
        if _partition(sample) in PARTITIONS
    ]


def build_jobs(
    features: list[dict[str, Any]],
    policies: list[str] | None,
    model: str,
    full_pool_file: str,
    feature_file: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        policy = str(feature.get("candidate_policy") or "legal-topological-order")
        key = f"{feature['sample_key']}::{feature.get('candidate_id','')}"
        rows.append(
            {
                    "job_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
                    "sample_key": feature["sample_key"],
                    "candidate_id": feature.get("candidate_id", ""),
                    "order_hash": feature.get("order_hash", ""),
                    "prompt_hash": feature.get("prompt_hash", ""),
                    "partition": feature["partition"],
                    "dataset": feature["dataset"],
                    "task": feature["task"],
                    "sample_id": feature["sample_id"],
                    "policy": policy,
                    "candidate_policy": policy,
                    "candidate_aliases": feature.get("candidate_aliases", "[]"),
                    "candidate_rank": feature.get("candidate_rank", 0),
                    "topological_order": feature.get("topological_order", ""),
                    "model": model,
                    "full_pool_file": full_pool_file,
                    "feature_file": feature_file,
                    "claim_boundary": "Fresh quality scoring job manifest; does not embed source prompt text.",
                }
            )
    return rows


def summarize(features: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        grouped[(str(row["partition"]), str(row["dataset"]), str(row["task"]))].append(row)
    job_counts = Counter((str(row["partition"]), str(row["dataset"]), str(row["task"])) for row in jobs)
    output: list[dict[str, Any]] = []
    for (partition, dataset, task), group in sorted(grouped.items()):
        output.append(
            {
                "partition": partition,
                "dataset": dataset,
                "task": task,
                "samples": len(group),
                "fresh_quality_jobs": job_counts[(partition, dataset, task)],
                "prelabel_fallback_rate": round(sum(bool(row["qc_prelabel_fallback"]) for row in group) / len(group), 6),
                "mean_expected_prefix_gain": round(sum(float(row["expected_prefix_gain"] or 0) for row in group) / len(group), 6),
                "mean_estimated_new_prefill_tokens": round(sum(float(row["estimated_new_prefill_tokens"] or 0) for row in group) / len(group), 6),
                "ordered_discourse_rate": round(sum(int(row["ordered_discourse_signal"]) for row in group) / len(group), 6),
                "low_adjacency_rate": round(sum(int(row["low_adjacency_signal"]) for row in group) / len(group), 6),
                "claim_boundary": "Full-pool QC input manifest; not a calibrated final gate.",
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--feature-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_qc_features_v0.csv"))
    parser.add_argument("--jobs-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase14c_full_pool_qc_feature_summary_v0.csv"))
    parser.add_argument("--policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tokenizer", default="")
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--candidate-feature-output", type=Path, default=Path("results/end_to_end/phase14r_qc_candidate_features_v0.csv"))
    args = parser.parse_args()
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    tokenizer = None
    if args.tokenizer:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    features = build_features(load_jsonl(args.full_pool), stable_word_limit=args.stable_word_limit, tokenizer=tokenizer, max_model_len=args.max_model_len)
    candidate_features = []
    for sample in load_jsonl(args.full_pool):
        if _partition(sample) in PARTITIONS:
            candidate_features.extend(build_candidate_features(sample, stable_word_limit=args.stable_word_limit, tokenizer=tokenizer, max_model_len=args.max_model_len))
    jobs = build_jobs(
        candidate_features,
        None,
        args.model,
        str(args.full_pool),
        str(args.candidate_feature_output),
    )
    write_csv(args.feature_output, features, FEATURE_FIELDS)
    write_csv(args.candidate_feature_output, candidate_features, CANDIDATE_FEATURE_FIELDS)
    write_jsonl(args.jobs_output, jobs)
    write_csv(args.summary_output, summarize(features, jobs), SUMMARY_FIELDS)
    print(f"features={len(features)} candidates={len(candidate_features)} jobs={len(jobs)} unique-layout manifest")
    return 0 if features and jobs else 1


if __name__ == "__main__":
    raise SystemExit(main())
