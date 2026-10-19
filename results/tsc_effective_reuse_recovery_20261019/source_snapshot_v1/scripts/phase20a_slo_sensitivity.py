#!/usr/bin/env python3
"""Recompute frozen Phase 19B SLO curves without rerunning generation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


FIELDS = ["policy", "load_tier", "concurrency", "slo_ms", "requests",
          "compliant_requests", "compliant_req_per_sec", "absolute_gain_vs_raw",
          "multiplicative_gain_vs_raw", "claim_boundary"]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--slo-ms", default="500,750,1000,1250,1500,2000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); rows = load(args.input)
    future = [row for row in rows if row.get("row_type") == "future" and row.get("success") is True]
    groups = defaultdict(list)
    for row in future: groups[(str(row["policy"]), str(row["load_tier"]))].append(row)
    output = []
    for slo in [float(value) for value in args.slo_ms.split(",")]:
        interim = {}
        for key, group in groups.items():
            batches = {str(row["batch_id"]): float(row["batch_wall_ms"]) for row in group}
            compliant = sum(float(row["ttft_ms"]) <= slo for row in group)
            rate = compliant / max(.001, sum(batches.values()) / 1000.0)
            interim[key] = (group, compliant, rate)
        for key, (group, compliant, rate) in sorted(interim.items()):
            raw_rate = interim[("raw-order", key[1])][2]
            output.append({
                "policy": key[0], "load_tier": key[1], "concurrency": group[0]["concurrency"],
                "slo_ms": slo, "requests": len(group), "compliant_requests": compliant,
                "compliant_req_per_sec": rate, "absolute_gain_vs_raw": rate - raw_rate,
                "multiplicative_gain_vs_raw": rate / raw_rate if raw_rate else "inf",
                "claim_boundary": "Offline SLO re-thresholding of frozen live TTFT and batch-wall records.",
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(output)
    print(json.dumps({"rows": len(output), "slo_buckets": 6}, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
