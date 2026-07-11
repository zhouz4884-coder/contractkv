#!/usr/bin/env python3
"""Recompute Phase 14 quality safety at the deployed request decision level."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


AUDIT_FIELDS = [
    "partition", "sample_key", "dataset", "task", "default_candidate_id",
    "default_unsafe", "pareto_candidates", "selected_candidate_id",
    "selected_predicted_risk", "selected_quality_drop", "selected_unsafe",
    "selected_safe", "fallback_raw", "unsafe_default_caught",
    "expected_prefix_gain", "oracle_safe_prefix_gain", "retained_prefix_gain",
    "exact_output_match", "decision_reason", "claim_boundary",
]

SUMMARY_FIELDS = [
    "partition", "threshold", "requests", "selected_requests",
    "selected_unsafe", "selected_false_safe_rate", "selected_false_safe_wilson95",
    "safe_opportunity_requests", "safe_opportunity_covered", "safe_opportunity_coverage",
    "unsafe_default_requests", "unsafe_default_caught", "unsafe_default_catch_rate",
    "oracle_safe_prefix_gain", "retained_safe_prefix_gain", "retained_prefix_gain_fraction",
    "exact_output_selected", "exact_output_coverage", "deployment_gate_open", "claim_boundary",
]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def wilson_upper(successes: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 1.0
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = p + z * z / (2.0 * total)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
    return min(1.0, (centre + spread) / denominator)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _output_hash(value: Any) -> str:
    normalized = " ".join(str(value or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _disruption(row: dict[str, Any]) -> float:
    return (
        max(0.0, 1.0 - _float(row.get("adjacency_preservation")))
        + _float(row.get("relative_order_edit_distance"))
        + _float(row.get("moved_segment_count"))
        + 10.0 * _float(row.get("violated_edge_count"))
    )


def pareto_prune(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove candidates dominated in work, disruption, and predicted risk."""
    kept = []
    for candidate in rows:
        work = _float(candidate.get("candidate_estimated_new_prefill_tokens")
                      or candidate.get("estimated_new_prefill_tokens"))
        disruption = _disruption(candidate)
        risk = _float(candidate.get("predicted_risk"))
        dominated = False
        for other in rows:
            if other is candidate:
                continue
            other_work = _float(other.get("candidate_estimated_new_prefill_tokens")
                                or other.get("estimated_new_prefill_tokens"))
            other_disruption = _disruption(other)
            other_risk = _float(other.get("predicted_risk"))
            no_worse = (other_work <= work and other_disruption <= disruption
                        and other_risk <= risk)
            strictly_better = (other_work < work or other_disruption < disruption
                               or other_risk < risk)
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            kept.append(candidate)
    return kept


def _default_candidate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    caposc = [row for row in rows if "cache-aware-posc" in str(row.get("candidate_aliases", ""))]
    pool = caposc or rows
    return min(pool, key=lambda row: (
        _float(row.get("candidate_estimated_new_prefill_tokens")
               or row.get("estimated_new_prefill_tokens")),
        -_float(row.get("expected_prefix_gain")),
        str(row.get("candidate_id")),
    )) if pool else None


def _select(rows: list[dict[str, Any]], threshold: float) -> tuple[dict[str, Any] | None, int]:
    front = pareto_prune(rows)
    accepted = [row for row in front if _float(row.get("predicted_risk")) <= threshold]
    if not accepted:
        return None, len(front)
    return min(accepted, key=lambda row: (
        _float(row.get("candidate_estimated_new_prefill_tokens")
               or row.get("estimated_new_prefill_tokens")),
        _float(row.get("predicted_risk")),
        _disruption(row),
    )), len(front)


