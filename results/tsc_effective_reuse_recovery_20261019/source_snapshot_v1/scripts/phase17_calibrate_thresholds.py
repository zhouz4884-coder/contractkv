#!/usr/bin/env python3
"""Select Phase 17 verifier thresholds on calibration only, then freeze."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def quantile(values: list[float], q: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    return values[min(len(values) - 1, int(round((len(values) - 1) * q)))]


def candidate_values(values: list[float], reverse: bool = False) -> list[float]:
    finite = [value for value in values if math.isfinite(value)]
    points = {quantile(finite, index / 20) for index in range(21)}
    points.add(-1e9 if not reverse else 1e9)
    return sorted(points, reverse=reverse)


def base_valid(row: dict[str, str]) -> bool:
    return (
        row.get("error_type") == "none"
        and row.get("raw_finish_reason") == "stop"
        and int(float(row.get("answer_tokens", 0) or 0)) > 0
        and int(float(row.get("top1_matches", 0) or 0)) == int(float(row.get("answer_tokens", 0) or 0))
        and truth(row.get("stop_consistent"))
    )


def certified(row: dict[str, str], thresholds: tuple[float, float, float]) -> bool:
    raw, absolute, drop = thresholds
    return base_valid(row) and number(row.get("raw_margin_q05")) >= raw and number(row.get("candidate_margin_q05")) >= absolute and number(row.get("degradation_q95")) <= drop


def metrics(rows: list[dict[str, str]], thresholds: tuple[float, float, float]) -> dict[str, Any]:
    safe = [row for row in rows if not truth(row.get("unsafe_quality_drop"))]
    unsafe = [row for row in rows if truth(row.get("unsafe_quality_drop"))]
    safe_cert = [row for row in safe if certified(row, thresholds)]
    unsafe_cert = [row for row in unsafe if certified(row, thresholds)]
    total_gain = sum(number(row.get("expected_prefix_gain"), 0) for row in safe)
    retained = sum(number(row.get("expected_prefix_gain"), 0) for row in safe_cert)
    return {
        "candidates": len(rows), "safe": len(safe), "unsafe": len(unsafe),
        "safe_certified": len(safe_cert), "unsafe_certified": len(unsafe_cert),
        "safe_coverage": len(safe_cert) / max(len(safe), 1),
        "unsafe_rejection_rate": 1 - len(unsafe_cert) / max(len(unsafe), 1),
        "retained_prefix_gain_fraction": retained / max(total_gain, 1),
        "certified_retained_prefix_gain": retained,
    }


def wilson_upper_zero(n: int, z: float = 1.96) -> float:
    return z * z / (n + z * z) if n else 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--threshold-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    calibration = [row for row in rows if row.get("partition") == "calibration"]
    heldout = [row for row in rows if row.get("partition") == "held_out_quality"]
    raw_values = candidate_values([number(row.get("raw_margin_q05")) for row in calibration])
    abs_values = candidate_values([number(row.get("candidate_margin_q05")) for row in calibration])
    drop_values = candidate_values([number(row.get("degradation_q95")) for row in calibration], reverse=True)
    feasible = []
    for thresholds in itertools.product(raw_values, abs_values, drop_values):
        result = metrics(calibration, thresholds)
        if result["unsafe_certified"] == 0 and result["safe_coverage"] >= .5 and result["retained_prefix_gain_fraction"] >= .5:
            feasible.append((result["certified_retained_prefix_gain"], result["safe_coverage"], thresholds, result))
    if feasible:
        _, _, thresholds, calibration_metrics = max(feasible, key=lambda value: (value[0], value[1]))
        status = "feasible"
    else:
        thresholds = (1e9, 1e9, -1e9)
        calibration_metrics = metrics(calibration, thresholds)
        status = "no_feasible_threshold_fail_closed"
    heldout_metrics = metrics(heldout, thresholds)
    threshold_payload = {
        "status": status, "tau_raw": thresholds[0], "tau_abs": thresholds[1], "tau_drop": thresholds[2],
        "selected_on": "calibration_only", "objective": "max_certified_retained_prefix_gain",
        "constraints": {"calibration_unsafe_certified": 0, "safe_coverage_min": .5, "retained_gain_min": .5},
    }
    args.threshold_output.parent.mkdir(parents=True, exist_ok=True)
    args.threshold_output.write_text(json.dumps(threshold_payload, indent=2) + "\n", encoding="utf-8")
    summary = []
    for split, result in [("calibration", calibration_metrics), ("held_out_quality", heldout_metrics)]:
        summary.append({
            "split": split, **result,
            "tau_raw": thresholds[0], "tau_abs": thresholds[1], "tau_drop": thresholds[2],
            "zero_observed_unsafe_wilson_upper_95": wilson_upper_zero(result["unsafe"] - result["unsafe_certified"]) if result["unsafe_certified"] == 0 else "",
            "threshold_status": status,
            "claim_boundary": "Thresholds selected on calibration only; held-out is evaluation, and 34 unsafe cases cannot establish a 3% risk bound.",
        })
    fields = list(summary[0])
    with args.summary_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(summary)
    print(json.dumps({"thresholds": threshold_payload, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
