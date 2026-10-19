#!/usr/bin/env python3
"""Extract request-level LMCache hit accounting from real server logs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path


HIT_RE = re.compile(
    r"Reqid:\s*(?P<request_id>[^,]+),\s*Total tokens\s*(?P<total>\d+),\s*"
    r"LMCache hit tokens:\s*(?P<hit>\d+),\s*need to load:\s*(?P<load>\d+)"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-directory", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for mode in ("lmcache", "blendraw", "cacheblend"):
        for repeat in range(1, args.repeats + 1):
            path = args.log_directory / f"llama-r{repeat}-{mode}.log"
            if not path.exists():
                continue
            matches = list(HIT_RE.finditer(path.read_text(encoding="utf-8", errors="replace")))
            for index, match in enumerate(matches):
                total = int(match.group("total")); hit = int(match.group("hit"))
                rows.append({
                    "mode": mode,
                    "repeat": repeat,
                    "event_index": index,
                    "request_id": match.group("request_id"),
                    "total_tokens": total,
                    "lmcache_hit_tokens": hit,
                    "lmcache_need_to_load_tokens": int(match.group("load")),
                    "new_prefill_tokens": max(0, total - hit),
                    "hit_fraction": hit / max(1, total),
                    "log_path": str(path),
                })

    summaries = []
    for mode in ("lmcache", "blendraw", "cacheblend"):
        selected = [row for row in rows if row["mode"] == mode]
        summaries.append({
            "mode": mode,
            "events": len(selected),
            "fresh_process_repeats": len({int(row["repeat"]) for row in selected}),
            "mean_total_tokens": statistics.fmean(float(row["total_tokens"]) for row in selected) if selected else 0.0,
            "mean_lmcache_hit_tokens": statistics.fmean(float(row["lmcache_hit_tokens"]) for row in selected) if selected else 0.0,
            "mean_new_prefill_tokens": statistics.fmean(float(row["new_prefill_tokens"]) for row in selected) if selected else 0.0,
            "mean_hit_fraction": statistics.fmean(float(row["hit_fraction"]) for row in selected) if selected else 0.0,
            "positive_hit_event_rate": sum(int(row["lmcache_hit_tokens"]) > 0 for row in selected) / max(1, len(selected)),
        })

    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["mode"])
        writer.writeheader(); writer.writerows(rows)
    payload = {
        "schema_version": "contractkv.lmcache-runtime-accounting.v1",
        "summaries": summaries,
        "claim_boundary": "Values are parsed from LMCacheConnectorV1 request logs; they are not inferred from prompt layout.",
    }
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