def build_rows(
    features: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    raw_outputs: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    label_by_id = {(row["sample_key"], row["candidate_id"]): row for row in labels}
    score_by_id = {(row["sample_key"], row["candidate_id"]): row for row in scores}
    outputs_by_id = {(row.get("sample_key"), row.get("candidate_id")): row for row in raw_outputs}
    raw_output_by_sample = {
        str(row.get("sample_key")): row for row in raw_outputs
        if str(row.get("policy")) == "raw-order"
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        key = (feature.get("sample_key", ""), feature.get("candidate_id", ""))
        label = label_by_id.get(key)
        if label is None:
            continue
        row = dict(feature)
        row.update({
            "predicted_risk": score_by_id.get(key, {}).get("predicted_risk", 1.0),
            "quality_drop_vs_raw": label.get("quality_drop_vs_raw", 0.0),
            "unsafe_quality_drop": label.get("unsafe_quality_drop", False),
        })
        grouped[str(feature["sample_key"])].append(row)

    audit = []
    for sample_key, candidates in sorted(grouped.items()):
        default = _default_candidate(candidates)
        selected, front_count = _select(candidates, threshold)
        safe = [row for row in candidates if not _bool(row.get("unsafe_quality_drop"))]
        oracle_gain = max((_float(row.get("expected_prefix_gain")) for row in safe), default=0.0)
        selected_gain = _float(selected.get("expected_prefix_gain")) if selected else 0.0
        selected_unsafe = bool(selected and _bool(selected.get("unsafe_quality_drop")))
        selected_output = outputs_by_id.get((sample_key, selected.get("candidate_id"))) if selected else None
        raw_output = raw_output_by_sample.get(sample_key)
        exact_match: bool | str = ""
        if selected_output is not None and raw_output is not None:
            exact_match = _output_hash(selected_output.get("output_text")) == _output_hash(raw_output.get("output_text"))
        audit.append({
            "partition": candidates[0].get("partition", ""),
            "sample_key": sample_key,
            "dataset": candidates[0].get("dataset", ""),
            "task": candidates[0].get("task", ""),
            "default_candidate_id": default.get("candidate_id", "") if default else "",
            "default_unsafe": _bool(default.get("unsafe_quality_drop")) if default else False,
            "pareto_candidates": front_count,
            "selected_candidate_id": selected.get("candidate_id", "") if selected else "",
            "selected_predicted_risk": _float(selected.get("predicted_risk")) if selected else "",
            "selected_quality_drop": _float(selected.get("quality_drop_vs_raw")) if selected else 0.0,
            "selected_unsafe": selected_unsafe,
            "selected_safe": bool(selected and not selected_unsafe),
            "fallback_raw": selected is None,
            "unsafe_default_caught": bool(default and _bool(default.get("unsafe_quality_drop")) and not selected_unsafe),
            "expected_prefix_gain": selected_gain,
            "oracle_safe_prefix_gain": oracle_gain,
            "retained_prefix_gain": min(selected_gain, oracle_gain) if selected and not selected_unsafe else 0.0,
            "exact_output_match": exact_match,
            "decision_reason": "pareto_safe_candidate" if selected else "fail_closed_raw_fallback",
            "claim_boundary": "Request-level selection audit over paired fresh Qwen3-8B task-sanity labels; not official benchmark scoring.",
        })
    return audit


def summarize(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    output = []
    for partition in sorted({str(row["partition"]) for row in rows} | {"all"}):
        group = rows if partition == "all" else [row for row in rows if row["partition"] == partition]
        selected = [row for row in group if not _bool(row["fallback_raw"])]
        selected_unsafe = sum(_bool(row["selected_unsafe"]) for row in selected)
        opportunities = [row for row in group if _float(row["oracle_safe_prefix_gain"]) > 0]
        covered = [row for row in opportunities if _bool(row["selected_safe"])]
        unsafe_defaults = [row for row in group if _bool(row["default_unsafe"])]
        caught = sum(_bool(row["unsafe_default_caught"]) for row in unsafe_defaults)
        oracle_gain = sum(_float(row["oracle_safe_prefix_gain"]) for row in group)
        retained_gain = sum(_float(row["retained_prefix_gain"]) for row in group)
        exact_known = [row for row in selected if row["exact_output_match"] != ""]
        exact = sum(_bool(row["exact_output_match"]) for row in exact_known)
        coverage = len(covered) / len(opportunities) if opportunities else 0.0
        catch_rate = caught / len(unsafe_defaults) if unsafe_defaults else 1.0
        retained_fraction = retained_gain / oracle_gain if oracle_gain else 0.0
        upper = wilson_upper(selected_unsafe, len(selected))
        gate = upper <= 0.03 and coverage >= 0.60 and catch_rate >= 0.80 and retained_fraction >= 0.60
        output.append({
            "partition": partition,
            "threshold": threshold,
            "requests": len(group),
            "selected_requests": len(selected),
            "selected_unsafe": selected_unsafe,
            "selected_false_safe_rate": selected_unsafe / len(selected) if selected else 0.0,
            "selected_false_safe_wilson95": upper,
            "safe_opportunity_requests": len(opportunities),
            "safe_opportunity_covered": len(covered),
            "safe_opportunity_coverage": coverage,
            "unsafe_default_requests": len(unsafe_defaults),
            "unsafe_default_caught": caught,
            "unsafe_default_catch_rate": catch_rate,
            "oracle_safe_prefix_gain": oracle_gain,
            "retained_safe_prefix_gain": retained_gain,
            "retained_prefix_gain_fraction": retained_fraction,
            "exact_output_selected": exact,
            "exact_output_coverage": exact / len(exact_known) if exact_known else 0.0,
            "deployment_gate_open": gate,
            "claim_boundary": "Request-level held-out gate. A closed gate routes deployment to SLC rather than relaxing safety bounds.",
        })
    return output


def choose_threshold(features, labels, scores, raw_outputs) -> float:
    calibration_scores = sorted({
        _float(row.get("predicted_risk")) for row in scores
        if row.get("partition") == "calibration"
    })
    thresholds = [-1.0] + calibration_scores
    best = (-1.0, -1.0, -1.0)
    for threshold in thresholds:
        rows = build_rows(features, labels, scores, raw_outputs, threshold)
        summary = next(row for row in summarize(rows, threshold) if row["partition"] == "calibration")
        if _float(summary["selected_false_safe_wilson95"]) > 0.03:
            continue
        objective = (
            _float(summary["retained_prefix_gain_fraction"]),
            _float(summary["safe_opportunity_coverage"]),
            threshold,
        )
        if objective > best:
            best = objective
    return best[2]


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--raw-outputs", type=Path)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    features, labels, scores = load_csv(args.features), load_csv(args.labels), load_csv(args.scores)
    raw_outputs = load_jsonl(args.raw_outputs)
    threshold = choose_threshold(features, labels, scores, raw_outputs)
    rows = build_rows(features, labels, scores, raw_outputs, threshold)
    summary = summarize(rows, threshold)
    write_csv(args.audit_output, rows, AUDIT_FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    held = next((row for row in summary if row["partition"] == "held_out_quality"), None)
    print(json.dumps({"threshold": threshold, "held_out": held}, ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
