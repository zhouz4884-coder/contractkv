"""Summarize actual token divergence, quality, full costs and shared-scope CI."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.summarize_submission_supplement import percentile

def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields); w.writeheader(); w.writerows(rows)

def first_divergence(raw, candidate):
    if not isinstance(raw, list) or not isinstance(candidate, list) or not raw or not candidate:
        return "unavailable"
    for index, (left, right) in enumerate(zip(raw, candidate)):
        if left != right: return index
    return min(len(raw), len(candidate)) if len(raw) != len(candidate) else -1

def summarize_pair(raw_rows, candidate_rows, raw_summary, candidate_summary, key, slack):
    references = {(r["session_id"], r["turn_id"]): r for r in raw_rows if r["row_type"] == "future"}
    future = [r for r in candidate_rows if r["row_type"] == "future"]
    canary = [r for r in candidate_rows if r["row_type"] == "canary"]
    if len(references) != len(future): raise ValueError("Paired request count mismatch")
    full_cost = sum(float(r.get("registration_ms", 0)) for r in canary)
    unhidden = sum(max(float(r.get("registration_ms", 0)) - slack, 0) for r in canary)
    raw_ttft = [float(r["ttft_ms"]) for r in references.values() if r["success"]]
    candidate_ttft = [float(r["ttft_ms"]) for r in future if r["success"]]
    raw_prefill = [float(r["new_prefill_tokens"]) for r in references.values() if isinstance(r.get("new_prefill_tokens"), (int, float))]
    candidate_prefill = [float(r["new_prefill_tokens"]) for r in future if isinstance(r.get("new_prefill_tokens"), (int, float))]
    raw_mean = statistics.fmean(raw_ttft); candidate_mean = statistics.fmean(candidate_ttft)
    admitted = [r for r in future if r["effective_level"] != "L0"]
    row = {"experiment": key[0], "model": key[1], "repeat": key[2], "budget_override": key[3],
           "slack_ms": slack, "requests": len(future), "raw_completed": sum(r["success"] for r in references.values()),
           "candidate_completed": sum(r["success"] for r in future), "compiled_requests": len(admitted),
           "certificate_coverage": len(admitted) / len(future), "raw_mean_ttft_ms": raw_mean,
           "candidate_observed_mean_ttft_ms": candidate_mean, "candidate_observed_p95_ttft_ms": percentile(candidate_ttft, .95),
           "raw_observed_p95_ttft_ms": percentile(raw_ttft, .95), "registration_total_ms": full_cost,
           "registration_ms_per_future": full_cost / len(future), "unhidden_ms_per_future": unhidden / len(future),
           "net_mean_ttft_ms": candidate_mean + unhidden / len(future),
           "net_mean_ttft_reduction": 1 - (candidate_mean + unhidden / len(future)) / raw_mean,
           "new_prefill_reduction": 1 - statistics.fmean(candidate_prefill) / statistics.fmean(raw_prefill),
           "raw_wall_s_including_registration": raw_summary["wall_time_s_including_registration"],
           "candidate_wall_s_including_registration": candidate_summary["wall_time_s_including_registration"],
           "observed_1500ms_goodput_raw": sum(t <= 1500 for t in raw_ttft) / raw_summary["wall_time_s_including_registration"],
           "observed_1500ms_goodput_candidate": sum(t <= 1500 for t in candidate_ttft) / candidate_summary["wall_time_s_including_registration"],
           "scope_invalid_admissions": sum(r["scope_invalid_admission"] for r in future),
           "claim_boundary": "Observed TTFT and wall time are live; net TTFT adds measured amortized residual cost. p95 is observed, not an overlap model."}
    pairs = []
    for r in future:
        ref = references[(r["session_id"], r["turn_id"])]; is_admitted = r["effective_level"] != "L0"
        first = first_divergence(ref.get("output_token_ids"), r.get("output_token_ids"))
        pairs.append({"experiment": key[0], "model": key[1], "repeat": key[2], "budget_override": key[3],
                      "session_id": r["session_id"], "turn_id": r["turn_id"], "family": r["family"],
                      "request_class": "admitted_compiled" if is_admitted else "raw_fallback",
                      "both_success": ref["success"] and r["success"],
                      "text_identical": ref["output_text"] == r["output_text"], "first_diverging_token": first,
                      "token_identical": first == -1 if first != "unavailable" else "unavailable",
                      "raw_score": ref["task_score"], "candidate_score": r["task_score"],
                      "quality_drop": ref["task_score"] - r["task_score"],
                      "raw_finish_reason": ref["finish_reason"], "candidate_finish_reason": r["finish_reason"],
                      "raw_output_tokens": len(ref.get("output_token_ids", [])), "candidate_output_tokens": len(r.get("output_token_ids", [])),
                      "output_budget": r["output_budget"], "prompt_tokens": r["actual_prompt_tokens"],
                      "dynamic_suffix_reuse_tokens": r["dynamic_suffix_reuse_tokens"]})
    return row, pairs

def shared_macro_bootstrap(cell_data, n, seed):
    models = ("qwen", "mistral", "llama"); groups = {}
    for model in models:
        for repeat in (1, 2, 3):
            key = ("common-hotpot", model, repeat, 0)
            if key not in cell_data: return None
            raw, candidate, _, _ = cell_data[key]
            rg, cg = defaultdict(list), defaultdict(list)
            costs = {}
            for row in raw:
                if row["row_type"] == "future": rg[row["session_id"]].append(float(row["ttft_ms"]))
            for row in candidate:
                if row["row_type"] == "future": cg[row["session_id"]].append(float(row["ttft_ms"]))
                else: costs[row["session_id"]] = float(row.get("registration_ms", 0))
            groups[(model, repeat)] = (rg, cg, costs)
    session_sets = [set(g[0]) & set(g[1]) for g in groups.values()]
    if any(s != session_sets[0] for s in session_sets): raise ValueError("Common source session identity changed")
    sessions = sorted(session_sets[0]); rng = random.Random(seed); output = []
    for slack in (0, 2000, 6000):
        def estimate(selected_sessions, selected_repeats):
            values = []
            for model in models:
                parts = []
                for repeat in selected_repeats[model]:
                    rg, cg, costs = groups[(model, repeat)]
                    raw_sum = sum(sum(rg[s]) for s in selected_sessions)
                    cand_sum = sum(sum(cg[s]) for s in selected_sessions)
                    residual = sum(max(costs.get(s, 0) - slack, 0) for s in selected_sessions)
                    parts.append(1 - (cand_sum + residual) / raw_sum)
                values.append(statistics.fmean(parts))
            return statistics.fmean(values)
        observed = estimate(sessions, {model: [1, 2, 3] for model in models})
        draws = [estimate(rng.choices(sessions, k=len(sessions)),
                          {model: rng.choices([1, 2, 3], k=3) for model in models}) for _ in range(n)]
        output.append({"slack_ms": slack, "model_count": 3, "identical_sessions": len(sessions),
                       "net_mean_ttft_reduction_macro": observed, "ci95_low": percentile(draws, .025),
                       "ci95_high": percentile(draws, .975), "bootstrap_samples": n,
                       "estimand": "mean effect of the three fixed models on this shared scope",
                       "resampling": "same source sessions jointly across models; fresh repeats within model",
                       "not_an_architecture_population_prediction_interval": True})
    return output

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--bootstrap-samples", type=int, default=10000)
    a = p.parse_args(); found = {}; sources = []; cell_data = {}; tables = []; quality = []
    for path in sorted((a.root / "cells").glob("*/summary.json")):
        summary = json.loads(path.read_text()); parts = path.parent.name.split("_")
        experiment, model, repeat, policy, budget = parts
        key = (experiment, model, int(repeat[1:]), int(budget[1:]))
        raw_file = path.parent / "raw.jsonl"
        if hashlib.sha256(raw_file.read_bytes()).hexdigest() != summary["source_sha256"]:
            raise ValueError("Raw file changed after summary: " + str(raw_file))
        found.setdefault(key, {})[policy] = (read(raw_file), summary)
        sources.append({"path": str(raw_file), "sha256": summary["source_sha256"]})
    for key, policies in found.items():
        if "raw-order" not in policies or "contractkv" not in policies: continue
        raw, rs = policies["raw-order"]; candidate, cs = policies["contractkv"]
        cell_data[key] = (raw, candidate, rs, cs)
        for slack in (0, 500, 2000, 6000):
            row, pairs = summarize_pair(raw, candidate, rs, cs, key, slack); tables.append(row)
            if slack == 0: quality.extend(pairs)
    write(a.output / "fresh_paired_performance_v1.csv", tables)
    write(a.output / "fresh_token_quality_pairs_v1.csv", quality)
    grouped = defaultdict(list)
    for row in quality:
        grouped[(row["experiment"], row["model"], row["budget_override"], row["family"], row["request_class"])].append(row)
        grouped[(row["experiment"], row["model"], row["budget_override"], "ALL", "ALL")].append(row)
    summaries = []
    for key, rows in sorted(grouped.items()):
        summaries.append({"experiment": key[0], "model": key[1], "budget_override": key[2], "family": key[3],
                          "request_class": key[4], "paired_requests": len(rows),
                          "completed_pairs": sum(r["both_success"] for r in rows),
                          "token_divergences": sum(r["first_diverging_token"] not in {-1, "unavailable"} for r in rows),
                          "text_divergences": sum(not r["text_identical"] for r in rows),
                          "material_score_drops_gt_0_03": sum(r["quality_drop"] > .03 for r in rows),
                          "mean_quality_drop": statistics.fmean(r["quality_drop"] for r in rows),
                          "raw_mean_score": statistics.fmean(r["raw_score"] for r in rows),
                          "candidate_mean_score": statistics.fmean(r["candidate_score"] for r in rows),
                          "positive_raw_score_pairs": sum(r["raw_score"] > 0 for r in rows),
                          "raw_zero_score_pairs": sum(r["raw_score"] == 0 for r in rows),
                          "material_drops_on_positive_raw": sum(r["raw_score"] > 0 and r["quality_drop"] > .03 for r in rows),
                          "raw_length_stops": sum(r["raw_finish_reason"] == "length" for r in rows),
                          "candidate_length_stops": sum(r["candidate_finish_reason"] == "length" for r in rows),
                          "raw_output_tokens_p95": percentile([r["raw_output_tokens"] for r in rows], .95),
                          "outputs_longer_than_96_tokens": sum(r["raw_output_tokens"] > 96 or r["candidate_output_tokens"] > 96 for r in rows)})
    write(a.output / "fresh_token_quality_summary_v1.csv", summaries)
    macro = shared_macro_bootstrap(cell_data, a.bootstrap_samples, 10672026)
    if macro: write(a.output / "common_hotpot_shared_cluster_ci_v1.csv", macro)
    main_count = sum(key[0] in {"common-hotpot", "free-generation"} and key[1] in {"qwen", "mistral", "llama"} for key in cell_data)
    manifest = {"schema_version": "tsc-revision-fresh-summary.v1", "complete_paired_cells": len(cell_data),
                "expected_main_paired_cells": 27, "main_matrix_complete": main_count == 27,
                "paired_future_requests": len(quality), "source_files": sources,
                "completion_authority": "remote_completion_audit_v1.json; this summarizer does not audit service/guard/publication tasks",
                "boundary": "Zero-slack service, guard, security and fairness audits have separate gates."}
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / "fresh_summary_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "source_files"}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
