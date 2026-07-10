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
from scripts.phase12_posc_layout_compiler import expected_prefix_gain_tokens
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import compile_for_real_replay


PARTITIONS = {"calibration", "held_out_quality"}
DEFAULT_POLICIES = ("raw-order", "contractkv-caposc")

HEADING_RE = re.compile(
    r"(?im)^\s*(abstract|introduction|background|method|methods|results|discussion|conclusion|related work|experiments?)s?\b"
)
CUE_RE = re.compile(
    r"(?i)\b(this paper|we propose|we present|our method|our approach|we evaluate|experimental results|baseline|dataset)\b"
)
CROSS_REF_RE = re.compile(r"(?i)\b(section|figure|fig\.|table|appendix|listing|theorem|lemma|class|function|import)\b")


FEATURE_FIELDS = [
    "sample_key",
    "dataset",
    "task",
    "sample_id",
    "partition",
    "num_segments",
    "total_segment_tokens",
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
    "risk_bucket",
    "risk_ucb",
    "qc_prelabel_fallback",
    "needs_fresh_quality_label",
    "claim_boundary",
]

JOB_FIELDS = [
    "job_id",
    "sample_key",
    "partition",
    "dataset",
    "task",
    "sample_id",
    "policy",
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
    context_types = {"RAG_CHUNK", "SYNTHETIC_CONTEXT", "REPO_IMPORT", "REPO_CLASS", "REPO_FUNCTION", "REPO_CONTEXT", "DOC_CONTEXT"}
    return "\n".join(str(segment.get("text", "")) for segment in case["segments"] if segment.get("segment_type") in context_types)


def _segment_signature(case: dict[str, Any]) -> str:
    counts = Counter(str(segment.get("segment_type", "")) for segment in case["segments"])
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


def build_feature(sample: dict[str, Any], stable_word_limit: int = 2600) -> dict[str, Any]:
    case = build_case(sample, stable_word_limit=stable_word_limit)
    raw = _raw_order(case)
    compiled = compile_for_real_replay("cache-aware-posc", case, SegmentPrefixLedger())
    order = [str(item) for item in compiled.get("topological_order", [])]
    moved = [sid for index, sid in enumerate(order) if index >= len(raw) or raw[index] != sid]
    text = _context_text(case)
    heading = len(HEADING_RE.findall(text))
    discourse = len(CUE_RE.findall(text))
    cross_ref = len(CROSS_REF_RE.findall(text))
    adjacency = adjacency_preservation(raw, order)
    edit_distance = sum(a != b for a, b in zip(raw, order)) + abs(len(raw) - len(order))
    violated_edges = compiled.get("violated_edges", [])
    ordered_discourse_signal = int((heading + discourse) >= 2 and edit_distance > 0)
    low_adjacency_signal = int(adjacency < 0.75 and edit_distance > 0)
    high_risk = bool(violated_edges) or bool(ordered_discourse_signal)
    tokens = sum(int(segment.get("token_count") or 0) for segment in case["segments"])
    context_tokens = sum(
        int(segment.get("token_count") or 0)
        for segment in case["segments"]
        if segment.get("segment_type") not in {"SYS_PROMPT", "USER_QUERY", "TOOL_OBS"}
    )
    return {
        "sample_key": sample_key(sample),
        "dataset": sample.get("dataset", ""),
        "task": sample.get("task", ""),
        "sample_id": str(sample.get("sample_id", "")),
        "partition": _partition(sample),
        "num_segments": len(case["segments"]),
        "total_segment_tokens": tokens,
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
        "risk_bucket": "structural_fallback_candidate" if high_risk else "needs_label_low_structure",
        "risk_ucb": 0.05 if high_risk else 0.0,
        "qc_prelabel_fallback": high_risk,
        "needs_fresh_quality_label": True,
        "claim_boundary": "Full-pool structural QC feature only; final safety labels require fresh paired Qwen3-8B scoring.",
    }


def build_features(samples: list[dict[str, Any]], stable_word_limit: int = 2600) -> list[dict[str, Any]]:
    return [
        build_feature(sample, stable_word_limit=stable_word_limit)
        for sample in samples
        if _partition(sample) in PARTITIONS
    ]


def build_jobs(
    features: list[dict[str, Any]],
    policies: list[str],
    model: str,
    full_pool_file: str,
    feature_file: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        for policy in policies:
            key = f"{feature['sample_key']}::{policy}"
            rows.append(
                {
                    "job_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
                    "sample_key": feature["sample_key"],
                    "partition": feature["partition"],
                    "dataset": feature["dataset"],
                    "task": feature["task"],
                    "sample_id": feature["sample_id"],
                    "policy": policy,
                    "model": model,
                    "full_pool_file": full_pool_file,
                    "feature_file": feature_file,
                    "claim_boundary": "Fresh quality scoring job manifest; does not embed source prompt text.",
                }
            )
    return rows


def summarize(features: list[dict[str, Any]], policies: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        grouped[(str(row["partition"]), str(row["dataset"]), str(row["task"]))].append(row)
    output: list[dict[str, Any]] = []
    for (partition, dataset, task), group in sorted(grouped.items()):
        output.append(
            {
                "partition": partition,
                "dataset": dataset,
                "task": task,
                "samples": len(group),
                "fresh_quality_jobs": len(group) * len(policies),
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
    args = parser.parse_args()
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    features = build_features(load_jsonl(args.full_pool), stable_word_limit=args.stable_word_limit)
    jobs = build_jobs(
        features,
        policies,
        args.model,
        str(args.full_pool),
        str(args.feature_output),
    )
    write_csv(args.feature_output, features, FEATURE_FIELDS)
    write_jsonl(args.jobs_output, jobs)
    write_csv(args.summary_output, summarize(features, policies), SUMMARY_FIELDS)
    print(f"features={len(features)} jobs={len(jobs)} policies={','.join(policies)}")
    return 0 if features and jobs else 1


if __name__ == "__main__":
    raise SystemExit(main())
