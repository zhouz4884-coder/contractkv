#!/usr/bin/env python3
"""Aggregate five-repeat D0/D1/D2 real-task open-loop serving cells."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


POLICIES = ("D0-native-apc", "D1-frozen-safe", "D2-template-contractkv")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def cell_dir(root: Path, policy: str, repeat: int) -> Path:
    return root / f"qwen-r{repeat}-{policy}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--repeats", default="1,2,3,4,5")
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args(); repeats = [int(value) for value in args.repeats.split(",")]
    summaries: dict[tuple[str, int, float], dict[str, Any]] = {}; raw_rows: dict[tuple[str, int], dict[str, Any]] = {}
    rows_by_cell: dict[tuple[str, int], list[dict[str, Any]]] = {}
    registration_by_cell: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for policy in POLICIES:
        for repeat in repeats:
            directory = cell_dir(args.directory, policy, repeat)
            rows = load_jsonl(directory / "raw.jsonl")
            rows_by_cell[(policy, repeat)] = rows
            registration_by_cell[(policy, repeat)] = load_jsonl(directory / "registration.jsonl")
            for row in load_jsonl(directory / "summary.jsonl"):
                summaries[(policy, repeat, number(row["slo_ttft_ms"]))] = row
            if policy == POLICIES[0]:
                for row in rows:
                    raw_rows[(str(row["session_id"]), int(row["turn_id"]), repeat)] = row
    aggregate = []
    for policy in POLICIES:
        for slo in sorted({key[2] for key in summaries}):
            repeat_rows = [summaries[(policy, repeat, slo)] for repeat in repeats]
            paired_deltas = []
            if policy != POLICIES[0]:
                for repeat in repeats:
                    for row in rows_by_cell[(policy, repeat)]:
                        baseline = raw_rows[(str(row["session_id"]), int(row["turn_id"]), repeat)]
                        if row.get("success") is True and baseline.get("success") is True:
                            paired_deltas.append(number(row.get("task_score")) - number(baseline.get("task_score")))
            registrations = [row for repeat in repeats for row in registration_by_cell[(policy, repeat)]]
            numeric_fields = (
                "completion_rate", "drop_rate", "registration_wall_s", "replay_wall_s", "end_to_end_wall_s",
                "mean_ttft_ms", "p95_ttft_ms", "p99_ttft_ms", "mean_tpot_ms", "mean_latency_ms",
                "mean_task_score", "replay_slo_goodput_rps", "end_to_end_slo_goodput_rps",
                "mean_prompt_tokens", "mean_prefix_hit_tokens", "mean_new_prefill_tokens", "metric_join_rate",
                "actual_verifier_endpoint_calls", "transaction_commits", "registration_failures",
                "scope_invalid_admissions", "certificate_binding_failures", "raw_fallback_rate",
            )
            row: dict[str, Any] = {
                "policy": policy, "slo_ttft_ms": slo, "fresh_process_repeats": len(repeats),
                "offered_requests_per_repeat": repeat_rows[0]["offered_requests"],
                "paired_quality_requests": len(paired_deltas),
                "mean_task_score_delta_vs_d0": statistics.fmean(paired_deltas) if paired_deltas else 0.0,
                "quality_drop_gt_0_03_rate": sum(delta < -.03 for delta in paired_deltas) / max(1, len(paired_deltas)),
                "quality_drop_gt_0_03_count": sum(delta < -.03 for delta in paired_deltas),
                "signed_certificates": sum(bool(item.get("signed_binding")) for item in registrations),
                "same_engine_verifier_transport": sum(str(item.get("transport", "")).startswith("same_vllm") for item in registrations),
            }
            for field in numeric_fields:
                values = [number(item.get(field)) for item in repeat_rows]
                row[field] = statistics.fmean(values)
                row[f"{field}_repeat_min"] = min(values); row[f"{field}_repeat_max"] = max(values)
            aggregate.append(row)
    payload = {
        "schema_version": "contractkv.tsc.real-task-open-loop-summary.v1",
        "model": "Qwen3-8B", "policies": list(POLICIES), "fresh_process_repeats": len(repeats),
        "rows": aggregate,
        "gates": {
            "all_completion_100pct": all(row["completion_rate"] == 1.0 for row in aggregate),
            "d2_same_engine_verifier": all(row["same_engine_verifier_transport"] > 0 for row in aggregate if row["policy"] == POLICIES[2]),
            "d2_zero_scope_invalid": all(row["scope_invalid_admissions"] == 0 for row in aggregate if row["policy"] == POLICIES[2]),
            "d2_zero_binding_failures": all(row["certificate_binding_failures"] == 0 for row in aggregate if row["policy"] == POLICIES[2]),
            "d2_zero_quality_drop_gt_0_03": all(row["quality_drop_gt_0_03_count"] == 0 for row in aggregate if row["policy"] == POLICIES[2]),
        },
        "claim_boundary": "Registration and in-engine verifier wall time are charged to end-to-end goodput. Quality deltas use the frozen real-task scorer and matched session/turn/repeat outputs.",
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fields = sorted({key for row in aggregate for key in row})
    with args.csv_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(aggregate)
    print(json.dumps(payload, indent=2)); return 0 if all(payload["gates"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
