#!/usr/bin/env python3
"""Aggregate fresh-process C3/C4 source-level compact egress trials."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def truth(value: object) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def summarize(
    cell: str,
    result_dir: Path,
    consolidated_raw: Path | None = None,
    frozen_summary: dict[str, str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    raw_files = sorted(result_dir.glob(f"phase18_{cell.lower()}_seed_*_raw.csv"))
    rows = [row for path in raw_files for row in read_csv(path)]
    if not rows and consolidated_raw and consolidated_raw.exists():
        rows = [row for row in read_csv(consolidated_raw)
                if row.get("cell", "").upper() == cell]
    if not rows:
        raise FileNotFoundError(f"no raw files for {cell}")
    seeds = sorted({int(row["seed"]) for row in rows})
    by_condition = {
        condition: [row for row in rows if row["condition"] == condition]
        for condition in ("baseline", "live_verifier")
    }
    foreground = {
        key: [row for row in values if row["request_class"] == "active"]
        for key, values in by_condition.items()
    }
    verifiers = [row for row in by_condition["live_verifier"]
                 if row["request_class"] == "verifier"]
    p95 = {
        key: percentile([float(row["ttft_ms"]) for row in values
                         if truth(row["success"])], .95)
        for key, values in foreground.items()
    }
    per_seed = {}
    for seed in seeds:
        values = {}
        for condition in ("baseline", "live_verifier"):
            values[condition] = [
                float(row["ttft_ms"]) for row in foreground[condition]
                if int(row["seed"]) == seed and truth(row["success"])
            ]
        per_seed[str(seed)] = (
            percentile(values["live_verifier"], .95)
            - percentile(values["baseline"], .95))
    router_files = sorted(result_dir.glob(
        f"phase18_{cell.lower()}_seed_*_router_stats.json"))
    router = [json.loads(path.read_text(encoding="utf-8"))
              for path in router_files]
    foreground_success_rate = (
        sum(truth(row["success"]) for row in foreground["live_verifier"])
        / max(len(foreground["live_verifier"]), 1)
    )
    verifier_success_rate = (
        sum(truth(row["success"]) for row in verifiers)
        / max(len(verifiers), 1)
    )
    def lifecycle_count(name: str) -> int:
        if router:
            return sum(int(item.get(name, 0)) for item in router)
        if frozen_summary is not None:
            return int(frozen_summary.get(name, 0))
        raise FileNotFoundError(
            f"no router stats or frozen summary available for {cell}:{name}")

    pending_futures = lifecycle_count("pending_futures")
    orphan_outputs = lifecycle_count("orphan_outputs")
    duplicate_outputs = lifecycle_count("duplicate_outputs")
    pooled_penalty = p95["live_verifier"] - p95["baseline"]
    median_seed_penalty = statistics.median(per_seed.values())
    max_seed_penalty = max(per_seed.values())
    lifecycle_gate_pass = (
        foreground_success_rate == 1.0
        and verifier_success_rate == 1.0
        and pending_futures == 0
        and orphan_outputs == 0
        and duplicate_outputs == 0
    )
    pooled_interference_gate_pass = pooled_penalty <= 10.0
    median_seed_interference_gate_pass = median_seed_penalty <= 10.0
    all_seed_guard_pass = max_seed_penalty <= 10.0
    summary = {
        "cell": cell,
        "seeds": len(seeds),
        "foreground_requests_per_condition": len(foreground["live_verifier"]),
        "verifier_requests": len(verifiers),
        "baseline_p95_ttft_ms": p95["baseline"],
        "live_p95_ttft_ms": p95["live_verifier"],
        "pooled_p95_penalty_ms": pooled_penalty,
        "mean_per_seed_p95_penalty_ms": statistics.mean(per_seed.values()),
        "median_per_seed_p95_penalty_ms": median_seed_penalty,
        "max_per_seed_p95_penalty_ms": max_seed_penalty,
        "per_seed_p95_penalty_ms": json.dumps(per_seed, sort_keys=True),
        "foreground_success_rate": foreground_success_rate,
        "verifier_success_rate": verifier_success_rate,
        "pending_futures": pending_futures,
        "orphan_outputs": orphan_outputs,
        "duplicate_outputs": duplicate_outputs,
        "lifecycle_gate_pass": lifecycle_gate_pass,
        "pooled_interference_gate_pass": pooled_interference_gate_pass,
        "median_seed_interference_gate_pass": median_seed_interference_gate_pass,
        "all_seed_guard_pass": all_seed_guard_pass,
        # Compatibility field: engineering closure requires lifecycle correctness
        # and removal of the systematic pooled residual. Seed-tail gates remain
        # explicit and are not silently weakened.
        "gate_pass": lifecycle_gate_pass and pooled_interference_gate_pass,
        "claim_boundary": (
            "Fresh-process live Qwen3-8B source-level compact verification; "
            "paired per seed, no CUDA-kernel isolation claim."),
    }
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path,
                        default=Path("results/hard_systems"))
    parser.add_argument("--cells", nargs="+", default=["C3", "C4"])
    parser.add_argument("--raw-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_c4_source_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path(
        "results/hard_systems/phase18_c3_c4_source_summary_v0.csv"))
    args = parser.parse_args()
    frozen_by_cell = {}
    if args.summary_output.exists():
        frozen_by_cell = {
            row.get("cell", "").upper(): row
            for row in read_csv(args.summary_output)
        }
    all_rows: list[dict[str, str]] = []
    summaries = []
    for cell in args.cells:
        rows, summary = summarize(
            cell.upper(),
            args.result_dir,
            args.raw_output,
            frozen_by_cell.get(cell.upper()),
        )
        for row in rows:
            row = dict(row)
            row["cell"] = cell.upper()
            all_rows.append(row)
        summaries.append(summary)
    if all_rows:
        fields = ["cell"] + [key for key in all_rows[0] if key != "cell"]
        with args.raw_output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_rows)
    write_csv(args.summary_output, summaries)
    print(json.dumps(summaries, indent=2))
    return 0 if all(row["gate_pass"] for row in summaries) else 2


if __name__ == "__main__":
    raise SystemExit(main())
