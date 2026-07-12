#!/usr/bin/env python3
"""Summarize Phase 18A C0/C1 control-plane measurements without extrapolation."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c0", type=Path, required=True); parser.add_argument("--c1", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--c2", type=Path)
    args = parser.parse_args(); rows = []
    for cell, path, trace in (("C0", args.c0, "synchronous_jsonl"), ("C1", args.c1, "counters_no_critical_path_io")):
        with path.open(encoding="utf-8", newline="") as handle:
            source = {row["condition"]: row for row in csv.DictReader(handle)}
        base, live = source["baseline"], source["live_verifier"]
        rows.append({"cell": cell, "trace_mode": trace, "parking": "polling", "compact_result": "full_logprob_response",
                     "foreground_requests": live["active_requests"], "verifier_requests": live["verifier_requests"],
                     "baseline_p95_ttft_ms": base["active_p95_ttft_ms"], "live_p95_ttft_ms": live["active_p95_ttft_ms"],
                     "p95_penalty_ms": live["p95_penalty_ms"], "active_success_rate": live["active_success_rate"],
                     "verifier_success_rate": live["verifier_success_rate"],
                     "claim_boundary": "C0/C1 screening only; separate fresh-process trials, not a paired significance estimate."})
    if args.c2:
        with args.c2.open(encoding="utf-8", newline="") as handle:
            source = {row["condition"]: row for row in csv.DictReader(handle)}
        base, live = source["baseline"], source["live_verifier"]
        rows.append({"cell": "C2", "trace_mode": "counters_no_critical_path_io", "parking": "event_driven", "compact_result": "full_logprob_response",
                     "foreground_requests": live["active_requests"], "verifier_requests": live["verifier_requests"], "baseline_p95_ttft_ms": base["active_p95_ttft_ms"], "live_p95_ttft_ms": live["active_p95_ttft_ms"], "p95_penalty_ms": live["p95_penalty_ms"], "active_success_rate": live["active_success_rate"], "verifier_success_rate": live["verifier_success_rate"], "claim_boundary": "C2 parking correctness/performance screening; separate fresh-process trial, not a paired significance estimate."})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    main()
