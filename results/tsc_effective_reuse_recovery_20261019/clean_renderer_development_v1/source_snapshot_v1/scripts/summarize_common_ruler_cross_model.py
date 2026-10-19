#!/usr/bin/env python3
"""Build model-stratified and macro bootstrap summaries for common RULER replay."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.summarize_submission_supplement import (
    clusters,
    hierarchical_bootstrap,
    load_jsonl,
    new_prefill_reduction,
    percentile,
    sample_metrics,
    verifier_by_session,
)


def pairs(root: Path) -> list[tuple[dict, dict, dict]]:
    result = []
    for repeat in (1, 2, 3):
        raw = load_jsonl(root / f"repeat{repeat}" / "raw-order.jsonl")
        contract = load_jsonl(root / f"repeat{repeat}" / "contractkv-full.jsonl")
        result.append((clusters(raw), clusters(contract), verifier_by_session(contract)))
    return result


def prefill(root: Path) -> list[float]:
    values = []
    for repeat in (1, 2, 3):
        values.append(new_prefill_reduction(
            load_jsonl(root / f"repeat{repeat}" / "raw-order.jsonl"),
            load_jsonl(root / f"repeat{repeat}" / "contractkv-full.jsonl")))
    return values


def macro_bootstrap(model_pairs: dict[str, list[tuple[dict, dict, dict]]], samples: int, seed: int, slo_ms: float) -> dict[str, Any]:
    rng = random.Random(seed)
    keys = ("net_mean_ttft_reduction", "slo_goodput_gain", "raw_slo_req_per_sec", "contract_slo_req_per_sec")
    observed_by_model = {}
    for model, repeat_pairs in model_pairs.items():
        parts = []
        for raw, contract, verifier in repeat_pairs:
            shared = sorted(set(raw) & set(contract))
            parts.append(sample_metrics(raw, contract, verifier, shared, slo_ms))
        observed_by_model[model] = {key: statistics.fmean(part[key] for part in parts) for key in keys}
    observed = {key: statistics.fmean(values[key] for values in observed_by_model.values()) for key in keys}
    draws = {key: [] for key in keys}
    for _ in range(samples):
        model_values = []
        for repeat_pairs in model_pairs.values():
            repeat_values = []
            for raw, contract, verifier in rng.choices(repeat_pairs, k=len(repeat_pairs)):
                shared = sorted(set(raw) & set(contract))
                sampled = rng.choices(shared, k=len(shared))
                repeat_values.append(sample_metrics(raw, contract, verifier, sampled, slo_ms))
            model_values.append({key: statistics.fmean(value[key] for value in repeat_values) for key in keys})
        for key in keys:
            draws[key].append(statistics.fmean(value[key] for value in model_values))
    output: dict[str, Any] = {"model": "cross-model-macro", "scope": "same 30 RULER sessions across three models"}
    for key in keys:
        output[f"estimate_{key}"] = observed[key]
        output[f"bootstrap95_low_{key}"] = percentile(draws[key], .025)
        output[f"bootstrap95_high_{key}"] = percentile(draws[key], .975)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", action="append", required=True, help="label,path")
    parser.add_argument("--session-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--slo-ms", type=float, default=1500)
    args = parser.parse_args()
    roots = {label: Path(path) for label, path in (spec.split(",", 1) for spec in args.model_root)}
    model_pairs = {model: pairs(root) for model, root in roots.items()}
    rows = []
    for model, repeat_pairs in model_pairs.items():
        stats = hierarchical_bootstrap(repeat_pairs, args.samples, 26100 + len(rows), args.slo_ms)
        pvalues = prefill(roots[model])
        record = {
            "model": model, "scope": "same frozen 30-session RULER scope", "sessions": 30,
            "future_requests_per_repeat": 270, "fresh_process_repeats": 3,
            "mean_new_prefill_reduction": statistics.fmean(pvalues),
            "min_new_prefill_reduction": min(pvalues), "max_new_prefill_reduction": max(pvalues),
            "slo_ms": args.slo_ms, "session_sha256": args.session_sha256, **stats,
            "claim_boundary": "Common qualified RULER scope; not a global workflow result.",
        }
        record["net_ttft_speedup"] = 1 / max(1 - record["estimate_net_mean_ttft_reduction"], 1e-9)
        record["slo_goodput_multiplier"] = 1 + record["estimate_slo_goodput_gain"]
        rows.append(record)
    macro = macro_bootstrap(model_pairs, args.samples, 26333, args.slo_ms)
    macro.update({
        "sessions": 30, "future_requests_per_repeat": 270, "fresh_process_repeats": 3,
        "mean_new_prefill_reduction": statistics.fmean(row["mean_new_prefill_reduction"] for row in rows),
        "min_new_prefill_reduction": min(row["min_new_prefill_reduction"] for row in rows),
        "max_new_prefill_reduction": max(row["max_new_prefill_reduction"] for row in rows),
        "slo_ms": args.slo_ms, "session_sha256": args.session_sha256,
        "session_clusters": sum(int(row["session_clusters"]) for row in rows),
        "claim_boundary": "Model-stratified macro average on one common scope; not a global workflow result.",
    })
    macro["net_ttft_speedup"] = 1 / max(1 - macro["estimate_net_mean_ttft_reduction"], 1e-9)
    macro["slo_goodput_multiplier"] = 1 + macro["estimate_slo_goodput_gain"]
    rows.append(macro)
    write_csv(args.output, rows)
    args.json_output.write_text(json.dumps({"status": "complete", "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
