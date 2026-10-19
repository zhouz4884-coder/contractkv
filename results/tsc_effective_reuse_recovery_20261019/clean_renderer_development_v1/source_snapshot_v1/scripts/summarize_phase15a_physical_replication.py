#!/usr/bin/env python3
"""Aggregate fresh-process Phase 15A physical-sharing replication cells."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile


FIELDS = [
    "shared_target_tokens", "sessions", "policy", "seeds", "fresh_process_cells",
    "completed_requests", "completion_rate", "quality_sanity_rate",
    "content_signature_match", "mean_ttft_ms", "p95_ttft_ms",
    "mean_prefix_hit_tokens", "mean_dedup_factor", "mean_effective_dedup_factor",
    "peak_concurrent_dedup_factor", "min_concurrent_refcount_match_rate",
    "mean_used_block_high_water", "mean_minimum_free_blocks", "p95_compiler_overhead_ms",
    "claim_boundary",
]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def load_raw(cell_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(cell_dir.glob("*_raw.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_cell"] = str(path)
                seed = re.search(r"_s(\d+)_", path.name)
                row["_seed"] = seed.group(1) if seed else ""
                rows.append(row)
    return rows


def load_summaries(cell_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(cell_dir.glob("*_summary.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_cell"] = str(path)
                seed = re.search(r"_s(\d+)_", path.name)
                row["_seed"] = seed.group(1) if seed else ""
                rows.append(row)
    return rows


def summarize(raw: list[dict[str, str]], cells: list[dict[str, str]]) -> list[dict[str, Any]]:
    raw_groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    cell_groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    signature_by_seed: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in raw:
        key = (row["shared_target_tokens"], row["sessions"], row["policy"])
        raw_groups[key].append(row)
        signature_by_seed[(row["_seed"], row["shared_target_tokens"], row["sessions"])].add(row["content_multiset_sha256"])
    for row in cells:
        cell_groups[(row["shared_target_tokens"], row["sessions"], row["policy"])].append(row)
    output = []
    for key, group in sorted(raw_groups.items()):
        tokens, sessions, policy = key
        summaries = cell_groups[key]
        ttft = [number(row["ttft_ms"]) for row in group if truth(row["success"])]
        # Warm fan-out includes one policy-neutral primer plus one unique
        # observation per concurrently measured session.
        signatures_match = all(
            len(values) == int(sessions) + 1
            for (seed, current_tokens, current_sessions), values in signature_by_seed.items()
            if current_tokens == tokens and current_sessions == sessions
        )
        output.append({
            "shared_target_tokens": tokens, "sessions": sessions, "policy": policy,
            "seeds": ",".join(sorted({row["_seed"] for row in summaries})),
            "fresh_process_cells": len(summaries), "completed_requests": sum(int(row["completed_requests"]) for row in summaries),
            "completion_rate": statistics.mean(number(row["completion_rate"]) for row in summaries),
            "quality_sanity_rate": statistics.mean(number(row["quality_sanity_rate"]) for row in summaries),
            "content_signature_match": signatures_match,
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0, "p95_ttft_ms": percentile(ttft, .95),
            "mean_prefix_hit_tokens": statistics.mean(number(row["prefix_hit_tokens"]) for row in group),
            "mean_dedup_factor": statistics.mean(number(row["dedup_factor"]) for row in summaries),
            "mean_effective_dedup_factor": statistics.mean(number(row["effective_dedup_factor"]) for row in summaries),
            "peak_concurrent_dedup_factor": max((number(row["peak_concurrent_dedup_factor"]) for row in summaries), default=0.0),
            "min_concurrent_refcount_match_rate": min((number(row["peak_concurrent_refcount_match_rate"]) for row in summaries), default=0.0),
            "mean_used_block_high_water": statistics.mean(number(row["used_block_high_water"]) for row in summaries),
            "mean_minimum_free_blocks": statistics.mean(number(row["minimum_free_blocks"]) for row in summaries),
            "p95_compiler_overhead_ms": 0.0,
            "claim_boundary": "Fresh process and empty prefix cache per cell; concurrent sharing uses same-snapshot active block tables and refcounts.",
        })
    return output


def write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    raw, cells = load_raw(args.cell_dir), load_summaries(args.cell_dir)
    if not raw or not cells:
        raise SystemExit("no physical replication cell results")
    write(args.raw_output, raw, list(raw[0]))
    write(args.summary_output, summarize(raw, cells), FIELDS)
    print(f"phase15a_physical_rows={len(raw)} cells={len(cells)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
