"""Pair actual open-loop task outputs and retain cold/steady-state costs."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read, write


def summarize(root: Path, logs: Path):
    cells = {}; sources = []; records = []
    for path in sorted((root / "service").glob("*/summary.jsonl")):
        _, model, repeat, policy = path.parent.name.split("_")
        key = model, int(repeat[1:]), policy
        raw_path = path.parent / "raw.jsonl"
        raw = read(raw_path); registrations = read(path.parent / "registration.jsonl")
        if len(raw) != 180 or len({(r["session_id"], r["turn_id"]) for r in raw}) != 180:
            raise ValueError("Incomplete or duplicate service trace " + str(path.parent))
        cells[key] = raw, registrations
        source_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        sources.append({"cell": path.parent.name, "raw_sha256": source_hash})
        log = logs / (path.parent.name + "_server.log")
        endpoint_calls = "unavailable"
        guard_calls = 0
        if log.exists():
            endpoint_calls = len(re.findall(r'"POST /v1/contractkv/verify HTTP/1\.[01]"', log.read_text(errors="replace")))
        guard_path = root / "guard_probe_qwen_v1.jsonl"
        if model == "qwen" and int(repeat[1:]) == 1 and policy == "D2-template-contractkv" and guard_path.exists():
            guard = read(guard_path)
            guard_calls = len(guard)
            if len(guard) != 20:
                endpoint_calls = "unavailable"
        for row in read(path):
            measured = {k: v for k, v in row.items() if k != "actual_verifier_endpoint_calls"}
            records.append({"model": model, **measured,
                            "verifier_http_calls_whole_server_process": endpoint_calls,
                            "guard_probe_calls_excluded": guard_calls,
                            "verifier_http_calls_from_server_log": endpoint_calls - guard_calls if isinstance(endpoint_calls, int) else "unavailable",
                            "planned_same_engine_verification_attempts": row.get("actual_verifier_endpoint_calls", "unavailable"),
                            "registration_ms_per_future": sum(float(r["registration_ms"]) for r in registrations) / len(raw),
                            "peak_used_gpu_blocks_observed_at_initial_prefill": max((int(r["used_gpu_blocks"]) for r in raw if isinstance(r.get("used_gpu_blocks"), (int, float))), default=0),
                            "source_sha256": source_hash})
    pairs = []
    for (model, repeat, policy), (candidate, registrations) in sorted(cells.items()):
        if policy == "D0-native-apc":
            continue
        reference_key = model, repeat, "D0-native-apc"
        if reference_key not in cells:
            continue
        refs = {(r["session_id"], r["turn_id"]): r for r in cells[reference_key][0]}
        for row in candidate:
            raw = refs[(row["session_id"], row["turn_id"])]
            pairs.append({"model": model, "repeat": repeat, "policy": policy, "family": row["family"],
                          "session_id": row["session_id"], "turn_id": row["turn_id"],
                          "request_class": row["effective_policy"], "both_success": raw["success"] and row["success"],
                          "raw_score": raw["task_score"], "candidate_score": row["task_score"],
                          "quality_drop": raw["task_score"] - row["task_score"],
                          "text_identical": raw["output_text"] == row["output_text"],
                          "scope_invalid_admission": row["scope_invalid_admission"],
                          "binding_valid": row["certificate_binding_valid"]})
    grouped = defaultdict(list)
    for row in pairs:
        for family in (row["family"], "ALL"):
            grouped[(row["model"], row["policy"], family)].append(row)
    quality = []
    for key, rows in sorted(grouped.items()):
        quality.append({"model": key[0], "policy": key[1], "family": key[2], "paired_requests": len(rows),
                        "completed_pairs": sum(r["both_success"] for r in rows),
                        "compiled_requests": sum(r["request_class"] == "compiled" for r in rows),
                        "text_divergences": sum(not r["text_identical"] for r in rows),
                        "material_drops_gt_0_03": sum(r["quality_drop"] > .03 for r in rows),
                        "mean_quality_drop": statistics.fmean(r["quality_drop"] for r in rows),
                        "raw_mean_score": statistics.fmean(r["raw_score"] for r in rows),
                        "candidate_mean_score": statistics.fmean(r["candidate_score"] for r in rows),
                        "scope_invalid_admissions": sum(r["scope_invalid_admission"] for r in rows),
                        "binding_failures": sum(not r["binding_valid"] for r in rows)})
    return records, pairs, quality, sources


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--logs", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); records, pairs, quality, sources = summarize(a.root, a.logs)
    write(a.output / "zero_slack_service_by_repeat_v1.csv", records)
    write(a.output / "zero_slack_service_quality_pairs_v1.csv", pairs)
    write(a.output / "zero_slack_service_quality_summary_v1.csv", quality)
    manifest = {"schema_version": "tsc-revision-zero-slack-summary.v1", "complete_cells": len(sources),
                "expected_cells": 18, "all_cells_present": len(sources) == 18,
                "paired_quality_requests": len(pairs), "source_files": sources,
                "request_ttft_boundary": "TTFT begins at actual post-registration submission; cold deployment wall time is separately included in end-to-end goodput.",
                "registration_warmup_counted": True,
                "http_endpoint_calls_are_not_inferred_from_planned_attempts": True}
    (a.output / "zero_slack_service_summary_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "source_files"}))


if __name__ == "__main__": main()
