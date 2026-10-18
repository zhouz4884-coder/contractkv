#!/usr/bin/env python3
"""Row-wise fairness audit and cold/warm/family diagnostics for Phase 15A."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile

POLICIES = ("vllm-raw-order", "static-posc", "contractkv-caposc")
FAIRNESS_FIELDS = [
    "seed", "concurrency", "session_id", "turn_id", "policies_present",
    "segment_hash_match", "prompt_token_count_match", "source_identity_match",
    "row_fair", "claim_boundary",
]
BREAKDOWN_FIELDS = [
    "policy", "concurrency", "slice_type", "slice_value", "requests", "seeds",
    "mean_ttft_ms", "p95_ttft_ms", "p99_ttft_ms", "mean_new_prefill_tokens",
    "slo_1000_compliance_rate", "slo_2000_compliance_rate", "slo_3000_compliance_rate",
    "seed_mean_ttft_ci95_half_width_ms", "claim_boundary",
]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_fairness(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["_seed"], row["concurrency"], row["session_id"], row["turn_id"])].append(row)
    output = []
    for key, group in sorted(groups.items()):
        seed, concurrency, session_id, turn_id = key
        policies = {row["policy"] for row in group}
        hashes = {row["segment_multiset_sha256"] for row in group}
        prompt_tokens = {row["actual_prompt_tokens"] for row in group}
        sources = {(row["dataset"], row["task"], row["session_id"], row["turn_id"]) for row in group}
        hash_match = len(hashes) == 1
        token_match = len(prompt_tokens) == 1
        source_match = len(sources) == 1
        present = policies == set(POLICIES)
        output.append({
            "seed": seed, "concurrency": concurrency, "session_id": session_id, "turn_id": turn_id,
            "policies_present": ",".join(sorted(policies)), "segment_hash_match": hash_match,
            "prompt_token_count_match": token_match, "source_identity_match": source_match,
            "row_fair": present and hash_match and token_match and source_match,
            "claim_boundary": "Row-wise join over seed, concurrency, session, and turn; no set-only fairness inference.",
        })
    return output


def _ci95_half_width(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return 1.96 * statistics.stdev(values) / math.sqrt(len(values))


def summarize_breakdowns(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        base = (row["policy"], row["concurrency"])
        groups[base + ("turn_temperature", "cold" if int(row["turn_id"]) == 0 else "warm")].append(row)
        groups[base + ("workload_family", row["workload_family"])].append(row)
        groups[base + ("seed", row["_seed"])].append(row)
        groups[base + ("all", "all")].append(row)
    output = []
    for (policy, concurrency, slice_type, slice_value), group in sorted(groups.items()):
        ttft = [_float(row["ttft_ms"]) for row in group if str(row["success"]).lower() == "true"]
        seed_means = []
        for seed in sorted({row["_seed"] for row in group}):
            values = [_float(row["ttft_ms"]) for row in group if row["_seed"] == seed and str(row["success"]).lower() == "true"]
            if values:
                seed_means.append(statistics.mean(values))
        output.append({
            "policy": policy, "concurrency": concurrency, "slice_type": slice_type, "slice_value": slice_value,
            "requests": len(group), "seeds": ",".join(sorted({row["_seed"] for row in group})),
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
            "p95_ttft_ms": percentile(ttft, .95), "p99_ttft_ms": percentile(ttft, .99),
            "mean_new_prefill_tokens": statistics.mean(_float(row["observed_new_prefill_tokens"]) for row in group),
            "slo_1000_compliance_rate": sum(value <= 1000 for value in ttft) / len(ttft) if ttft else 0.0,
            "slo_2000_compliance_rate": sum(value <= 2000 for value in ttft) / len(ttft) if ttft else 0.0,
            "slo_3000_compliance_rate": sum(value <= 3000 for value in ttft) / len(ttft) if ttft else 0.0,
            "seed_mean_ttft_ci95_half_width_ms": _ci95_half_width(seed_means),
            "claim_boundary": "Zero-GPU post-processing of fresh-process Phase 15A endpoint records.",
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--fairness-output", type=Path, required=True)
    parser.add_argument("--breakdown-output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_csv(args.input)
    fairness = audit_fairness(rows)
    write_csv(args.fairness_output, fairness, FAIRNESS_FIELDS)
    write_csv(args.breakdown_output, summarize_breakdowns(rows), BREAKDOWN_FIELDS)
    fair = sum(str(row["row_fair"]).lower() == "true" for row in fairness)
    print(f"fair_rows={fair}/{len(fairness)} breakdown_rows={len(summarize_breakdowns(rows))}")
    return 0 if fairness and fair == len(fairness) else 1


if __name__ == "__main__":
    raise SystemExit(main())
