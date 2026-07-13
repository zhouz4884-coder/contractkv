#!/usr/bin/env python3
"""Inventory the Phase 19 task pool and 8 TB dataset assets."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = ["dataset", "task", "partition", "sample_count", "unique_source_groups"]
ARCHIVES = [
    "sources/RULER-main.zip",
    "sources/LongBench-main.zip",
    "sources/repobench-main.zip",
    "sources/contractkv_datasets.zip",
]
REPOS = ["repos/RULER-main", "repos/LongBench-main", "repos/repobench-main"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    rows = load_jsonl(args.full_pool)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        metadata = row.get("metadata", {})
        groups[(str(row.get("dataset", "")), str(row.get("task", "")),
                str(metadata.get("phase14_partition", "unassigned")))].append(row)
    output = []
    for (dataset, task, partition), group in sorted(groups.items()):
        output.append({
            "dataset": dataset, "task": task, "partition": partition,
            "sample_count": len(group),
            "unique_source_groups": len({str(row.get("metadata", {}).get("source_group_id", "")) for row in group}),
        })
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(output)
    assets = []
    for relative in ARCHIVES:
        path = args.dataset_root / relative
        assets.append({"kind": "archive", "path": str(path), "present": path.is_file(),
                       "size_bytes": path.stat().st_size if path.is_file() else 0})
    for relative in REPOS:
        path = args.dataset_root / relative
        assets.append({"kind": "repo", "path": str(path), "present": path.is_dir(), "size_bytes": 0})
    generated = args.dataset_root / "contractkv_datasets/outputs/sample_prompts.jsonl"
    assets.append({"kind": "generated_pool", "path": str(generated), "present": generated.is_file(),
                   "size_bytes": generated.stat().st_size if generated.is_file() else 0})
    summary = {
        "full_pool_rows": len(rows),
        "datasets": {dataset: sum(1 for row in rows if str(row.get("dataset")) == dataset)
                     for dataset in sorted({str(row.get("dataset")) for row in rows})},
        "partitions": {partition: sum(1 for row in rows if str(row.get("metadata", {}).get("phase14_partition")) == partition)
                       for partition in sorted({str(row.get("metadata", {}).get("phase14_partition")) for row in rows})},
        "assets": assets,
        "all_required_assets_present": all(item["present"] for item in assets),
        "claim_boundary": "Local source and unified-pool readiness; not a claim that official benchmark scoring has run on every source example.",
    }
    args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_required_assets_present"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
