"""Separate free-output risk, raw-repeat variation, routing and full costs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import first_divergence, read, write
from scripts.summarize_submission_supplement import percentile


def route(row):
    if row.get("certificate_issued"):
        return "admitted_compiled"
    if row.get("requested_level") == "L0":
        return "manifest_direct_raw"
    return "runtime_raw_fallback"


def future_index(rows):
    out = {}
    for row in rows:
        if row.get("row_type") != "future":
            continue
        key = row["session_id"], row["turn_id"]
        if key in out:
            raise ValueError("Duplicate future identity")
        out[key] = row
    return out


def collect(root):
    cells = {}
    for path in sorted((root / "cells").glob("*/summary.json")):
        experiment, model, repeat, policy, budget = path.parent.name.split("_")
        raw = path.parent / "raw.jsonl"
        summary = json.loads(path.read_text())
        if hashlib.sha256(raw.read_bytes()).hexdigest() != summary["source_sha256"]:
            raise ValueError("Changed cell " + str(path))
        cells[(experiment, model, int(repeat[1:]), int(budget[1:]), policy)] = read(raw)
    return cells


def raw_controls(cells):
    comparisons = []
    scopes = sorted({(e, m, b) for e, m, r, b, p in cells if p == "raw-order"})
    for experiment, model, budget in scopes:
        for left, right in itertools.combinations((1, 2, 3), 2):
            lk, rk = (experiment, model, left, budget, "raw-order"), (experiment, model, right, budget, "raw-order")
            if lk not in cells or rk not in cells:
                continue
            refs, candidates = future_index(cells[lk]), future_index(cells[rk])
            if set(refs) != set(candidates):
                raise ValueError("Raw-repeat identities differ")
            for key, ref in refs.items():
                candidate = candidates[key]
                comparisons.append({
                    "experiment": experiment, "model": model, "budget_override": budget,
                    "repeat_left": left, "repeat_right": right, "session_id": key[0], "turn_id": key[1],
                    "family": ref["family"], "prompt_identical": ref["prompt_sha256"] == candidate["prompt_sha256"],
                    "first_diverging_token": first_divergence(ref.get("output_token_ids"), candidate.get("output_token_ids")),
                    "text_identical": ref["output_text"] == candidate["output_text"],
                    "raw_score_left": ref["task_score"], "raw_score_right": candidate["task_score"],
                    "score_absolute_difference": abs(ref["task_score"] - candidate["task_score"]),
                })
    grouped = defaultdict(list)
    for row in comparisons:
        for family in (row["family"], "ALL"):
            grouped[(row["experiment"], row["model"], row["budget_override"], family)].append(row)
    summaries = []
    for key, rows in sorted(grouped.items()):
        summaries.append({"experiment": key[0], "model": key[1], "budget_override": key[2], "family": key[3],
                          "raw_repeat_comparisons": len(rows), "prompt_identity_mismatches": sum(not r["prompt_identical"] for r in rows),
                          "token_divergences": sum(r["first_diverging_token"] not in {-1, "unavailable"} for r in rows),
                          "text_divergences": sum(not r["text_identical"] for r in rows),
                          "score_absolute_differences_gt_0_03": sum(r["score_absolute_difference"] > .03 for r in rows),
                          "not_independent_samples": "Each request appears in three repeat-pair comparisons."})
    return comparisons, summaries


def cost_decomposition(cells):
    out = []
    for key, rows in sorted(cells.items()):
        experiment, model, repeat, budget, policy = key
        ref_key = experiment, model, repeat, budget, "raw-order"
        if policy != "contractkv" or ref_key not in cells:
            continue
        refs = future_index(cells[ref_key]); canaries = {r["session_id"]: r for r in rows if r["row_type"] == "canary"}
        grouped = defaultdict(list)
        for row in rows:
            if row["row_type"] != "future":
                continue
            cls = route(canaries[row["session_id"]])
            grouped[("ALL", "ALL")].append(row)
            grouped[(row["family"], cls)].append(row)
            grouped[("ALL", cls)].append(row)
        for (family, cls), futures in grouped.items():
            sessions = {r["session_id"] for r in futures}
            selected = [canaries[s] for s in sessions]
            costs = [float(r["registration_ms"]) for r in selected]
            raw_ttft = [refs[(r["session_id"], r["turn_id"])]["ttft_ms"] for r in futures]
            ct = [r["ttft_ms"] for r in futures]
            for slack in (0, 500, 2000, 6000):
                residual = sum(max(c - slack, 0) for c in costs) / len(futures)
                net = statistics.fmean(ct) + residual
                out.append({"experiment": experiment, "model": model, "repeat": repeat, "budget_override": budget,
                            "family": family, "request_class": cls, "slack_ms": slack, "sessions": len(sessions),
                            "future_requests": len(futures), "completed": sum(r["success"] for r in futures),
                            "raw_mean_ttft_ms": statistics.fmean(raw_ttft), "observed_mean_ttft_ms": statistics.fmean(ct),
                            "observed_p95_ttft_ms": percentile(ct, .95), "registration_total_ms": sum(costs),
                            "observed_p99_ttft_ms": percentile(ct, .99),
                            "registration_mean_ms_per_session": statistics.fmean(costs), "registration_p95_ms_per_session": percentile(costs, .95),
                            "verify_endpoint_total_ms": sum(float(r.get("verify_endpoint_ms", 0)) for r in selected),
                            "residual_registration_ms_per_future": residual, "net_mean_ttft_ms": net,
                            "net_mean_ttft_reduction": 1 - net / statistics.fmean(raw_ttft),
                            "claim_boundary": "Measured registration; amortized mean accounting, not live per-request p95 overlap."})
    return out


def certificate_audit(cells):
    audits = []; rejected = []; decisions = []
    for key, rows in sorted(cells.items()):
        experiment, model, repeat, budget, policy = key
        if policy != "contractkv":
            continue
        canaries = [r for r in rows if r["row_type"] == "canary"]
        counts = Counter((r["family"], r.get("verify_decision", "unavailable")) for r in canaries)
        decisions.extend({"experiment": experiment, "model": model, "repeat": repeat, "budget_override": budget,
                          "family": family, "decision": decision, "sessions": count}
                         for (family, decision), count in sorted(counts.items()))
        accepted = [r for r in canaries if r.get("certificate_issued")]
        failed = [r for r in canaries if not r.get("certificate_issued")]
        future = [r for r in rows if r["row_type"] == "future"]
        bad_boundary = [r for r in accepted if int(r["committed_tokens"]) > int(r["stable_prefix_tokens"])]
        audits.append({"experiment": experiment, "model": model, "repeat": repeat, "budget_override": budget,
                       "sessions": len(canaries), "accepted": len(accepted),
                       "commit_past_stable_boundary": len(bad_boundary),
                       "rejected_published_tokens": sum(int(r.get("committed_tokens", 0)) for r in failed),
                       "accepted_length_stop": sum(r.get("raw_finish_reason") == "length" for r in accepted),
                       "scope_invalid_admissions": sum(bool(r.get("scope_invalid_admission")) for r in future),
                       "turn0_free_output_direct_evidence_records": sum("warm_output_token_ids" in r and "reference_output_token_ids" in r for r in accepted),
                       "max_committed_tokens": max((int(r["committed_tokens"]) for r in accepted), default=0),
                       "commit_guard": "stable-only boundary; partial end block not promoted"})
        for r in failed:
            rejected.append({"experiment": experiment, "model": model, "repeat": repeat, "budget_override": budget,
                             "session_id": r["session_id"], "family": r["family"], "route": route(r),
                             "decision": r.get("verify_decision"), "reason": r.get("failure_reason", ""),
                             "raw_finish_reason": r.get("raw_finish_reason", "not_run"),
                             "registration_ms": r["registration_ms"], "committed_tokens": r.get("committed_tokens", 0)})
    return audits, rejected, decisions


def violations(cells):
    out = []
    for key, rows in sorted(cells.items()):
        experiment, model, repeat, budget, policy = key
        rk = experiment, model, repeat, budget, "raw-order"
        if policy != "contractkv" or rk not in cells:
            continue
        refs = future_index(cells[rk])
        for r in rows:
            if r["row_type"] != "future":
                continue
            raw = refs[(r["session_id"], r["turn_id"])]
            drop = raw["task_score"] - r["task_score"]
            if drop <= .03:
                continue
            other_scores = []
            for rr in (1, 2, 3):
                if rr == repeat:
                    continue
                kr = experiment, model, rr, budget, "raw-order"
                if kr in cells:
                    other_scores.append(future_index(cells[kr])[(r["session_id"], r["turn_id"])]["task_score"])
            out.append({"experiment": experiment, "model": model, "repeat": repeat, "budget_override": budget,
                        "session_id": r["session_id"], "turn_id": r["turn_id"], "family": r["family"],
                        "query_wrapper_index": int(r["turn_id"]) % 3 if experiment != "common-hotpot" else 0,
                        "request_class": "admitted_compiled" if r["effective_level"] != "L0" else "raw_fallback",
                        "raw_score": raw["task_score"], "candidate_score": r["task_score"], "quality_drop": drop,
                        "other_raw_repeat_scores": json.dumps(other_scores),
                        "raw_output": raw["output_text"], "candidate_output": r["output_text"],
                        "raw_finish_reason": raw["finish_reason"], "candidate_finish_reason": r["finish_reason"],
                        "first_diverging_token": first_divergence(raw.get("output_token_ids"), r.get("output_token_ids")),
                        "prompt_identity": raw["prompt_sha256"] == r["prompt_sha256"],
                        "no_causal_attribution_from_single_pair": True})
    return out


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    cells = collect(a.root)
    raw_pairs, raw_summary = raw_controls(cells)
    write(a.output / "raw_repeat_controls_pairs_v1.csv", raw_pairs)
    write(a.output / "raw_repeat_controls_summary_v1.csv", raw_summary)
    write(a.output / "fresh_cost_decomposition_v1.csv", cost_decomposition(cells))
    audit, rejects, decisions = certificate_audit(cells)
    write(a.output / "certificate_publication_audit_v1.csv", audit)
    write(a.output / "certificate_rejections_v1.csv", rejects)
    write(a.output / "certificate_decision_counts_v1.csv", decisions)
    bad = violations(cells)
    write(a.output / "material_quality_drop_cases_v1.csv", bad)
    manifest = {"schema_version": "tsc-revision-diagnostics.v1", "live_cells_analyzed": len(cells),
                "raw_repeat_comparisons": len(raw_pairs), "material_drop_pairs": len(bad),
                "material_drops_on_compiled": sum(r["request_class"] == "admitted_compiled" for r in bad),
                "main_compiled_material_drops_on_unwrapped_query": sum(r["experiment"] == "free-generation" and
                                                                      r["request_class"] == "admitted_compiled" and
                                                                      r["query_wrapper_index"] == 0 for r in bad),
                "raw_repeat_controls_do_not_prove_a_specific_pair_is_numerical_noise": True,
                "zero_rejected_publication": all(r["rejected_published_tokens"] == 0 for r in audit),
                "stable_publication_boundary_valid": all(r["commit_past_stable_boundary"] == 0 for r in audit)}
    (a.output / "fresh_diagnostics_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__": main()
