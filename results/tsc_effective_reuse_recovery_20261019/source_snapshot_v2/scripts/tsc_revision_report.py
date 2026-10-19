"""Render an evidence-bounded R1 report in the frozen X1-X7 task order."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def fmean(rows, field):
    return statistics.fmean(float(r[field]) for r in rows)


def pct(value):
    return f"{100 * value:.2f}%"


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + [
        "| " + " | ".join(str(v) for v in row) + " |" for row in rows]


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    perf = csv_rows(a.root / "fresh_paired_performance_v1.csv")
    quality = csv_rows(a.root / "fresh_token_quality_summary_v1.csv")
    raw_controls = csv_rows(a.root / "raw_repeat_controls_summary_v1.csv")
    costs = csv_rows(a.root / "fresh_cost_decomposition_v1.csv")
    paired_quality = csv_rows(a.root / "fresh_token_quality_pairs_v1.csv")
    audit = json.loads((a.root / "remote_completion_audit_v1.json").read_text())
    lines = ["# TSC Major Revision R1: Completed Experimental Evidence", "",
             "This report follows X1-X7 in the frozen revision plan. Experiment completion is distinct from scientific success. "
             "The submitted manuscript has not been overwritten; this is an experimental evidence package, not a submitted revision.", "",
             "## X1. Identical Non-RULER Common Scope", "",
             "All models consume the same 30 source-disjoint HotpotQA sessions, fixed L2 segment order, 10 turns, "
             "128-token budget, concurrency 2, and three fresh raw/ContractKV process pairs. All runtime rejections remain in the denominator.", ""]
    common = []; common_json = []
    for model in ("qwen", "mistral", "llama"):
        subset = [r for r in perf if r["experiment"] == "common-hotpot" and r["model"] == model]
        at0 = [r for r in subset if r["slack_ms"] == "0"]
        at2 = [r for r in subset if r["slack_ms"] == "2000"]
        at6 = [r for r in subset if r["slack_ms"] == "6000"]
        q = next(r for r in quality if r["experiment"] == "common-hotpot" and r["model"] == model and r["family"] == "ALL")
        values = {"model": model, "requests": int(q["paired_requests"]), "coverage": fmean(at0, "certificate_coverage"),
                  "new_prefill_reduction": fmean(at0, "new_prefill_reduction"),
                  "raw_mean_ttft_ms": fmean(at0, "raw_mean_ttft_ms"),
                  "candidate_observed_mean_ttft_ms": fmean(at0, "candidate_observed_mean_ttft_ms"),
                  "zero_slack_net_reduction": fmean(at0, "net_mean_ttft_reduction"),
                  "slack2000_net_reduction": fmean(at2, "net_mean_ttft_reduction"),
                  "slack6000_net_reduction": fmean(at6, "net_mean_ttft_reduction"),
                  "score_drops_gt_0_03": int(q["material_score_drops_gt_0_03"]),
                  "raw_score": float(q["raw_mean_score"]), "candidate_score": float(q["candidate_mean_score"])}
        common_json.append(values)
        common.append([model, values["requests"], pct(values["coverage"]), pct(values["new_prefill_reduction"]),
                       f'{values["raw_mean_ttft_ms"]:.1f} -> {values["candidate_observed_mean_ttft_ms"]:.1f}',
                       pct(values["zero_slack_net_reduction"]), pct(values["slack2000_net_reduction"]),
                       pct(values["slack6000_net_reduction"]), values["score_drops_gt_0_03"]])
    lines += table(["Model", "Paired futures", "Coverage", "New-prefill reduction", "Observed mean TTFT ms",
                    "Net reduction, slack 0", "Net, 2s", "Net, 6s", "Drops >0.03"], common)
    lines += ["", "The non-RULER mechanism generalizes, but its global effects do not converge as tightly as the RULER scope. "
              "The 0/2/6s columns are amortized residual-cost accounting, not measured scheduler overlap. "
              "At zero slack, the fixed-model macro interval crosses zero; it is not evidence of universal cold-session speedup.", ""]
    macro = csv_rows(a.root / "common_hotpot_shared_cluster_ci_v1.csv")
    lines += table(["Slack ms", "Fixed-three-model net mean reduction", "Joint-session 95% CI"],
                   [[r["slack_ms"], pct(float(r["net_mean_ttft_reduction_macro"])),
                     f'[{pct(float(r["ci95_low"]))}, {pct(float(r["ci95_high"]))}]'] for r in macro])
    lines += ["", "The bootstrap resamples the same source sessions jointly across models and fresh repeats within model (10,000 draws). "
              "It estimates the average effect for these three fixed models, not an architecture-population prediction interval.", "",
              "## X2. Actual Free-Running Generation and Output Horizon", "",
              "Each model executes 50 new source-disjoint benchmark-derived sessions (10 per family), three fresh paired repetitions, "
              "and nine futures per session. The original family budgets and an independently rebound 512-token budget are separate conditions. "
              "Every future has actual vLLM output token IDs, a request-metric join, and a frozen task score. "
              "This diagnostic tries one frozen maximum level and then raw fallback; it does not execute the original adaptive eligible-level descent or benefit gate. "
              "Its generic task instruction and context/output settings are therefore not a reproduction of the complete published end-to-end policy.", ""]
    qt = [r for r in quality if r["experiment"] == "free-generation" and r["family"] == "ALL"]
    lines += table(["Model", "Budget", "Pairs", "Token divergences", "Drops >0.03", "Mean score raw -> C", "Raw length stops"],
                   [[r["model"], "native" if r["budget_override"] == "0" else r["budget_override"], r["paired_requests"],
                     r["token_divergences"], r["material_score_drops_gt_0_03"],
                     f'{float(r["raw_mean_score"]):.5f} -> {float(r["candidate_mean_score"]):.5f}', r["raw_length_stops"]] for r in qt])
    admitted = [r for r in paired_quality if r["experiment"] == "free-generation" and r["request_class"] == "admitted_compiled"]
    material = [r for r in admitted if float(r["quality_drop"]) > .03]
    roots = defaultdict(set)
    for r in material:
        roots[(r["model"], r["family"])].add(r["session_id"])
    lines += ["", f"There are **{len(material)} material drops among {len(admitted)} admitted future pairs** across the two budget conditions. "
              "These are future-scope robustness counterexamples, not zero regression. The cases are correlated within sessions and repeats, not independent failures. "
              "The global mean score drop remains very small or negative, but it must not replace the per-request tail-risk table.", ""]
    lines += table(["Model/family", "Distinct affected sessions"], [["/".join(k), len(v)] for k, v in sorted(roots.items())])
    lines += ["", "### Root-Cause Separation", "",
              "- In the three-model free-generation matrix, all compiled material drops occur on turns with new query wrappers (turns 1/2/4/5/7/8); none occur on the unwrapped-query turns 3/6/9. "
              "Repeated raw scores in the substantive cases are stable. Raw-vs-raw controls exhibit much less variation, so the main failures cannot be dismissed as numerical noise.",
              "- The code checks stable-prefix identity and generation budget, but does not turn a Turn-0 path certificate into a proof for a changed query. "
              "The defect is an insufficient future-input scope gate if such a certificate is consumed as an arbitrary-query guarantee. "
              "The conceptual boundary is that teacher-forced equivalence for one prompt does not imply equivalence for all future prompts.",
              "- Qasper includes an expression-length/F1 effect; RepoBench includes changed code completions and NarrativeQA changed answer content. "
              "Official thresholded scores are retained; benign-looking wording is not silently reclassified as a pass.",
              "- Prefix promotion itself passed: no accepted length-stop reference, no commit beyond the stable-only boundary, and no publication on rejected verification. "
              "This separates correct physical publication from overly broad behavioral scope.",
              "- No held-out family/layout/threshold was retuned and no success subset replaces the global denominator. "
              "A deployment repair must prospectively bind allowed query/suffix transformations or reattest new scopes; that repair's performance has not been measured in this frozen matrix.", ""]
    controls = [r for r in raw_controls if r["family"] == "ALL"]
    lines += table(["Experiment/model", "Budget", "Raw-repeat comparisons", "Token divergences", "Score abs diff >0.03"],
                   [[r["experiment"] + "/" + r["model"], r["budget_override"], r["raw_repeat_comparisons"],
                     r["token_divergences"], r["score_absolute_differences_gt_0_03"]] for r in controls])
    lines += ["", "Raw comparisons pair repeats 1-2, 1-3 and 2-3, so each request participates three times. "
              "They provide a control distribution, not causal exoneration of individual fallback mismatches.", "",
              "### Horizon Boundary", "",
              f"Among the {len(admitted)} admitted free-running pairs, "
              f"{sum(int(r['raw_output_tokens']) > 96 or int(r['candidate_output_tokens']) > 96 for r in admitted)} pairs actually exceed 96 output tokens. "
              "The 512 cap therefore tests an extended generation binding and length-stop handling, **not 512-token positive certified behavior**. "
              "Original main canaries did not archive their direct free-output token IDs; later futures did. "
              "The exact main source snapshot is retained, and this logging omission is not filled with inferred tokens.", "",
              "## X3. Complete Verification Cost and Live Zero-Slack Service", "",
              "Historical archived timing is audited without inventing missing reference or rejected-attempt clocks. "
              "Fresh R1 registration clocks include reference decode, token preparation and verification for both accepted and rejected sessions. "
              "The TP2 14B experiment is a fresh cost supplement, not a reconstruction of the earlier 44.69% result. "
              "The following session table measures the R1 maximum-level diagnostic variant; it does not substitute for missing exact historical clocks.", ""]
    cost_rows = []
    for model in ("qwen", "mistral", "llama", "qwen14"):
        subset = [r for r in costs if r["model"] == model and r["family"] == "ALL" and r["request_class"] == "ALL"
                  and r["slack_ms"] == "0" and r["budget_override"] in ("0", "96") and r["experiment"] != "common-hotpot"]
        if subset:
            cost_rows.append([model, sum(int(r["future_requests"]) for r in subset),
                              f'{fmean(subset, "registration_mean_ms_per_session"):.1f}',
                              f'{fmean(subset, "residual_registration_ms_per_future"):.1f}', pct(fmean(subset, "net_mean_ttft_reduction"))])
    lines += table(["Fresh model", "Futures", "Registration ms/session", "Full cost ms/future", "Zero-slack net TTFT reduction"], cost_rows)
    ruler_rows = []
    for model in ("qwen", "mistral", "llama"):
        subset = [r for r in costs if r["experiment"] == "free-generation" and r["model"] == model
                  and r["family"] == "RULER" and r["request_class"] == "admitted_compiled"
                  and r["slack_ms"] == "0" and r["budget_override"] == "0"]
        ruler_rows.append([model, sum(int(r["future_requests"]) for r in subset),
                           f'{fmean(subset, "raw_mean_ttft_ms"):.1f} -> {fmean(subset, "observed_mean_ttft_ms"):.1f}',
                           pct(fmean(subset, "net_mean_ttft_reduction"))])
    lines += ["", "A complementary within-family result is strong even with all registration charged and no slack. "
              "The RULER rows below are a labelled scope subset of the same frozen matrix; they do not replace the five-family global result.", ""]
    lines += table(["Model", "Native-budget RULER futures", "Observed mean TTFT ms", "Full-cost zero-slack net reduction"], ruler_rows)
    service = csv_rows(a.root / "zero_slack_service_by_repeat_v1.csv")
    sg = defaultdict(list)
    for r in service:
        if float(r["slo_ttft_ms"]) == 1500:
            sg[(r["model"], r["policy"])].append(r)
    service_rows = []
    for (model, policy), rows in sorted(sg.items()):
        service_rows.append([model, policy, f'{fmean(rows, "mean_ttft_ms"):.1f}',
                             f'{fmean(rows, "p99_ttft_ms"):.1f}', f'{fmean(rows, "end_to_end_slo_goodput_rps"):.3f}',
                             f'{fmean(rows, "registration_wall_s"):.2f}', pct(fmean(rows, "drop_rate")),
                             f'{fmean(rows, "mean_new_prefill_tokens"):.1f}'])
    lines += ["", "The service replay has 20 tenants across five frozen templates, 180 actual future task requests per cell, "
              "Poisson arrivals at 1.6 requests/s, max_num_seqs=2, and three fresh processes per policy/model. "
              "The verifier uses the same vLLM engine. Full registration plus business warming is charged to wall-clock goodput; nothing is subtracted as imaginary overlap.", ""]
    lines += table(["Model", "Policy", "Observed mean TTFT ms", "Observed p99 ms", "Cold-inclusive 1500ms goodput req/s",
                    "Registration+warmup s", "Drop rate", "New-prefill tokens"], service_rows)
    sq = csv_rows(a.root / "zero_slack_service_quality_summary_v1.csv")
    lines += ["", "Request TTFT begins after registration at actual submission. Cold-start delay is included in the end-to-end goodput denominator, "
              "not hidden in a claimed per-request p99. Client prompt preparation and server startup precede the declared interval. "
              "Verifier HTTP calls are counted from server logs, excluding the guard probe and separately from planned registration attempts.", ""]
    lines += table(["Model/policy", "Quality pairs", "Compiled", "Drops >0.03", "Mean score raw -> policy"],
                   [[r["model"] + "/" + r["policy"], r["paired_requests"], r["compiled_requests"], r["material_drops_gt_0_03"],
                     f'{float(r["raw_mean_score"]):.5f} -> {float(r["candidate_mean_score"]):.5f}'] for r in sq if r["family"] == "ALL"])
    lines += ["", "## X4. Value of Certification Beyond Layout-Only Serving", ""]
    guard = audit["live_guard"]
    actual_guard = audit["fresh_post_decision_guard"]
    lines += [f"The same legal declared-DAG candidate set contains {guard.get('cases', 0)} controlled prompts. "
              f"Of {guard.get('genuine_bad_layout_cases', 0)} candidates that actually reduce the task score, "
              f"{guard.get('bad_layouts_rejected', 0)} are rejected. Rejected publication totals "
              f"{guard.get('rejected_published_tokens', 'unavailable')} tokens. "
              "Raw and candidate outputs, the actual verifier decision, and commit state are retained.", "",
              "This is a controlled instruction-order negative control, not a benchmark aggregate. "
              "The score strips only a reasoning wrapper and accepts the exact requested color. "
              "A dependency graph declared by the caller can omit a semantic constraint; the behavioral verifier is useful precisely in that case.", "",
              "The initial Qwen3-8B probe's effective score is a routing-accounted value from already generated raw/candidate outputs, not a new post-decision generation. "
              "It demonstrates actual rejection and transaction-scoped zero publication. A supplementary probe closes that final output step with fresh business requests.", "",
              "D1 is an offline frozen-safe reference without online attestation; D2 adds evidence-bound shared-state admission. "
              "D2 is not required to beat D1's latency. Its claimed benefit is rejecting unsafe promotion while retaining useful reuse on accepted scopes.", "",
              f"The supplementary {actual_guard.get('model', 'unavailable')} TP2 probe executes "
              f"{actual_guard.get('cases', 0)} fresh post-decision business outputs. "
              f"It rejects {actual_guard.get('bad_layouts_rejected', 0)}/{actual_guard.get('genuine_bad_layout_cases', 0)} genuinely bad candidates; "
              f"all protected scores equal raw: {actual_guard.get('fresh_protected_scores_equal_raw', False)}. "
              f"Rejected publication: {actual_guard.get('rejected_published_tokens', 'unavailable')} tokens. "
              "This supplemental probe runs only after a main cell's raw file and timing summary are finalized, and does not enter that cell's future-count or wall-time denominator.", "",
              "## X5. Manifest Correctness and Isolation Boundary", ""]
    trust = json.loads((a.root / "registration_manifest_summary_v1.json").read_text())
    lines += [f"The {trust['cases']}-case CPU registration validator rejects untrusted issuer/role, stale signatures/hashes, "
              "missing authorization/version, and explicitly private or mutable publication. All expected outcomes match. "
              "A correctly signed trusted-operator declaration that mislabels private content as public is deliberately accepted: "
              "hashes establish byte identity, not confidentiality. This is an explicit trust boundary, not a claimed live confidentiality defense.", "",
              "The R1 endpoint is operator-internal and bound to localhost. Shared-prefix authorization does not eliminate hit-timing inference "
              "within an authorized domain. The prototype does not implement a prefix-cache timing-channel defense.", "",
              "## X6. Baseline Fairness, Statistics and Input Differences", ""]
    baseline = [r for r in csv_rows(a.root / "matched_baseline_quality_thresholds_v1.csv") if r["family"] == "ALL" and r["threshold"] == "0.03"]
    lines += table(["Method", "Native paired baseline", "Pairs", "Mean score raw -> method", "Material drops", "Material improvements"],
                   [[r["method"], r["matched_baseline"], r["paired_requests"],
                     f'{float(r["baseline_mean_score"]):.5f} -> {float(r["candidate_mean_score"]):.5f}',
                     r["material_regressions"], r["material_improvements"]] for r in baseline])
    lines += ["", "CacheBlend's aggregate quality improvement and per-request regressions can coexist. "
              "Its original study reports aggregate F1/Rouge on different models and datasets, not this workload's >0.03 per-request statistic. "
              "Threshold sensitivity (0.01/0.03/0.05) and family-level improvements/regressions are supplied. "
              "Neither 112x causal safety nor 2.18% cross-stack performance superiority is asserted.", "",
              "The exact frozen-tokenizer input analysis retains 4,695 segment observations: raw/candidate order index, token position, displacement, "
              "prompt length and render-token identity. Stable context is moved before the volatile observation when the frozen layout permits it. "
              "These are measured input differences, not claims about RoPE or attention as an architectural root cause.", "",
              "## X7. Reproducibility and Completion", "",
              f"Required live cells completed: **{audit['complete_live_cells']}/{audit['expected_live_cells']}**. "
              f"Measured futures: **{audit['observed_measured_future_requests']}/{audit['expected_measured_future_requests']}**. "
              "Raw hashes, request identities, complete registration clocks, actual token evidence, metric joins and rejected-publication invariants "
              "are checked on the authoritative remote raw root. Private credential archives are not part of the public package.", "",
              "The actual executed main source is SHA-verified in `source_snapshots/tsc_revision_live_main_v1.py`; "
              "later logging-only additions are separately identified. The serving patch is archived against official vLLM v0.10.2, "
              "alongside package versions and the non-test result-code inventory. "
              "Superseded boundary/startup attempts remain quarantined and excluded from formal tables.", "",
              "## Scientific Bottom Line", "",
              "The physical reuse and fail-closed publication mechanism remain supported. The non-RULER common scope is a positive mechanism test. "
              "The broader unseen-query-wrapper free-generation test exposes a real future-scope boundary; it cannot be presented as globally zero regression. "
              "Cold-session verification economics are weaker than slack-accounted or high-fan-out service results. "
              "These distinctions should strengthen the revised paper's argument by making its scope enforceable, not be hidden behind only the best numbers.", ""]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text("\n".join(lines), encoding="utf-8")
    result = {"schema_version": "tsc-revision-report.v1", "experimental_execution_complete": audit["experimental_execution_complete"],
              "common_hotpot": common_json, "free_generation_admitted_pairs": len(admitted),
              "free_generation_material_drops_on_admitted": len(material), "guard": guard,
              "fresh_post_decision_guard": actual_guard,
              "manuscript_and_response_letter_not_yet_revised": True,
              "original_claims_not_silently_replaced_by_new_protocol": True}
    (a.root / "final_report_metrics_v1.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "common_hotpot"}))


if __name__ == "__main__": main()
