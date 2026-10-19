#!/usr/bin/env python3
"""Summarize service-template quality, certificate granularity, and headline CIs."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


LOCALITY_RE = re.compile(r"(?P<model>qwen|mistral)_g(?P<level>\d+)_r(?P<repeat>\d+)_(?P<policy>D[012]-[^_]+)_f(?P<fraction>.+)")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values); position = (len(values) - 1) * q
    lower = int(position); upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row)) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def cluster_index(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    """Index rows once so hierarchical bootstrap does not rescan a cell per draw."""
    rows_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sessions_by_template: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        session = str(row["session_id"])
        template = str(row["service_template_id"])
        rows_by_session[session].append(row)
        sessions_by_template[template].add(session)
    templates = sorted(sessions_by_template)
    return templates, {key: sorted(value) for key, value in sessions_by_template.items()}, dict(rows_by_session)


def quality_summary(root: Path, iterations: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cells = root / "quality/cells"
    index: dict[tuple[int, str], list[dict[str, Any]]] = {}
    summaries = []
    registrations = []
    for path in sorted(cells.glob("qwen_r*_*/raw.jsonl")):
        match = re.fullmatch(r"qwen_r(?P<repeat>\d+)_(?P<policy>D[02]-[^/]+)", path.parent.name)
        if not match:
            continue
        key = (int(match.group("repeat")), match.group("policy"))
        index[key] = load_jsonl(path)
        summaries.extend(load_jsonl(path.parent / "summary.jsonl"))
        registrations.extend(load_jsonl(path.parent / "registration.jsonl"))

    pairs = []
    for repeat in (1, 2, 3):
        raw = {(row["session_id"], int(row["turn_id"])): row for row in index.get((repeat, "D0-native-apc"), [])}
        contract = {(row["session_id"], int(row["turn_id"])): row for row in index.get((repeat, "D2-template-contractkv"), [])}
        for key in sorted(set(raw) & set(contract)):
            r, c = raw[key], contract[key]
            pairs.append({
                "repeat": repeat, "service_template_id": r["service_template_id"], "tenant_id": r["tenant_id"],
                "session_id": r["session_id"], "family": r["family"], "dataset": r["dataset"], "task": r["task"],
                "sample_id": r["sample_id"], "turn_id": r["turn_id"],
                "raw_success": r["success"], "contract_success": c["success"],
                "raw_score": r["task_score"], "contract_score": c["task_score"],
                "paired_difference": number(c["task_score"]) - number(r["task_score"]),
                "quality_violation_gt_0_03": number(r["task_score"]) - number(c["task_score"]) > .03,
                "contract_effective_policy": c["effective_policy"], "scope_check_pass": c["scope_check_pass"],
                "metric": c["metric"], "metric_source": c["metric_source"],
            })

    rng = random.Random(27019)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        groups[str(row["family"])].append(row)
        groups["ALL"].append(row)
    output = []
    for family, rows in sorted(groups.items()):
        templates = sorted({str(row["service_template_id"]) for row in rows})
        sessions = sorted({str(row["session_id"]) for row in rows})
        repeats = sorted({int(row["repeat"]) for row in rows})
        repeat_indexes = {}
        for repeat in repeats:
            repeat_rows = [row for row in rows if int(row["repeat"]) == repeat]
            repeat_indexes[repeat] = cluster_index(repeat_rows)
        draws = []
        for _ in range(iterations):
            selected = []
            for repeat in [rng.choice(repeats) for _ in repeats]:
                repeat_templates, sessions_by_template, rows_by_session = repeat_indexes[repeat]
                sampled_templates = [rng.choice(repeat_templates) for _ in repeat_templates]
                for template in sampled_templates:
                    template_sessions = sessions_by_template[template]
                    for session in [rng.choice(template_sessions) for _ in template_sessions]:
                        selected.extend(rows_by_session[session])
            draws.append(statistics.mean(number(row["paired_difference"]) for row in selected))
        diff = statistics.mean(number(row["paired_difference"]) for row in rows)
        output.append({
            "family": family, "paired_future_outputs": len(rows), "fresh_process_repeats": len(repeats),
            "service_templates": len(templates), "tenant_sessions": len(sessions),
            "completion_rate": sum(truth(row["raw_success"]) and truth(row["contract_success"]) for row in rows) / max(1, len(rows)),
            "raw_mean_score": statistics.mean(number(row["raw_score"]) for row in rows),
            "contract_mean_score": statistics.mean(number(row["contract_score"]) for row in rows),
            "paired_difference": diff, "cluster_bootstrap_ci_low": percentile(draws, .025),
            "cluster_bootstrap_ci_high": percentile(draws, .975),
            "quality_violations_gt_0_03": sum(truth(row["quality_violation_gt_0_03"]) for row in rows),
            "raw_fallback_rate": sum(row["contract_effective_policy"] == "raw-fallback" for row in rows) / max(1, len(rows)),
        })
    gate = {
        "paired_future_outputs": len(pairs), "expected_paired_future_outputs": 1350,
        "completion_100pct": bool(pairs) and all(truth(row["raw_success"]) and truth(row["contract_success"]) for row in pairs),
        "policy_quality_violations_zero": bool(pairs) and not any(truth(row["quality_violation_gt_0_03"]) for row in pairs),
        "paired_quality_ci_low_ge_minus_0_03": bool(output) and all(number(row["cluster_bootstrap_ci_low"]) >= -.03 for row in output),
        "scope_invalid_admissions_zero": bool(summaries) and all(number(row.get("scope_invalid_admissions")) == 0 for row in summaries),
        "unauthorized_reuse_zero": bool(summaries) and all(number(row.get("unauthorized_cross_template_reused_hashes")) == 0 for row in summaries),
        "dynamic_suffix_reuse_zero": bool(summaries) and all(number(row.get("dynamic_suffix_reuse_blocks")) == 0 for row in summaries),
        "qualified_template_certificate_fanout": sum(truth(row.get("certificate_issued")) for row in registrations
                                                       if row.get("verify_decision") != "RAW_REGISTRATION") == 12,
        "unqualified_template_raw_fallback": sum(row.get("verify_decision") == "FROZEN_RAW_FALLBACK"
                                                   for row in registrations) == 3,
        "claim_boundary": "Five task-bearing service templates with hierarchical paired bootstrap; four qualified templates share certificates and Qasper fails closed to raw order.",
    }
    gate["gate_pass"] = len(pairs) == 1350 and all(value for key, value in gate.items()
                                                        if key not in {"paired_future_outputs", "expected_paired_future_outputs", "claim_boundary", "gate_pass"})
    return pairs, output, gate


def locality_cells(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "locality_cells").glob("*/summary.jsonl")):
        match = LOCALITY_RE.fullmatch(path.parent.name)
        if not match:
            continue
        for row in load_jsonl(path):
            row.update({"model": match.group("model"), "tenants_per_template": int(match.group("level")),
                        "repeat": int(match.group("repeat")), "load_fraction": float(match.group("fraction").replace("p", "."))})
            rows.append(row)
    return rows


def granularity_summary(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [row for row in locality_cells(root)
            if row["model"] == "qwen" and row["tenants_per_template"] == 25
            and row["repeat"] in {1, 2, 3} and abs(row["load_fraction"] - .8) < 1e-9
            and number(row["slo_ttft_ms"]) == 1500
            and row["policy"] in {"D0-native-apc", "D1-frozen-safe", "D2-session-contractkv", "D2-template-contractkv"}]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["policy"])].append(row)
    metrics = ["actual_verifier_endpoint_calls", "transaction_commits", "verification_fanout",
               "unhidden_verification_ms_per_future_request", "mean_prompt_tokens", "mean_new_prefill_tokens", "template_prefix_hit_ratio",
               "mean_ttft_ms", "p99_ttft_ms", "slo_compliant_goodput_rps", "completion_rate",
               "quality_sanity_rate", "unauthorized_cross_domain_reused_hashes", "dynamic_suffix_reuse_blocks"]
    output = []
    for policy, group in sorted(grouped.items()):
        item = {"policy": policy, "fresh_process_repeats": len(group), "future_requests": sum(int(row["offered_requests"]) for row in group)}
        for metric in metrics:
            item[f"mean_{metric}"] = statistics.mean(number(row.get(metric)) for row in group)
        output.append(item)
    lookup = {row["policy"]: row for row in output}
    session = lookup.get("D2-session-contractkv", {}); template = lookup.get("D2-template-contractkv", {})
    prefix_delta_tokens = abs(number(session.get("mean_mean_new_prefill_tokens"))
                              - number(template.get("mean_mean_new_prefill_tokens")))
    prompt_tokens = max(number(session.get("mean_mean_prompt_tokens")),
                        number(template.get("mean_mean_prompt_tokens")), 1e-9)
    prefix_delta_fraction_prompt = prefix_delta_tokens / prompt_tokens
    gate = {
        "four_strategies_present": set(lookup) == {"D0-native-apc", "D1-frozen-safe", "D2-session-contractkv", "D2-template-contractkv"},
        "three_fresh_repeats_each": bool(output) and all(int(row["fresh_process_repeats"]) == 3 for row in output),
        "same_future_requests_each": bool(output) and all(int(row["future_requests"]) == 3375 for row in output),
        "d2_prefix_work_delta_le_one_block": prefix_delta_tokens <= 16.0,
        "d2_prefix_work_delta_le_1pct_prompt": prefix_delta_fraction_prompt <= .01,
        "template_verifier_calls_lt_session": number(template.get("mean_actual_verifier_endpoint_calls")) < number(session.get("mean_actual_verifier_endpoint_calls")),
        "template_verification_ms_per_request_lt_session": number(template.get("mean_unhidden_verification_ms_per_future_request")) < number(session.get("mean_unhidden_verification_ms_per_future_request")),
        "quality_and_isolation_safe": bool(output) and all(
            number(row["mean_completion_rate"]) == 1.0 and number(row["mean_quality_sanity_rate"]) == 1.0
            and number(row["mean_unauthorized_cross_domain_reused_hashes"]) == 0
            and number(row["mean_dynamic_suffix_reuse_blocks"]) == 0 for row in output),
        "prefix_work_delta_tokens": prefix_delta_tokens,
        "prefix_work_delta_fraction_prompt": prefix_delta_fraction_prompt,
    }
    gate["gate_pass"] = all(value for key, value in gate.items()
                            if key not in {"prefix_work_delta_tokens", "prefix_work_delta_fraction_prompt", "gate_pass"})
    return output, gate


def sample_cell(index: tuple[list[str], dict[str, list[str]], dict[str, list[dict[str, Any]]]],
                rng: random.Random) -> list[dict[str, Any]]:
    templates, sessions_by_template, rows_by_session = index
    selected = []
    for template in [rng.choice(templates) for _ in templates]:
        sessions = sessions_by_template[template]
        for session in [rng.choice(sessions) for _ in sessions]:
            selected.extend(rows_by_session[session])
    return selected


def headline_ci(root: Path, iterations: int) -> list[dict[str, Any]]:
    output = []; rng = random.Random(27020)
    for model in ("qwen", "mistral"):
        cells: dict[tuple[int, str], list[dict[str, Any]]] = {}
        summaries: dict[tuple[int, str], dict[str, Any]] = {}
        for path in (root / "locality_cells").glob(f"{model}_g25_r[123]_*_f*p8/raw.jsonl"):
            match = LOCALITY_RE.fullmatch(path.parent.name)
            if not match or match.group("policy") not in {"D0-native-apc", "D2-template-contractkv"}:
                continue
            key = (int(match.group("repeat")), match.group("policy")); cells[key] = load_jsonl(path)
            summary = load_jsonl(path.parent / "summary.jsonl")
            summaries[key] = next(row for row in summary if number(row["slo_ttft_ms"]) == 1500)
        if len(cells) != 6:
            continue
        indexed_cells = {key: cluster_index(rows) for key, rows in cells.items()}
        repeat_metrics = []
        for repeat in (1, 2, 3):
            raw, contract = cells[(repeat, "D0-native-apc")], cells[(repeat, "D2-template-contractkv")]
            repeat_metrics.append({
                "mean_reduction": 1 - statistics.mean(number(row["ttft_ms"]) for row in contract) / statistics.mean(number(row["ttft_ms"]) for row in raw),
                "p99_reduction": 1 - percentile([number(row["ttft_ms"]) for row in contract], .99) / percentile([number(row["ttft_ms"]) for row in raw], .99),
                "prefill_reduction": 1 - statistics.mean(number(row["new_prefill_tokens"]) for row in contract) / statistics.mean(number(row["new_prefill_tokens"]) for row in raw),
            })
        draws: dict[int, list[tuple[float, float, float, float]]] = {
            slo: [] for slo in (500, 1000, 1500, 3000)
        }
        for _ in range(iterations):
            chosen_repeats = [rng.choice((1, 2, 3)) for _ in range(3)]
            raw_means = []; contract_means = []; raw_prefill = []; contract_prefill = []
            goodputs = {slo: [[], []] for slo in draws}
            for repeat in chosen_repeats:
                sampled = {}
                for policy in ("D0-native-apc", "D2-template-contractkv"):
                    sampled[policy] = sample_cell(indexed_cells[(repeat, policy)], rng)
                raw_means.append(statistics.mean(number(row["ttft_ms"]) for row in sampled["D0-native-apc"]))
                contract_means.append(statistics.mean(number(row["ttft_ms"]) for row in sampled["D2-template-contractkv"]))
                raw_prefill.append(statistics.mean(number(row["new_prefill_tokens"]) for row in sampled["D0-native-apc"]))
                contract_prefill.append(statistics.mean(number(row["new_prefill_tokens"]) for row in sampled["D2-template-contractkv"]))
                for pidx, policy in enumerate(("D0-native-apc", "D2-template-contractkv")):
                    wall = int(summaries[(repeat, policy)]["completed_requests"]) / max(number(summaries[(repeat, policy)]["achieved_throughput_rps"]), 1e-9)
                    for slo in draws:
                        compliant = sum(number(row["ttft_ms"]) <= slo for row in sampled[policy])
                        goodputs[slo][pidx].append(compliant / max(wall, 1e-9))
            mean_reduction = 1 - statistics.mean(contract_means) / statistics.mean(raw_means)
            prefill_reduction = 1 - statistics.mean(contract_prefill) / statistics.mean(raw_prefill)
            for slo in draws:
                raw_goodput = statistics.mean(goodputs[slo][0])
                contract_goodput = statistics.mean(goodputs[slo][1])
                draws[slo].append((mean_reduction, prefill_reduction, raw_goodput, contract_goodput))
        for slo, values in draws.items():
            raw_points = []; contract_points = []
            for repeat in (1, 2, 3):
                for target, policy in ((raw_points, "D0-native-apc"),
                                       (contract_points, "D2-template-contractkv")):
                    full_rows = cells[(repeat, policy)]
                    summary = summaries[(repeat, policy)]
                    wall = int(summary["completed_requests"]) / max(number(summary["achieved_throughput_rps"]), 1e-9)
                    target.append(sum(number(row["ttft_ms"]) <= slo for row in full_rows) / max(wall, 1e-9))
            raw_point = statistics.mean(raw_points)
            contract_point = statistics.mean(contract_points)
            raw_draws = [value[2] for value in values]
            contract_draws = [value[3] for value in values]
            delta_draws = [value[3] - value[2] for value in values]
            ratio_identifiable = percentile(raw_draws, .025) > 0
            ratio_draws = [contract / raw for _, _, raw, contract in values if raw > 0]
            output.append({
                "model": model, "tenants_per_template": 25, "load_fraction": .8, "slo_ttft_ms": slo,
                "fresh_process_repeats": 3, "cluster_bootstrap_iterations": iterations,
                "mean_ttft_reduction": statistics.mean(row["mean_reduction"] for row in repeat_metrics),
                "mean_ttft_reduction_ci_low": percentile([value[0] for value in values], .025),
                "mean_ttft_reduction_ci_high": percentile([value[0] for value in values], .975),
                "p99_ttft_reduction_repeat_min": min(row["p99_reduction"] for row in repeat_metrics),
                "p99_ttft_reduction_repeat_max": max(row["p99_reduction"] for row in repeat_metrics),
                "new_prefill_reduction": statistics.mean(row["prefill_reduction"] for row in repeat_metrics),
                "new_prefill_reduction_repeat_min": min(row["prefill_reduction"] for row in repeat_metrics),
                "new_prefill_reduction_repeat_max": max(row["prefill_reduction"] for row in repeat_metrics),
                "raw_slo_goodput_rps": raw_point, "contract_slo_goodput_rps": contract_point,
                "slo_goodput_delta_rps": contract_point - raw_point,
                "slo_goodput_delta_ci_low": percentile(delta_draws, .025),
                "slo_goodput_delta_ci_high": percentile(delta_draws, .975),
                "slo_goodput_multiplier": contract_point / max(raw_point, 1e-9),
                "slo_goodput_multiplier_ci_low": percentile(ratio_draws, .025) if ratio_identifiable else "",
                "slo_goodput_multiplier_ci_high": percentile(ratio_draws, .975) if ratio_identifiable else "",
                "slo_goodput_multiplier_ci_identifiable": ratio_identifiable,
                "resampling_units": "fresh_process/service_template/tenant_session",
            })
    return output


def load_curves(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = root / "service_locality_policy_comparison_v0.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row.get("policy") == "D2-template-contractkv"
                and int(number(row.get("tenants_per_template"))) == 25]
    return ([row for row in selected if number(row.get("load_fraction")) <= 1.4],
            [row for row in selected if number(row.get("load_fraction")) > 1.4])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("results/tsc_service"))
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    args = parser.parse_args(); root = args.root
    pairs, quality, quality_gate = quality_summary(root, args.bootstrap_iterations)
    granularity, granularity_gate = granularity_summary(root)
    ci = headline_ci(root, args.bootstrap_iterations)
    headline_curve, overload_curve = load_curves(root)
    write_csv(root / "service_template_quality_pairs_v0.csv", pairs)
    write_csv(root / "service_template_quality_summary_v0.csv", quality)
    (root / "service_template_quality_gate_v0.json").write_text(json.dumps(quality_gate, indent=2) + "\n", encoding="utf-8")
    write_csv(root / "certificate_granularity_ablation_v0.csv", granularity)
    (root / "certificate_granularity_ablation_gate_v0.json").write_text(json.dumps(granularity_gate, indent=2) + "\n", encoding="utf-8")
    write_csv(root / "service_locality_confidence_intervals_v0.csv", ci)
    write_csv(root / "service_locality_headline_load_curve_v0.csv", headline_curve)
    write_csv(root / "service_locality_overload_appendix_v0.csv", overload_curve)
    gate = {
        "service_template_quality_gate": quality_gate["gate_pass"],
        "certificate_granularity_gate": granularity_gate["gate_pass"],
        "headline_ci_rows": len(ci), "headline_load_curve_rows": len(headline_curve),
        "overload_rows_appendix_only": len(overload_curve),
    }
    gate["gate_pass"] = gate["service_template_quality_gate"] and gate["certificate_granularity_gate"] and len(ci) == 8
    (root / "tsc_submission_closure_gate_v0.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2))
    return 0 if gate["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
