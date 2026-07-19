#!/usr/bin/env python3
"""Render paper-facing reports for the TSC service-evaluation extension."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def percent(value: Any) -> str:
    return f"{number(value):.2%}"


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def p0_1(root: Path, docs: Path) -> None:
    rows = read_csv(root / "open_loop_policy_comparison_v0.csv")
    locality = read_csv(root / "service_locality_policy_comparison_v0.csv")
    confidence = read_csv(root / "service_locality_confidence_intervals_v0.csv")
    residency = read_csv(root / "locality_residency_policy_comparison_v0.csv")
    primary = [row for row in rows if number(row["slo_ttft_ms"]) in {500, 1000, 1500, 3000}]
    lines = [
        "# P0-1 Open-Loop SLO Service Evaluation", "",
        "## Scope", "",
        "Real vLLM Poisson and ON/OFF serving cells; every cell uses the frozen 1,125-request trace and three fresh-process repeats. Registration cost that is not hidden by tool slack is amortized into the SLO test.", "",
        "## ContractKV versus native vLLM APC", "",
        "| Model | Arrival | Load | SLO (ms) | SLO-goodput multiplier | Mean TTFT reduction | p99 TTFT reduction | New-prefill reduction | D0 completion | D2 completion |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(primary, key=lambda item: (item["model"], item["arrival_mode"], number(item["load_fraction"]), number(item["slo_ttft_ms"]))):
        lines.append(
            f"| {row['model']} | {row['arrival_mode']} | {number(row['load_fraction']):.0%} | {number(row['slo_ttft_ms']):.0f} | "
            f"{number(row['contractkv_vs_raw_goodput_multiplier']):.2f}x | {percent(row['contractkv_vs_raw_mean_ttft_reduction'])} | "
            f"{percent(row['contractkv_vs_raw_p99_ttft_reduction'])} | {percent(row['contractkv_vs_raw_new_prefill_reduction'])} | "
            f"{percent(row['raw_completion_rate'])} | {percent(row['contractkv_completion_rate'])} |"
        )
    positive = [number(row["contractkv_vs_raw_goodput_multiplier"]) for row in primary if number(row["contractkv_vs_raw_goodput_multiplier"]) > 0]
    lines += ["", "## Evidence boundary", "",
              f"Primary comparison rows: {len(primary)}; observed SLO-goodput multiplier range: {min(positive, default=0):.2f}x-{max(positive, default=0):.2f}x.",
              "Marker sanity checks the serving path and is not official benchmark scoring. Full per-cell queue, GPU, block-pool, and transport fields remain in `results/tsc_service/open_loop_cell_summary_v0.csv`."]
    lines += ["", "## Service-template locality", "",
              "The natural mixed trace is retained as a low-locality boundary. The prospective locality sweep changes only authorized stable-template sharing; tenant-private suffixes and the arrival trace remain frozen.", "",
              "| Model | Tenants/template | Policy | Load | SLO (ms) | Goodput multiplier | Mean TTFT reduction | p99 reduction | New-prefill reduction |", "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for row in sorted([item for item in locality if number(item["slo_ttft_ms"]) in {500, 1000, 1500, 3000}
                       and .6 <= number(item["load_fraction"]) <= 1.4],
                      key=lambda item: (item["model"], number(item["tenants_per_template"]), item["policy"], number(item["load_fraction"]), number(item["slo_ttft_ms"]))):
        lines.append(f"| {row['model']} | {number(row['tenants_per_template']):.0f} | {row['policy']} | {number(row['load_fraction']):.0%} | {number(row['slo_ttft_ms']):.0f} | {number(row['slo_goodput_multiplier_vs_raw']):.2f}x | {percent(row['mean_ttft_reduction_vs_raw'])} | {percent(row['p99_ttft_reduction_vs_raw'])} | {percent(row['new_prefill_reduction_vs_raw'])} |")
    lines += ["", "## Certificate fan-out", "",
              "| Model | Policy | Tenants/template | Verifier calls | Commits | Fan-out | Unhidden ms/request | Mean TTFT reduction |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in sorted([item for item in locality if number(item["load_fraction"]) == .8
                       and number(item["slo_ttft_ms"]) == 1500],
                      key=lambda item: (item["model"], number(item["tenants_per_template"]), item["policy"])):
        lines.append(
            f"| {row['model']} | {row['policy']} | {number(row['tenants_per_template']):.0f} | "
            f"{number(row.get('actual_verifier_endpoint_calls')):.1f} | {number(row.get('transaction_commits')):.1f} | "
            f"{number(row.get('verification_fanout')):.1f} | {number(row.get('unhidden_verification_ms_per_future_request')):.3f} | "
            f"{percent(row.get('mean_ttft_reduction_vs_raw'))} |"
        )
    lines += ["", "## Hierarchical uncertainty", "",
              "Confidence intervals resample fresh process, service template, and tenant session. p99 is reported as the range across the three fresh repeats rather than by pooling all requests.", "",
              "| Model | SLO (ms) | Mean TTFT reduction (95% CI) | p99 reduction repeat range | New-prefill repeat range | SLO-goodput delta req/s (95% CI) | Multiplier (95% CI when identifiable) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in confidence:
        ratio_ci = (f"{number(row['slo_goodput_multiplier']):.2f}x "
                    f"[{number(row['slo_goodput_multiplier_ci_low']):.2f}x, {number(row['slo_goodput_multiplier_ci_high']):.2f}x]"
                    if str(row.get("slo_goodput_multiplier_ci_identifiable", "")).lower() == "true"
                    else f"{number(row['slo_goodput_multiplier']):.2f}x [ratio CI not identifiable: clustered D0 crosses zero]")
        lines.append(
            f"| {row['model']} | {number(row['slo_ttft_ms']):.0f} | {percent(row['mean_ttft_reduction'])} "
            f"[{percent(row['mean_ttft_reduction_ci_low'])}, {percent(row['mean_ttft_reduction_ci_high'])}] | "
            f"[{percent(row['p99_ttft_reduction_repeat_min'])}, {percent(row['p99_ttft_reduction_repeat_max'])}] | "
            f"[{percent(row['new_prefill_reduction_repeat_min'])}, {percent(row['new_prefill_reduction_repeat_max'])}] | "
            f"{number(row['slo_goodput_delta_rps']):.3f} [{number(row['slo_goodput_delta_ci_low']):.3f}, "
            f"{number(row['slo_goodput_delta_ci_high']):.3f}] | {ratio_ci} |"
        )
    lines += ["", "The former single-number 1,500-ms sustainable-capacity ratio is intentionally omitted: native D0 is already below that p99 gate at the lowest measured load, so its denominator is zero. The paper-facing result is the complete 60%-140% load-p99-goodput curve. Loads above 140% remain an overload appendix and are not headline evidence."]
    lines += ["", "## Locality-residency operating region", "",
              "Exact vLLM eviction counts are unavailable in the scheduler probe and are not fabricated. Reuse distance, prefix-hit ratio, new-prefill work, and zero-hit-after-prior-template requests are reported instead.", "",
              "| Active templates | Arrival order | Mean reuse distance | Prefix-hit ratio | New-prefill reduction | Net mean TTFT reduction | SLO-goodput multiplier |", "|---:|---|---:|---:|---:|---:|---:|"]
    for row in sorted([item for item in residency if number(item["slo_ttft_ms"]) == 1500],
                      key=lambda item: (number(item["active_templates"]), item["arrival_distribution"])):
        lines.append(
            f"| {number(row['active_templates']):.0f} | {row['arrival_distribution']} | "
            f"{number(row['mean_reuse_distance_requests']):.1f} | {percent(row['contractkv_prefix_hit_ratio'])} | "
            f"{percent(row['new_prefill_reduction'])} | {percent(row['net_mean_ttft_reduction'])} | "
            f"{number(row['slo_goodput_multiplier']):.2f}x |"
        )
    write(docs / "tsc_p0_1_open_loop_slo_report.md", lines)


def p0_2(root: Path, docs: Path) -> None:
    rows = [row for row in read_csv(root / "multi_tenant_aggregate_v0.csv")
            if row.get("kind") == "stageC" and row.get("service_class") == "ALL"]
    lines = [
        "# P0-2 Multi-Tenant Isolation and Fairness", "", "## Forty-tenant sharing curve", "",
        "| Policy | Authorized sharing | Completion | Mean TTFT (ms) | p95 TTFT (ms) | Steady SLO req/s | Cold-start SLO req/s | Jain fairness | Verifier calls | Fan-out | Unauthorized reuse | Dynamic suffix reuse | Scope-invalid admission |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda item: (number(item["sharing_ratio"]), item["policy"])):
        lines.append(
            f"| {row['policy']} | {number(row['sharing_ratio']):.0%} | {percent(row['mean_completion_rate'])} | "
            f"{number(row['mean_mean_ttft_ms']):.1f} | {number(row['mean_p95_ttft_ms']):.1f} | "
            f"{number(row['mean_slo_compliant_goodput_rps']):.3f} | {number(row['mean_cold_start_amortized_slo_goodput_rps']):.3f} | "
            f"{number(row['mean_jain_tenant_slo_fairness']):.4f} | {number(row.get('mean_actual_verifier_endpoint_calls')):.1f} | "
            f"{number(row.get('mean_verification_fanout')):.1f} | {number(row['mean_unauthorized_cross_tenant_reuse']):.0f} | "
            f"{number(row['mean_dynamic_suffix_reuse_blocks']):.0f} | {number(row['mean_scope_invalid_admissions']):.0f} |"
        )
    lines += ["", "## Safety interpretation", "",
              "Tenant identity, authorization scope, policy hash, and private suffix are part of the real prompt/cache key. Both steady-state and registration-amortized goodput are reported; ContractKV is not claimed to implement priority scheduling."]
    write(docs / "tsc_p0_2_multi_tenant_report.md", lines)


def p0_3(root: Path, docs: Path) -> None:
    rows = []
    for path in sorted((root / "economics").glob("*_boundary_live_v0.csv")):
        rows.extend(read_csv(path))
    lines = ["# P0-3 Verification Economics", "", "## Live boundary points", "",
             "| Model | Live lanes | Accepted | Fail-closed fallback | Positive lanes | Positive fraction | Mean registration (ms) | Mean unhidden verification (ms) | Mean net benefit (ms) |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for model in sorted({row.get("model_identity", "") for row in rows}):
        group = [row for row in rows if row.get("model_identity") == model]
        positive = [row for row in group if number(row.get("observed_net_benefit_ms")) > 0]
        accepted = [row for row in group if str(row.get("certificate_issued", "")).lower() == "true"]
        lines.append(
            f"| {model} | {len(group)} | {len(accepted)} | {len(group) - len(accepted)} | {len(positive)} | {len(positive) / max(1, len(group)):.2%} | "
            f"{statistics.mean(number(row.get('registration_ms')) for row in group):.1f} | "
            f"{statistics.mean(number(row.get('unhidden_verification_ms')) for row in group):.1f} | "
            f"{statistics.mean(number(row.get('observed_net_benefit_ms')) for row in group):.1f} |"
        )
    lines += ["", "## Operating-region definition", "",
              "This is a deployment operating-region analysis, not a perfect online benefit predictor. The analytical contour interpolates only measured registration cost and measured per-turn savings. A rejected certificate executes raw-order fallback and remains in the live table; accepted and positive-benefit counts are reported separately, including accepted negative-benefit lanes. Live boundary lanes remain separately identifiable, and the offline contour is not presented as serving throughput."]
    write(docs / "tsc_p0_3_verification_economics_report.md", lines)


def p0_4(root: Path, docs: Path) -> None:
    path = root / "lifecycle/lifecycle_summary_v0.json"
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    lines = ["# P0-4 Service Lifecycle and Certificate Scope", "", "## Gate", "",
             f"- Events: {summary.get('events', 0)}",
             f"- Old certificates invalidated: {summary.get('old_certificates_immediately_invalidated', False)}",
             f"- Old-prefix consumption after scope change is zero: {summary.get('old_prefix_consumption_zero', False)}",
             f"- Unrelated scopes continue: {summary.get('unrelated_scope_continues', False)}",
             f"- Cross-version contamination is zero: {summary.get('cross_version_contamination_zero', False)}",
             f"- Overall gate: {summary.get('gate_pass', False)}", "", "## Boundary", "",
             "Template/context/schema/policy/qualification/tenant changes are live routing-scope tests. Model and tokenizer changes validate scope invalidation without claiming in-process weight or tokenizer hot reload. Cancellation and duplicate-finalize rows reuse the real Phase 18 compact-wire fault evidence."]
    write(docs / "tsc_p0_4_service_lifecycle_report.md", lines)


def p0_a(root: Path, docs: Path) -> None:
    rows = read_csv(root / "service_template_quality_summary_v0.csv")
    gate_path = root / "service_template_quality_gate_v0.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    negative_path = root / "service_template_quality_all_compiled_negative_control_v0.json"
    negative = json.loads(negative_path.read_text(encoding="utf-8")) if negative_path.exists() else {}
    lines = [
        "# P0-A Service-Template Formal Task-Quality Audit", "", "## Protocol", "",
        "Five semantically coherent deployed templates (RULER, HotpotQA, NarrativeQA, Qasper, and RepoBench) are each consumed by ten authorized tenants for ten turns. D0 raw order and D2 template-certificate cells use three paired fresh processes. Each tenant receives the same template-consistent context, query, and answer; only a neutral private tool-observation identity changes. Generation uses the frozen task budgets rather than the 64-token marker budget.", "",
        "| Family | Paired future outputs | Raw score | D2 score | Paired delta (95% cluster CI) | Violations >0.03 | Raw fallback |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['family']} | {number(row['paired_future_outputs']):.0f} | {number(row['raw_mean_score']):.6f} | "
            f"{number(row['contract_mean_score']):.6f} | {number(row['paired_difference']):+.6f} "
            f"[{number(row['cluster_bootstrap_ci_low']):+.6f}, {number(row['cluster_bootstrap_ci_high']):+.6f}] | "
            f"{number(row['quality_violations_gt_0_03']):.0f} | {percent(row['raw_fallback_rate'])} |"
        )
    lines += ["", "## Safety gate", "",
              f"Overall gate: **{'PASS' if gate.get('gate_pass') else 'FAIL/INCOMPLETE'}**. "
              f"Paired future outputs: {gate.get('paired_future_outputs', 0)}; completion 100%: {gate.get('completion_100pct', False)}; "
              f"policy quality violations zero: {gate.get('policy_quality_violations_zero', False)}; scope-invalid admissions zero: {gate.get('scope_invalid_admissions_zero', False)}; "
              f"unauthorized reuse zero: {gate.get('unauthorized_reuse_zero', False)}.", "",
              "The hierarchical bootstrap resamples fresh process, service template, and tenant session. This closes certificate fan-out for four qualified templates and fail-closed behavior across all five; it does not replace the broader frozen full-task quality experiments.", "",
              "## Fail-closed negative control", "",
              f"The archived policy that issued certificates to all five templates produced {negative.get('archived_metric_drops_gt_0_03', 0)} paired metric drops. "
              f"All were Qasper: {negative.get('all_drops_qasper', False)}. The pre-existing Qasper risk qualification therefore remains raw-order; the paper-facing guarded policy eliminates those drops: {negative.get('safe_policy_eliminates_drops', False)}. "
              "The archived rows remain machine-readable and are not counted as successful ContractKV admissions."]
    write(docs / "tsc_p0_a_service_template_quality_report.md", lines)


def p0_b(root: Path, docs: Path) -> None:
    rows = read_csv(root / "certificate_granularity_ablation_v0.csv")
    gate_path = root / "certificate_granularity_ablation_gate_v0.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    lines = [
        "# P0-B Certificate-Object Granularity Ablation", "", "## Controlled setup", "",
        "Qwen3-8B, 25 tenants per service template, the identical frozen 1,125-request trace, 80% offered load, and three fresh processes. D0, D1, D2-Session, and D2-Template use the same prompt layouts within their safe-layout class; only certificate granularity changes between the two D2 rows.", "",
        "| Policy | Verifier calls | Commits | Fan-out | Unhidden verify ms/request | New-prefill tokens | Prefix-hit ratio | Mean/p99 TTFT (ms) | 1500-ms SLO req/s |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['policy']} | {number(row['mean_actual_verifier_endpoint_calls']):.1f} | "
            f"{number(row['mean_transaction_commits']):.1f} | {number(row['mean_verification_fanout']):.1f} | "
            f"{number(row['mean_unhidden_verification_ms_per_future_request']):.3f} | "
            f"{number(row['mean_mean_new_prefill_tokens']):.1f} | {percent(row['mean_template_prefix_hit_ratio'])} | "
            f"{number(row['mean_mean_ttft_ms']):.1f}/{number(row['mean_p99_ttft_ms']):.1f} | "
            f"{number(row['mean_slo_compliant_goodput_rps']):.3f} |"
        )
    lines += ["", "## Causal conclusion", "",
              f"Overall gate: **{'PASS' if gate.get('gate_pass') else 'FAIL/INCOMPLETE'}**. "
              f"D2 session/template new-prefill delta: {number(gate.get('prefix_work_delta_tokens')):.1f} tokens "
              f"({percent(gate.get('prefix_work_delta_fraction_prompt'))} of prompt). "
              f"Template verifier calls lower: {gate.get('template_verifier_calls_lt_session', False)}; "
              f"template verification cost per future request lower: {gate.get('template_verification_ms_per_request_lt_session', False)}.", "",
              "The ablation isolates the economic effect of certificate-object granularity: service-template certificates amortize one verification across authorized sessions without changing the layout or manufacturing additional prefix hits. Quality, dynamic-suffix isolation, and cross-domain isolation remain unchanged."]
    write(docs / "tsc_p0_b_certificate_granularity_ablation_report.md", lines)


def p1_1(root: Path, docs: Path) -> None:
    rows = [row for row in read_csv(root / "multi_tenant_aggregate_v0.csv")
            if row.get("kind") == "density" and row.get("service_class") == "ALL"]
    lines = ["# P1-1 Service Density and Consolidation", "", "## Density sweep", "",
             "| Policy | Tenants | Completion | SLO req/s | Mean TTFT (ms) | p95 TTFT (ms) | Peak used blocks | Minimum free blocks |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in sorted(rows, key=lambda item: (number(item["tenants"]), item["policy"])):
        lines.append(f"| {row['policy']} | {number(row['tenants']):.0f} | {percent(row['mean_completion_rate'])} | {number(row['mean_slo_compliant_goodput_rps']):.3f} | {number(row['mean_mean_ttft_ms']):.1f} | {number(row['mean_p95_ttft_ms']):.1f} | {number(row['mean_peak_used_gpu_blocks']):.1f} | {number(row['mean_minimum_free_gpu_blocks']):.1f} |")
    lines += ["", "Capacity failures are retained as results rather than aborting the sweep. Density is reported in tenants and real vLLM block-pool occupancy; no token-to-GiB conversion is invented when a physical byte mapping is unavailable."]
    write(docs / "tsc_p1_1_service_density_report.md", lines)


def p1_2(root: Path, docs: Path) -> None:
    rows = [row for row in read_csv(root / "multi_tenant_aggregate_v0.csv")
            if row.get("kind") == "stageC" and number(row.get("sharing_ratio")) == 1.0
            and row.get("service_class") != "ALL"]
    lines = ["# P1-2 Gold/Silver/Bronze Service Classes", "", "## Fully authorized 40-tenant cell", "",
             "| Policy | Class | Completion | SLO req/s | Mean TTFT (ms) | p95 TTFT (ms) | Weighted goodput | Jain fairness |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in sorted(rows, key=lambda item: (item["policy"], item["service_class"])):
        lines.append(f"| {row['policy']} | {row['service_class']} | {percent(row['mean_completion_rate'])} | {number(row['mean_slo_compliant_goodput_rps']):.3f} | {number(row['mean_mean_ttft_ms']):.1f} | {number(row['mean_p95_ttft_ms']):.1f} | {number(row['mean_weighted_slo_goodput']):.3f} | {number(row['mean_jain_tenant_slo_fairness']):.4f} |")
    lines += ["", "Gold/Silver/Bronze use 750/1500/3000 ms TTFT SLOs with weights 3/2/1. This evaluates whether prefix optimization creates severe class or tenant unfairness; it is not a claim of SLA-aware scheduling."]
    write(docs / "tsc_p1_2_service_class_report.md", lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/tsc_service"))
    parser.add_argument("--docs", type=Path, default=Path("docs"))
    args = parser.parse_args()
    p0_1(args.root, args.docs); p0_2(args.root, args.docs); p0_3(args.root, args.docs)
    p0_4(args.root, args.docs); p0_a(args.root, args.docs); p0_b(args.root, args.docs)
    p1_1(args.root, args.docs); p1_2(args.root, args.docs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
