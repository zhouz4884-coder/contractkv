#!/usr/bin/env python3
"""Render the frozen Phase 20B JSONL taxonomy as a compact CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = ["session_id", "dataset", "task", "sample_id", "taxonomy",
          "protocol_bug", "prompt_prefix_match", "verify_offset_match",
          "target_absent_position", "stop_rank", "supported", "equivalent",
          "contract_type", "candidate_repeats_deterministic", "elapsed_ms"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in FIELDS} for row in rows)
    return 0


if __name__ == "__main__": raise SystemExit(main())
