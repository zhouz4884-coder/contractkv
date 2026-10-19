#!/usr/bin/env python3
"""Compute transfer residual stall over slack and KV proxy sizes."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


SLACK_BUCKETS_MS = [0, 10, 50, 100, 200, 500]
COPY_POLICIES = ["Critical-Path-Copy", "Slack-Window-Copy", "Joint-Selected-Copy"]

FIELDS = [
    "copy_policy",
    "kv_size_mb",
    "tool_slack_ms",
    "copy_ms",
    "residual_stall_ms",
    "hidden_transfer_ms",
    "hidden_fraction",
    "interpretation",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def residual_stall(copy_ms: float, slack_ms: float, mode: str) -> float:
    if mode == "Critical-Path-Copy":
        return copy_ms
    if mode in {"Slack-Window-Copy", "Joint-Selected-Copy"}:
        return max(0.0, copy_ms - slack_ms)
    return 0.0


def _interpret(size_mb: int, stall: float) -> str:
    if stall == 0:
        return "fully_hidden_by_slack"
    if size_mb <= 256:
        return "small_transfer_partially_exposed"
    return "large_transfer_residual_stall"


def load_copy_sizes(path: Path) -> dict[int, float]:
    rows = read_csv(path)
    result = {}
    for row in rows:
        if row.get("mode") != "copy_on_critical_path":
            continue
        result[int(float(row["kv_size_mb"]))] = float(row["copy_ms"])
    return result


def sweep_tool_slack(
    copy_sizes_ms: dict[int, float],
    slack_buckets: list[int] | None = None,
    policies: list[str] | None = None,
) -> list[dict[str, Any]]:
    slack_buckets = slack_buckets or SLACK_BUCKETS_MS
    policies = policies or COPY_POLICIES
    rows = []
    for size_mb, copy_ms in sorted(copy_sizes_ms.items()):
        for slack in slack_buckets:
            for policy in policies:
                stall = residual_stall(copy_ms, slack, policy)
                hidden = max(0.0, copy_ms - stall)
                rows.append(
                    {
                        "copy_policy": policy,
                        "kv_size_mb": size_mb,
                        "tool_slack_ms": slack,
                        "copy_ms": round(copy_ms, 6),
                        "residual_stall_ms": round(stall, 6),
                        "hidden_transfer_ms": round(hidden, 6),
                        "hidden_fraction": round(hidden / copy_ms, 6) if copy_ms > 0 else 0.0,
                        "interpretation": _interpret(size_mb, stall),
                    }
                )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy-proxy", type=Path, default=Path("results/runtime/tool_slack_copy_proxy_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/workload/tool_slack_sensitivity_v0.csv"))
    parser.add_argument("--slack-buckets-ms", default="0,10,50,100,200,500")
    args = parser.parse_args()
    slack = [int(item) for item in args.slack_buckets_ms.split(",") if item]
    rows = sweep_tool_slack(load_copy_sizes(args.copy_proxy), slack)
    write_csv(args.output, rows)
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
