#!/usr/bin/env python3
"""Summarize frozen Mistral c=1/c=4 load-extension outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(.95 * len(ordered)) - 1)]


def mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) not in {"", None}]
    return statistics.fmean(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", action="append", required=True, help="concurrency:policy:path")
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--slo-output", type=Path, required=True)
    args = parser.parse_args()
    cells: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for item in args.cell:
        conc, policy, path = item.split(":", 2)
        cells[(int(conc), policy)] = load(Path(path))
    summaries = []
    slo_rows = []
    for (conc, policy), rows in cells.items():
        future = [row for row in rows if row.get("row_type") == "future" and row.get("success") is True]
        ttft = [float(row.get("ttft_ms", 0)) for row in future]
        batches: dict[str, float] = {}
        for row in future:
            batch = str(row.get("batch_id") or row.get("request_id"))
            batches[batch] = max(batches.get(batch, 0.0), float(row.get("batch_wall_ms", 0) or 0))
        wall_s = sum(batches.values()) / 1000.0
        summaries.append({"concurrency": conc, "policy": policy,
                          "completed_requests": len(future),
                          "completion_rate": len(future) / 450.0,
                          "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
                          "p95_ttft_ms": p95(ttft),
                          "mean_tpot_ms": mean(future, "tpot_ms"),
                          "mean_new_prefill_tokens": mean(future, "new_prefill_tokens"),
                          "mean_prefix_hit_tokens": mean(future, "prefix_hit_tokens"),
                          "wall_time_s": wall_s})
        for slo in (500, 750, 1000, 1250, 1500, 2000):
            compliant = sum(value <= slo for value in ttft)
            slo_rows.append({"concurrency": conc, "policy": policy, "slo_ms": slo,
                             "slo_compliant": compliant,
                             "slo_compliant_fraction": compliant / max(1, len(ttft)),
                             "slo_compliant_req_per_sec": compliant / max(wall_s, 1e-9)})
    index = {(row["concurrency"], row["policy"]): row for row in summaries}
    for conc in sorted({key[0] for key in cells}):
        raw = index[(conc, "raw-order")]
        contract = index[(conc, "contractkv-full")]
        contract["mean_ttft_reduction_vs_raw"] = (
            raw["mean_ttft_ms"] - contract["mean_ttft_ms"]) / max(raw["mean_ttft_ms"], 1.0)
        contract["new_prefill_reduction_vs_raw"] = (
            raw["mean_new_prefill_tokens"] - contract["mean_new_prefill_tokens"]) / max(raw["mean_new_prefill_tokens"], 1.0)
    for path, rows in ((args.summary_output, summaries), (args.slo_output, slo_rows)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            fields = sorted({key for row in rows for key in row})
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
