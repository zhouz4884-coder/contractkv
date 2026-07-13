#!/usr/bin/env python3
"""Convert observed vLLM physical-block sharing into model-specific memory facts."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
    "model", "sessions", "shared_target_tokens", "fresh_process_repeats",
    "raw_completion_rate", "contract_completion_rate", "quality_sanity_rate",
    "block_size", "kv_bytes_per_token", "kv_mib_per_block",
    "raw_mean_effective_unique_blocks", "contract_mean_effective_unique_blocks",
    "observed_physical_blocks_saved", "observed_kv_mib_saved",
    "observed_kv_gib_saved", "raw_mean_newly_allocated_blocks",
    "contract_mean_newly_allocated_blocks", "raw_mean_used_block_high_water",
    "contract_mean_used_block_high_water", "peak_used_blocks_saved",
    "peak_used_kv_mib_saved", "peak_used_kv_gib_saved",
    "raw_mean_minimum_free_blocks", "contract_mean_minimum_free_blocks",
    "raw_peak_concurrent_logical_refs", "raw_peak_concurrent_unique_blocks",
    "raw_peak_concurrent_reference_blocks_avoided",
    "contract_peak_shared_physical_blocks",
    "contract_peak_logical_refs", "contract_peak_concurrent_unique_blocks",
    "contract_peak_concurrent_reference_blocks_avoided",
    "net_concurrent_reference_blocks_avoided",
    "net_concurrent_kv_mib_saved", "net_concurrent_kv_gib_saved",
    "contract_peak_refcount_match_rate",
    "raw_mean_ttft_ms", "contract_mean_ttft_ms", "ttft_reduction",
    "max_observed_concurrency_without_oom", "oom_boundary",
    "claim_boundary",
]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_cells(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cell in sorted(path.glob("*_summary.csv")):
        with cell.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_path"] = str(cell)
                rows.append(row)
    return rows


def mean_initial_prompt_allocations(rows: list[dict[str, str]]) -> float:
    """Recover initial prompt allocations without decode-lifetime maxima."""
    values = []
    for row in rows:
        sessions = max(number(row.get("sessions")), 1.0)
        effective_unique = number(row.get("unique_physical_blocks_effective"))
        unique_reused = number(row.get("unique_reused_physical_blocks"))
        values.append(max(0.0, effective_unique - unique_reused) / sessions)
    return statistics.fmean(values) if values else 0.0


def kv_geometry(config: dict[str, Any]) -> tuple[int, int, int, int]:
    layers = int(config["num_hidden_layers"])
    kv_heads = int(config.get("num_key_value_heads", config["num_attention_heads"]))
    head_dim = int(config.get("head_dim", int(config["hidden_size"]) // int(config["num_attention_heads"])))
    bytes_per_element = 2  # The experiment fixes float16 KV cache.
    return layers, kv_heads, head_dim, 2 * layers * kv_heads * head_dim * bytes_per_element


def summarize(cells: list[dict[str, str]], model: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    _, _, _, bytes_per_token = kv_geometry(config)
    grouped: dict[tuple[int, int], dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in cells:
        grouped[(int(row["sessions"]), int(row["shared_target_tokens"]))][row["policy"]].append(row)
    max_complete = max((sessions for (sessions, _), group in grouped.items()
                        if all(number(row["completion_rate"]) == 1.0
                               for rows in group.values() for row in rows)), default=0)
    output: list[dict[str, Any]] = []
    for (sessions, tokens), policies in sorted(grouped.items()):
        raw = policies.get("raw-order", [])
        contract = policies.get("contractkv-caposc", [])
        if not raw or not contract:
            continue
        block_size = int(max(number(row.get("block_size")) for row in raw + contract))
        mib_per_block = bytes_per_token * block_size / 2**20
        raw_unique = statistics.fmean(number(row["unique_physical_blocks_effective"]) for row in raw)
        contract_unique = statistics.fmean(number(row["unique_physical_blocks_effective"]) for row in contract)
        saved = max(0.0, raw_unique - contract_unique)
        raw_used = statistics.fmean(number(row["used_block_high_water"]) for row in raw)
        contract_used = statistics.fmean(number(row["used_block_high_water"]) for row in contract)
        peak_saved = max(0.0, raw_used - contract_used)
        raw_peak_logical = max(number(row.get("peak_concurrent_logical_refs")) for row in raw)
        raw_peak_unique = max(number(row.get("peak_concurrent_unique_blocks")) for row in raw)
        contract_peak_logical = max(number(row.get("peak_concurrent_logical_refs")) for row in contract)
        contract_peak_unique = max(number(row.get("peak_concurrent_unique_blocks")) for row in contract)
        raw_avoided = max(0.0, raw_peak_logical - raw_peak_unique)
        contract_avoided = max(0.0, contract_peak_logical - contract_peak_unique)
        net_concurrent_avoided = max(0.0, contract_avoided - raw_avoided)
        output.append({
            "model": model, "sessions": sessions, "shared_target_tokens": tokens,
            "fresh_process_repeats": min(len(raw), len(contract)),
            "raw_completion_rate": statistics.fmean(number(row["completion_rate"]) for row in raw),
            "contract_completion_rate": statistics.fmean(number(row["completion_rate"]) for row in contract),
            "quality_sanity_rate": min(statistics.fmean(number(row["quality_sanity_rate"]) for row in raw),
                                       statistics.fmean(number(row["quality_sanity_rate"]) for row in contract)),
            "block_size": block_size, "kv_bytes_per_token": bytes_per_token,
            "kv_mib_per_block": mib_per_block,
            "raw_mean_effective_unique_blocks": raw_unique,
            "contract_mean_effective_unique_blocks": contract_unique,
            "observed_physical_blocks_saved": saved,
            "observed_kv_mib_saved": saved * mib_per_block,
            "observed_kv_gib_saved": saved * mib_per_block / 1024.0,
            "raw_mean_newly_allocated_blocks": mean_initial_prompt_allocations(raw),
            "contract_mean_newly_allocated_blocks": mean_initial_prompt_allocations(contract),
            "raw_mean_used_block_high_water": raw_used,
            "contract_mean_used_block_high_water": contract_used,
            "peak_used_blocks_saved": peak_saved,
            "peak_used_kv_mib_saved": peak_saved * mib_per_block,
            "peak_used_kv_gib_saved": peak_saved * mib_per_block / 1024.0,
            "raw_mean_minimum_free_blocks": statistics.fmean(number(row["minimum_free_blocks"]) for row in raw),
            "contract_mean_minimum_free_blocks": statistics.fmean(number(row["minimum_free_blocks"]) for row in contract),
            "raw_peak_concurrent_logical_refs": raw_peak_logical,
            "raw_peak_concurrent_unique_blocks": raw_peak_unique,
            "raw_peak_concurrent_reference_blocks_avoided": raw_avoided,
            "contract_peak_shared_physical_blocks": max(number(row["peak_concurrent_shared_blocks"]) for row in contract),
            "contract_peak_logical_refs": contract_peak_logical,
            "contract_peak_concurrent_unique_blocks": contract_peak_unique,
            "contract_peak_concurrent_reference_blocks_avoided": contract_avoided,
            "net_concurrent_reference_blocks_avoided": net_concurrent_avoided,
            "net_concurrent_kv_mib_saved": net_concurrent_avoided * mib_per_block,
            "net_concurrent_kv_gib_saved": net_concurrent_avoided * mib_per_block / 1024.0,
            "contract_peak_refcount_match_rate": min(number(row["peak_concurrent_refcount_match_rate"]) for row in contract),
            "raw_mean_ttft_ms": statistics.fmean(number(row["mean_ttft_ms"]) for row in raw),
            "contract_mean_ttft_ms": statistics.fmean(number(row["mean_ttft_ms"]) for row in contract),
            "ttft_reduction": 1.0 - statistics.fmean(number(row["mean_ttft_ms"]) for row in contract) /
                              max(statistics.fmean(number(row["mean_ttft_ms"]) for row in raw), 1e-9),
            "max_observed_concurrency_without_oom": max_complete,
            "oom_boundary": f">={max_complete}" if max_complete else "unavailable",
            "claim_boundary": ("The primary dedup count uses same-snapshot logical references minus unique physical block IDs; "
                               "block-pool high-water is an independent peak check. Cross-lifecycle unique IDs are diagnostic only. "
                               "Memory conversion uses actual Qwen KV geometry, never new-prefill tokens. OOM boundary is lower-bounded only."),
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-dir", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    cells = load_cells(args.cell_dir)
    if not cells:
        raise SystemExit("no physical dedup cell summaries")
    config = json.loads(args.model_config.read_text(encoding="utf-8"))
    rows = summarize(cells, args.model, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    args.json_output.write_text(json.dumps({"geometry": dict(zip(
        ("layers", "kv_heads", "head_dim", "kv_bytes_per_token"), kv_geometry(config))),
        "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
