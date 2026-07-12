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


def summarize(cell: str, result_dir: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    raw_files = sorted(result_dir.glob(f"phase18_{cell.lower()}_seed_*_raw.csv"))
    rows = [row for path in raw_files for row in read_csv(path)]
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
    summary = {
        "cell": cell,
        "seeds": len(seeds),
        "foreground_requests_per_condition": len(foreground["live_verifier"]),
        "verifier_requests": len(verifiers),
        "baseline_p95_ttft_ms": p95["baseline"],
        "live_p95_ttft_ms": p95["live_verifier"],
        "pooled_p95_penalty_ms": p95["live_verifier"] - p95["baseline"],
        "mean_per_seed_p95_penalty_ms": statistics.mean(per_seed.values()),
        "median_per_seed_p95_penalty_ms": statistics.median(per_seed.values()),
        "max_per_seed_p95_penalty_ms": max(per_seed.values()),
        "per_seed_p95_penalty_ms": json.dumps(per_seed, sort_keys=True),
        "foreground_success_rate": sum(truth(row["success"])
                                       for row in foreground["live_verifier"])
        / max(len(foreground["live_verifier"]), 1),
        "verifier_success_rate": sum(truth(row["success"]) for row in verifiers)
        / max(len(verifiers), 1),
        "pending_futures": sum(int(item.get("pending_futures", 0))
                               for item in router),
        "orphan_outputs": sum(int(item.get("orphan_outputs", 0))
                              for item in router),
        "duplicate_outputs": sum(int(item.get("duplicate_outputs", 0))
                                 for item in router),
        "gate_pass": (
            all(truth(row["success"]) for row in foreground["live_verifier"])
            and all(truth(row["success"]) for row in verifiers)
            and sum(int(item.get("pending_futures", 0)) for item in router) == 0
            and sum(int(item.get("orphan_outputs", 0)) for item in router) == 0
            and max(per_seed.values()) <= 10.0
        ),
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
    all_rows: list[dict[str, str]] = []
    summaries = []
    for cell in args.cells:
        rows, summary = summarize(cell.upper(), args.result_dir)
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
