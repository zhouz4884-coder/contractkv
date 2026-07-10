#!/usr/bin/env python3
"""Calibrate a lightweight Phase 14R candidate-level QC risk selector.

This script intentionally separates two roles:

* completed paired labels provide supervised calibration data;
* candidate feature rows describe the broader layout choice space.

The resulting model is a small logistic regressor trained only on the
calibration partition.  It reports held-out false-safe, coverage, and Wilson
upper bounds so Phase 14D can use QC-CAPOSC-v2 without pretending a fixed
prelabel rule is a calibrated model.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


FEATURE_NAMES = [
    "violated_edge_count",
    "adjacency_loss",
    "relative_order_edit_distance",
    "moved_segment_count",
    "ordered_discourse_signal",
    "low_adjacency_signal",
    "cross_reference_signal",
    "code_internal_order_changed",
    "code_component_crossings",
    "tool_code_dependency_violation",
    "expected_prefix_gain_k",
    "context_segment_tokens_k",
]

SCORE_FIELDS = [
    "sample_key",
    "candidate_id",
    "order_hash",
    "prompt_hash",
    "partition",
    "dataset",
    "task",
    "sample_id",
    "candidate_policy",
    "unsafe_quality_drop",
    "quality_drop_vs_raw",
    "predicted_risk",
    "qc_fallback_v2",
    "safe_optimization_v2",
    "false_safe_v2",
    "claim_boundary",
]

SUMMARY_FIELDS = [
    "split",
    "requests",
    "unsafe_requests",
    "threshold",
    "fallback_rate",
    "false_safe_rate",
    "false_safe_wilson95_upper",
    "safe_optimization_coverage",
    "unsafe_caught_rate",
    "mean_quality_drop",
    "claim_boundary",
]


def _rows(path: Path) -> list[dict[str, Any]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8", newline=""))) if path.exists() else []


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _feature_vector(row: dict[str, Any]) -> list[float]:
    adjacency = _float(row.get("adjacency_preservation"))
    return [
        _float(row.get("violated_edge_count")),
        max(0.0, 1.0 - adjacency),
        _float(row.get("relative_order_edit_distance")),
        _float(row.get("moved_segment_count")),
        1.0 if _bool(row.get("ordered_discourse_signal")) else 0.0,
        1.0 if _bool(row.get("low_adjacency_signal")) else 0.0,
        _float(row.get("cross_reference_signal")),
        _float(row.get("code_internal_order_changed")),
        _float(row.get("code_component_crossings")),
        _float(row.get("tool_code_dependency_violation")),
        _float(row.get("expected_prefix_gain")) / 1000.0,
        _float(row.get("context_segment_tokens")) / 1000.0,
    ]


def _sigmoid(value: float) -> float:
    if value < -60:
        return 0.0
    if value > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def train_logistic(xs: list[list[float]], ys: list[int], steps: int = 1200, lr: float = 0.03, l2: float = 0.01) -> list[float]:
    if not xs:
        return [0.0] * (len(FEATURE_NAMES) + 1)
    weights = [0.0] * (len(xs[0]) + 1)
    pos = max(1, sum(ys))
    neg = max(1, len(ys) - pos)
    pos_weight = neg / pos
    for _ in range(steps):
        grad = [0.0] * len(weights)
        for x, y in zip(xs, ys):
            z = weights[0] + sum(w * v for w, v in zip(weights[1:], x))
            p = _sigmoid(z)
            scale = pos_weight if y else 1.0
            err = (p - y) * scale
            grad[0] += err
            for i, value in enumerate(x, start=1):
                grad[i] += err * value
        n = max(1, len(xs))
        weights[0] -= lr * grad[0] / n
        for i in range(1, len(weights)):
            weights[i] -= lr * ((grad[i] / n) + l2 * weights[i])
    return weights


def predict(weights: list[float], x: list[float]) -> float:
    return _sigmoid(weights[0] + sum(w * v for w, v in zip(weights[1:], x)))


def choose_threshold(rows: list[dict[str, Any]], target_false_safe: float = 0.03) -> float:
    risks = sorted({_float(row["predicted_risk"]) for row in rows})
    if not risks:
        return 1.0
    best = min(risks) - 1e-12
    best_gain = 0.0
    best_coverage = 0.0
    for threshold in risks + [1.0]:
        accepted = [row for row in rows if _float(row["predicted_risk"]) <= threshold]
        if not accepted:
            continue
        false_safe_count = sum(_bool(row["unsafe_quality_drop"]) for row in accepted)
        upper = _wilson_upper(false_safe_count, len(accepted))
        safe = [row for row in rows if not _bool(row["unsafe_quality_drop"])]
        coverage = sum((not _bool(row["unsafe_quality_drop"])) and _float(row["predicted_risk"]) <= threshold for row in rows) / max(1, len(safe))
        retained_gain = sum(
            max(0.0, _float(row.get("expected_prefix_gain")))
            for row in accepted
            if not _bool(row.get("unsafe_quality_drop"))
        )
        if upper <= target_false_safe and (retained_gain, coverage, -threshold) > (best_gain, best_coverage, -best):
            best = threshold
            best_gain = retained_gain
            best_coverage = coverage
    return best


def _wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    phat = k / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return (center + margin) / denom


def calibrate(
    features: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    target_false_safe: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_key = {
        (str(row.get("sample_key", "")), str(row.get("candidate_id", ""))): row
        for row in features
    }
    labeled = []
    for label in labels:
        key = (str(label.get("sample_key", "")), str(label.get("candidate_id", "")))
        feature = by_key.get(key)
        if not feature:
            continue
        row = {**feature, **label}
        labeled.append(row)
    train = [row for row in labeled if str(row.get("partition")) == "calibration"]
    xs = [_feature_vector(row) for row in train]
    ys = [1 if _bool(row.get("unsafe_quality_drop")) else 0 for row in train]
    weights = train_logistic(xs, ys)
    scored = []
    for row in labeled:
        risk = predict(weights, _feature_vector(row))
        out = dict(row)
        out["predicted_risk"] = risk
        scored.append(out)
    threshold = choose_threshold([row for row in scored if str(row.get("partition")) == "calibration"], target_false_safe)
    output = []
    for row in scored:
        fallback = _float(row["predicted_risk"]) > threshold
        unsafe = _bool(row.get("unsafe_quality_drop"))
        record = {
            "sample_key": row.get("sample_key", ""),
            "candidate_id": row.get("candidate_id", ""),
            "order_hash": row.get("order_hash", ""),
            "prompt_hash": row.get("prompt_hash", ""),
            "partition": row.get("partition", ""),
            "dataset": row.get("dataset", ""),
            "task": row.get("task", ""),
            "sample_id": row.get("sample_id", ""),
            "candidate_policy": row.get("candidate_policy", "contractkv-caposc"),
            "unsafe_quality_drop": unsafe,
            "quality_drop_vs_raw": row.get("quality_drop_vs_raw", ""),
            "predicted_risk": round(_float(row["predicted_risk"]), 6),
            "qc_fallback_v2": fallback,
            "safe_optimization_v2": (not fallback) and (not unsafe),
            "false_safe_v2": (not fallback) and unsafe,
            "claim_boundary": "Candidate-level QC-v2 calibration over completed paired labels; task-sanity labels, not official benchmark scoring.",
        }
        output.append(record)
    calibration_rows = [row for row in output if str(row.get("partition")) == "calibration"]
    accepted = [row for row in calibration_rows if not _bool(row.get("qc_fallback_v2"))]
    false_safe_count = sum(_bool(row.get("false_safe_v2")) for row in accepted)
    summary_rows = summarize(output, threshold)
    held = next((row for row in summary_rows if row["split"] == "held_out_quality"), {})
    model = {
        "intercept": weights[0],
        "weights": dict(zip(FEATURE_NAMES, weights[1:])),
        "threshold": threshold,
        "threshold_objective": "maximize_safe_expected_prefix_gain_subject_to_wilson95_upper",
        "target_false_safe_wilson95_upper": target_false_safe,
        "calibration_false_safe_wilson95_upper": _wilson_upper(false_safe_count, len(accepted)),
        "deployment_gate_open": bool(
            held
            and _float(held.get("false_safe_wilson95_upper")) <= target_false_safe
            and _float(held.get("safe_optimization_coverage")) >= 0.80
            and _float(held.get("unsafe_caught_rate")) >= 0.80
        ),
        "deployment_gate_requirements": {
            "held_out_false_safe_wilson95_upper_lte": target_false_safe,
            "held_out_safe_optimization_coverage_gte": 0.80,
            "held_out_unsafe_caught_rate_gte": 0.80,
        },
    }
    return output, summary_rows, model


def summarize(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {"all": rows}
    for row in rows:
        groups.setdefault(str(row.get("partition", "")), []).append(row)
    out = []
    for split, group in sorted(groups.items()):
        unsafe = [row for row in group if _bool(row.get("unsafe_quality_drop"))]
        accepted = [row for row in group if not _bool(row.get("qc_fallback_v2"))]
        safe = [row for row in group if not _bool(row.get("unsafe_quality_drop"))]
        false_safe_count = sum(_bool(row.get("false_safe_v2")) for row in group)
        drops = [_float(row.get("quality_drop_vs_raw")) for row in group]
        out.append(
            {
                "split": split,
                "requests": len(group),
                "unsafe_requests": len(unsafe),
                "threshold": round(threshold, 6),
                "fallback_rate": round(sum(_bool(row.get("qc_fallback_v2")) for row in group) / max(1, len(group)), 6),
                "false_safe_rate": round(false_safe_count / max(1, len(accepted)), 6),
                "false_safe_wilson95_upper": round(_wilson_upper(false_safe_count, len(accepted)), 6),
                "safe_optimization_coverage": round(sum(_bool(row.get("safe_optimization_v2")) for row in group) / max(1, len(safe)), 6),
                "unsafe_caught_rate": round(sum(_bool(row.get("qc_fallback_v2")) for row in unsafe) / max(1, len(unsafe)), 6),
                "mean_quality_drop": round(sum(drops) / max(1, len(drops)), 6),
                "claim_boundary": "QC-v2 is calibrated on calibration split and evaluated on held-out labels; Wilson upper bound reports finite-sample risk.",
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("results/end_to_end/phase14c_full_pool_qc_features_v0.csv"))
    parser.add_argument("--labels", type=Path, default=Path("results/end_to_end/phase14c_full_pool_quality_labels_v1.csv"))
    parser.add_argument("--target-false-safe", type=float, default=0.03)
    parser.add_argument("--scores-output", type=Path, default=Path("results/end_to_end/phase14r_qc_v2_scores.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/end_to_end/phase14r_qc_v2_summary.csv"))
    parser.add_argument("--model-output", type=Path, default=Path("results/end_to_end/phase14r_qc_v2_model.json"))
    args = parser.parse_args()
    scores, summary, model = calibrate(_rows(args.features), _rows(args.labels), args.target_false_safe)
    write_csv(args.scores_output, scores, SCORE_FIELDS)
    write_csv(args.summary_output, summary, SUMMARY_FIELDS)
    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    args.model_output.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    print(f"qc_v2_scores={len(scores)} summary_rows={len(summary)} threshold={model['threshold']:.6f}")
    return 0 if scores else 1


if __name__ == "__main__":
    raise SystemExit(main())
