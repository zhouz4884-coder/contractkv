#!/usr/bin/env python3
"""Generate a fresh-server prefix-cache isolation replication plan."""

from __future__ import annotations

import argparse
import csv
import itertools
import random
from pathlib import Path


FIELDS = [
    "replicate_id",
    "seed",
    "run_order",
    "policy",
    "requires_fresh_server",
    "requires_fresh_prefix_cache",
    "metrics_log",
    "claim_boundary",
]


def build_plan(policies: list[str], repeats: int, seed: int, metrics_dir: str) -> list[dict[str, str]]:
    rng = random.Random(seed)
    permutations = list(itertools.permutations(policies))
    rows: list[dict[str, str]] = []
    for replicate in range(repeats):
        order = list(permutations[replicate % len(permutations)])
        rng.shuffle(order)
        for index, policy in enumerate(order):
            rows.append(
                {
                    "replicate_id": str(replicate),
                    "seed": str(seed + replicate),
                    "run_order": str(index),
                    "policy": policy,
                    "requires_fresh_server": "true",
                    "requires_fresh_prefix_cache": "true",
                    "metrics_log": f"{metrics_dir.rstrip('/')}/phase14r_prefix_{replicate}_{index}_{policy}.jsonl",
                    "claim_boundary": "Execution plan only; each row must run on a fresh vLLM process/cache before claiming isolated prefix-cache benefit.",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policies", default="raw-order,static-posc,cache-aware-posc")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=14014)
    parser.add_argument("--metrics-dir", default="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/prefix_cache")
    parser.add_argument("--output", type=Path, default=Path("results/prefix_cache/phase14r_prefix_isolation_plan.csv"))
    args = parser.parse_args()
    policies = [item.strip() for item in args.policies.split(",") if item.strip()]
    rows = build_plan(policies, args.repeats, args.seed, args.metrics_dir)
    write_csv(args.output, rows)
    print(f"isolation_plan_rows={len(rows)} repeats={args.repeats} policies={','.join(policies)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
