#!/usr/bin/env python3
"""Compute session-cluster uncertainty for the extended RULER replication."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.summarize_submission_supplement import (
    clusters,
    hierarchical_bootstrap,
    load_jsonl,
    new_prefill_reduction,
    verifier_by_session,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--slo-ms", type=float, default=1500)
    args = parser.parse_args()
    pairs, prefill = [], []
    for repeat in (1, 2, 3):
        raw = load_jsonl(args.root / f"repeat{repeat}" / "raw-order.jsonl")
        contract = load_jsonl(args.root / f"repeat{repeat}" / "contractkv-full.jsonl")
        pairs.append((clusters(raw), clusters(contract), verifier_by_session(contract)))
        prefill.append(new_prefill_reduction(raw, contract))
    result = {
        "model": "Llama-3.1-8B-Instruct", "scope": "30 new source-disjoint qualified RULER sessions",
        "sessions": 30, "future_requests_per_repeat": 270, "fresh_process_repeats": 3,
        "mean_new_prefill_reduction": sum(prefill) / len(prefill), "min_new_prefill_reduction": min(prefill),
        "max_new_prefill_reduction": max(prefill), "slo_ms": args.slo_ms,
        **hierarchical_bootstrap(pairs, args.samples, 314159, args.slo_ms),
        "claim_boundary": "Prospectively frozen L3 RULER scope; no global Llama extrapolation.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result)); writer.writeheader(); writer.writerow(result)
    args.json_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
