"""Matched-baseline quality distributions; no cross-runtime causal ranking."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.summarize_llama_sota_matrix import paths, load, score_rows, request_key
from scripts.tsc_revision_offline_audit import write_csv

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    sessions = a.root / "results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl"
    answers = {str(row["phase19b_session_id"]): row for row in load(sessions)}
    pairs = []; sources = []
    for method, baseline in (("contractkv", "vllm_apc"), ("cacheblend", "cacheblend_raw"), ("sglang_certified", "sglang_raw"), ("manual_oracle", "vllm_apc")):
        for repeat, (raw_path, candidate_path) in enumerate(zip(paths(a.root, baseline), paths(a.root, method)), 1):
            raw, candidate = load(raw_path), load(candidate_path); score_rows(raw, answers); score_rows(candidate, answers)
            refs = {request_key(row): row for row in raw if row.get("row_type") == "future"}
            sources.extend({"path": str(path.relative_to(a.root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for path in (raw_path, candidate_path))
            for row in candidate:
                if row.get("row_type") != "future": continue
                ref = refs[request_key(row)]
                if "_frozen_task_score" not in ref or "_frozen_task_score" not in row:
                    raise ValueError("Unscorable matched-baseline pair")
                pairs.append({"method": method, "matched_baseline": baseline, "repeat": repeat,
                              "session_id": row["session_id"], "turn_id": row["turn_id"],
                              "dataset": row["dataset"], "task": row["task"],
                              "raw_score": ref["_frozen_task_score"], "candidate_score": row["_frozen_task_score"],
                              "quality_drop": ref["_frozen_task_score"] - row["_frozen_task_score"],
                              "text_changed": str(ref.get("output_text")) != str(row.get("output_text")),
                              "effective_level": row.get("effective_level", "not_applicable"),
                              "raw_prompt_tokens": ref.get("prompt_tokens", "unavailable"),
                              "candidate_prompt_tokens": row.get("prompt_tokens", "unavailable")})
    grouped = defaultdict(list)
    for row in pairs:
        grouped[(row["method"], row["matched_baseline"], row["dataset"] + ":" + row["task"])].append(row)
        grouped[(row["method"], row["matched_baseline"], "ALL")].append(row)
    summaries = []
    for (method, baseline, family), rows in sorted(grouped.items()):
        for threshold in (.01, .03, .05):
            summaries.append({"method": method, "matched_baseline": baseline, "family": family,
                              "threshold": threshold, "paired_requests": len(rows),
                              "baseline_mean_score": statistics.fmean(r["raw_score"] for r in rows),
                              "candidate_mean_score": statistics.fmean(r["candidate_score"] for r in rows),
                              "mean_quality_drop": statistics.fmean(r["quality_drop"] for r in rows),
                              "material_regressions": sum(r["quality_drop"] > threshold for r in rows),
                              "material_regression_rate": sum(r["quality_drop"] > threshold for r in rows) / len(rows),
                              "material_improvements": sum(r["quality_drop"] < -threshold for r in rows),
                              "exact_score_ties": sum(abs(r["quality_drop"]) < 1e-12 for r in rows),
                              "claim_boundary": "Each method versus its native matched baseline; no 112x cross-stack causal safety ratio."})
    a.output.mkdir(parents=True, exist_ok=True)
    write_csv(a.output / "matched_baseline_quality_pairs_v1.csv", pairs)
    write_csv(a.output / "matched_baseline_quality_thresholds_v1.csv", summaries)
    manifest = {"schema_version": "tsc-revision-matched-baseline-audit.v1", "paired_requests": len(pairs),
                "source_files": sources, "cross_runtime_superiority_claim": False,
                "original_cacheblend_reporting": "Aggregate F1/Rouge quality; different models/datasets; not the per-request >0.03 material regression statistic."}
    (a.output / "matched_baseline_audit_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "source_files"}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
