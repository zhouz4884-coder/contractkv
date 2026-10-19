#!/usr/bin/env python3
"""Charge frozen canary verification cost under a tool-slack sweep."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


FIELDS = ["load_tier", "concurrency", "slack_ms", "future_requests",
          "observed_mean_ttft_ms", "unhidden_verifier_ms_per_future",
          "net_mean_ttft_ms", "raw_mean_ttft_ms", "net_reduction_vs_raw",
          "break_even_slack_ms", "claim_boundary"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--slack-ms", default="0,500,1000,1500,2000,3000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    output = []
    for load in sorted({str(row["load_tier"]) for row in rows}):
        full = [row for row in rows if row.get("policy") == "contractkv-full" and row.get("load_tier") == load]
        future = [row for row in full if row.get("row_type") == "future" and row.get("success") is True]
        canaries = [row for row in full if row.get("row_type") == "canary"]
        raw = [row for row in rows if row.get("policy") == "raw-order" and row.get("load_tier") == load
               and row.get("row_type") == "future" and row.get("success") is True]
        observed = statistics.mean(float(row["ttft_ms"]) for row in future)
        raw_mean = statistics.mean(float(row["ttft_ms"]) for row in raw)
        verify = [float(row.get("verification_ms", 0)) for row in canaries]
        total_verify = sum(verify)
        break_even = max(0.0, total_verify - len(future) * max(0.0, raw_mean - observed)) / max(1, len(canaries))
        for slack in [float(value) for value in args.slack_ms.split(",")]:
            unhidden = sum(max(0.0, value - slack) for value in verify) / max(1, len(future))
            net = observed + unhidden
            output.append({
                "load_tier": load, "concurrency": future[0]["concurrency"], "slack_ms": slack,
                "future_requests": len(future), "observed_mean_ttft_ms": observed,
                "unhidden_verifier_ms_per_future": unhidden, "net_mean_ttft_ms": net,
                "raw_mean_ttft_ms": raw_mean, "net_reduction_vs_raw": 1 - net / raw_mean,
                "break_even_slack_ms": break_even,
                "claim_boundary": "Offline slack accounting over measured canary verification latency and live TTFT.",
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(output)
    main_rows = [row for row in output if float(row["slack_ms"]) == 2000]
    gate = {"rows": len(output), "all_slack_buckets_complete": len(output) == 18,
            "qwen_2s_net_ttft_reduction_ge_0_30": all(float(row["net_reduction_vs_raw"]) >= .30 for row in main_rows)}
    gate["gate_pass"] = gate["all_slack_buckets_complete"] and gate["qwen_2s_net_ttft_reduction_ge_0_30"]
    args.gate_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2)); return 0 if gate["gate_pass"] else 2


if __name__ == "__main__": raise SystemExit(main())
