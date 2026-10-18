#!/usr/bin/env python3
"""Join Phase 19B cells and freeze task quality plus net serving benefit."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.phase12_prefix_cache_ab import percentile
from scripts.phase15d_task_bearing_certified_replay import output_contract


FIELDS = [
    "policy", "load_tier", "concurrency", "future_requests", "completion_rate",
    "certificate_issue_rate", "quality_violation_rate", "output_contract_mismatch_rate", "mean_quality_drop",
    "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "mean_latency_ms",
    "mean_prefix_hit_tokens", "mean_new_prefill_tokens", "mean_prefix_hit_fraction",
    "certified_prefix_hit_fraction", "max_dynamic_suffix_reuse_tokens",
    "slo_compliant_req_per_sec", "unhidden_verifier_ms_per_future_request",
    "net_mean_ttft_ms", "net_ttft_reduction_vs_raw", "new_prefill_reduction_vs_raw",
    "retained_prefix_gain_rate", "slo_goodput_gain_vs_raw", "claim_boundary",
]


def truth(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def f(value: object) -> float:
    try: return float(value)
    except (TypeError, ValueError): return 0.0


def load(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return rows


def normalize_prefill(row: dict[str, Any]) -> None:
    if row.get("prompt_tokens", "") == "" or row.get("prefix_hit_tokens", "") == "":
        return
    previous = row.get("new_prefill_tokens", "")
    if row.get("scheduler_initial_prefill_tokens", "") == "":
        row["scheduler_initial_prefill_tokens"] = previous
    row["new_prefill_tokens"] = max(0.0, f(row["prompt_tokens"]) - f(row["prefix_hit_tokens"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--slo-ms", type=float, default=1000)
    parser.add_argument("--expected-full-cells", type=int, default=3)
    parser.add_argument("--min-certificate-coverage", type=float, default=.50)
    parser.add_argument("--min-safe-coverage", type=float, default=.50)
    parser.add_argument("--min-certified-prefix-hit-fraction", type=float, default=.95)
    parser.add_argument("--min-net-ttft-reduction", type=float, default=.30)
    parser.add_argument("--min-new-prefill-reduction", type=float, default=.40)
    parser.add_argument("--min-retained-prefix-gain", type=float, default=0.0)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args(); rows = load(args.inputs)
    for row in rows:
        normalize_prefill(row)
    raw_index = {(row["load_tier"], row["session_id"], int(row["turn_id"])): row
                 for row in rows if row["row_type"] == "future" and row["policy"] == "raw-order"}
    for row in rows:
        row["quality_contract_match"] = ""
        row["quality_drop_vs_raw"] = ""
        if row["row_type"] != "future" or not truth(row.get("success")): continue
        baseline = raw_index.get((row["load_tier"], row["session_id"], int(row["turn_id"])))
        if baseline is None or not truth(baseline.get("success")): continue
        match, contract = output_contract(str(row["dataset"]), str(row["task"]),
                                          str(baseline.get("output_text", "")), str(row.get("output_text", "")), "")
        row["quality_contract_match"] = match; row["quality_contract_type"] = contract
        row["quality_drop_vs_raw"] = max(0.0, f(baseline.get("task_score"))-f(row.get("task_score")))
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[(str(row["policy"]), str(row["load_tier"]))].append(row)
    prelim = {}
    for key, group in groups.items():
        future = [row for row in group if row["row_type"] == "future"]
        success = [row for row in future if truth(row.get("success"))]
        canaries = [row for row in group if row["row_type"] == "canary"]
        batch_wall = {}
        for row in future: batch_wall[str(row.get("batch_id"))] = f(row.get("batch_wall_ms"))
        wall_s = sum(batch_wall.values())/1000.0
        prefix = [f(row["prefix_hit_tokens"]) for row in success if row.get("prefix_hit_tokens", "") != ""]
        prompts = [f(row["prompt_tokens"]) for row in success if row.get("prompt_tokens", "") != ""]
        prefill = [f(row["new_prefill_tokens"]) for row in success if row.get("new_prefill_tokens", "") != ""]
        quality = [row for row in success if row.get("quality_contract_match", "") != ""]
        ttft = [f(row["ttft_ms"]) for row in success]
        certified = [row for row in success if truth(row.get("certificate_issued"))]
        certified_stable = [f(row["certified_stable_prefix_tokens"]) for row in certified
                            if row.get("certified_stable_prefix_tokens", "") != ""]
        certified_prefix = [min(f(row["prefix_hit_tokens"]), f(row["certified_stable_prefix_tokens"]))
                            for row in certified if row.get("prefix_hit_tokens", "") != ""
                            and row.get("certified_stable_prefix_tokens", "") != ""]
        dynamic_suffix = [f(row["dynamic_suffix_reuse_tokens"]) for row in certified
                          if row.get("dynamic_suffix_reuse_tokens", "") != ""]
        unhidden = sum(f(row.get("unhidden_verifier_ms")) for row in canaries)
        prelim[key] = {
            "policy": key[0], "load_tier": key[1], "concurrency": int(group[0]["concurrency"]),
            "future_requests": len(future), "completion_rate": len(success)/max(1,len(future)),
            "certificate_issue_rate": sum(truth(row.get("certificate_issued")) for row in canaries)/max(1,len(canaries)) if canaries else "",
            "quality_violation_rate": sum(f(row["quality_drop_vs_raw"]) > .03 for row in quality)/max(1,len(quality)),
            "output_contract_mismatch_rate": sum(not truth(row["quality_contract_match"]) for row in quality)/max(1,len(quality)),
            "mean_quality_drop": statistics.mean(f(row["quality_drop_vs_raw"]) for row in quality) if quality else 0,
            "mean_ttft_ms": statistics.mean(ttft) if ttft else 0, "p95_ttft_ms": percentile(ttft,.95),
            "mean_tpot_ms": statistics.mean(f(row["tpot_ms"]) for row in success) if success else 0,
            "mean_latency_ms": statistics.mean(f(row["latency_ms"]) for row in success) if success else 0,
            "mean_prefix_hit_tokens": statistics.mean(prefix) if prefix else 0,
            "mean_new_prefill_tokens": statistics.mean(prefill) if prefill else 0,
            "mean_prefix_hit_fraction": (sum(prefix)/max(1.0,sum(prompts))) if prefix and prompts else 0,
            "certified_prefix_hit_fraction": (sum(certified_prefix)/max(1.0,sum(certified_stable)))
                                             if certified_prefix and certified_stable else 0,
            "max_dynamic_suffix_reuse_tokens": max(dynamic_suffix, default=0),
            "slo_compliant_req_per_sec": sum(f(row["ttft_ms"])<=args.slo_ms for row in success)/max(.001,wall_s),
            "unhidden_verifier_ms_per_future_request": unhidden/max(1,len(future)),
        }
    summaries=[]
    for key, item in sorted(prelim.items()):
        policy_turns = {int(row["turn_id"]) for row in groups[key]
                        if row["row_type"] == "future"}
        raw_rows = [row for row in groups.get(("raw-order", key[1]), [])
                    if row["row_type"] == "future" and int(row["turn_id"]) in policy_turns
                    and truth(row.get("success"))]
        raw_batches = {str(row.get("batch_id")): f(row.get("batch_wall_ms")) for row in raw_rows}
        raw_mean_ttft = statistics.mean(f(row["ttft_ms"]) for row in raw_rows) if raw_rows else item["mean_ttft_ms"]
        raw_mean_prefill = statistics.mean(f(row["new_prefill_tokens"]) for row in raw_rows if row.get("new_prefill_tokens", "") != "") if raw_rows else item["mean_new_prefill_tokens"]
        raw_goodput = sum(f(row["ttft_ms"]) <= args.slo_ms for row in raw_rows) / max(.001, sum(raw_batches.values()) / 1000.0)
        physical_prefill = f(prelim.get(("physical-cache-aware", key[1]), {}).get("mean_new_prefill_tokens", raw_mean_prefill))
        available_prefix_gain = max(0.0, raw_mean_prefill - physical_prefill)
        retained_prefix_gain = max(0.0, raw_mean_prefill - item["mean_new_prefill_tokens"])
        net=item["mean_ttft_ms"]+item["unhidden_verifier_ms_per_future_request"]
        item.update({"net_mean_ttft_ms":net,
                     "net_ttft_reduction_vs_raw":1-net/max(.001,raw_mean_ttft),
                     "new_prefill_reduction_vs_raw":1-item["mean_new_prefill_tokens"]/max(.001,raw_mean_prefill),
                     "retained_prefix_gain_rate":retained_prefix_gain/max(.001,available_prefix_gain),
                     "slo_goodput_gain_vs_raw":item["slo_compliant_req_per_sec"]/max(.001,raw_goodput)-1,
                     "claim_boundary":"Fresh isolated vLLM task-bearing future turns with scheduler-observed prefix metrics; task-sanity scoring, not official benchmark scoring."})
        summaries.append(item)
    with args.summary_output.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader();writer.writerows({k:r.get(k,"") for k in FIELDS} for r in summaries)
    full=[row for row in summaries if row["policy"]=="contractkv-full"]
    quality_by_load = {}
    for load_tier in {str(row["load_tier"]) for row in rows}:
        raw_scores = {(str(row["session_id"]), int(row["turn_id"])): f(row.get("task_score"))
                      for row in rows if row["row_type"] == "future" and row["policy"] == "raw-order"
                      and row["load_tier"] == load_tier and truth(row.get("success"))}
        candidate_scores = {(str(row["session_id"]), int(row["turn_id"])): f(row.get("task_score"))
                            for row in rows if row["row_type"] == "future"
                            and row["policy"] == "physical-cache-aware" and row["load_tier"] == load_tier
                            and truth(row.get("success"))}
        session_drops: dict[str, list[float]] = defaultdict(list)
        for key, raw_score in raw_scores.items():
            if key in candidate_scores:
                session_drops[key[0]].append(max(0.0, raw_score - candidate_scores[key]))
        certified_sessions = {str(row["session_id"]) for row in rows
                              if row["row_type"] == "future" and row["policy"] == "contractkv-full"
                              and row["load_tier"] == load_tier and truth(row.get("certificate_issued"))}
        safe_sessions = {sid for sid, drops in session_drops.items() if not any(value > .03 for value in drops)}
        unsafe_sessions = set(session_drops) - safe_sessions
        quality_by_load[load_tier] = {
            "safe_coverage": len(safe_sessions & certified_sessions) / max(1, len(safe_sessions)),
            "unsafe_certified": len(unsafe_sessions & certified_sessions),
        }
    grouped_rows = {key: value for key, value in groups.items()}
    measured_turn_sets = {
        key: {int(row["turn_id"]) for row in group if row["row_type"] == "future"}
        for key, group in grouped_rows.items()
    }
    future_counts_by_load: dict[str, set[int]] = defaultdict(set)
    for (policy, load_tier), group in grouped_rows.items():
        future_counts_by_load[load_tier].add(sum(row["row_type"] == "future" for row in group))
    initialization_complete = all(
        sum(row["row_type"] in {"warmup", "canary"} for row in group)
        == len({str(row["session_id"]) for row in group})
        for group in grouped_rows.values()
    )
    gate={"rows":len(rows),"full_cells":len(full),
          "future_request_count_aligned":all(len(counts)==1 for counts in future_counts_by_load.values()),
          "measured_turns_aligned":bool(measured_turn_sets) and len({tuple(sorted(value)) for value in measured_turn_sets.values()})==1
                                   and all(0 not in value for value in measured_turn_sets.values()),
          "unmeasured_turn0_complete":initialization_complete,
          "unsafe_certified_zero":all(value["unsafe_certified"] == 0 for value in quality_by_load.values()),
          "safe_coverage_ge_threshold":all(value["safe_coverage"] >= args.min_safe_coverage for value in quality_by_load.values()),
          "quality_violation_zero":all(row["quality_violation_rate"]==0 for row in full),
          "certificate_coverage_ge_threshold":all(f(row["certificate_issue_rate"])>=args.min_certificate_coverage for row in full),
          "certified_stable_prefix_reuse_ge_threshold":all(row["certified_prefix_hit_fraction"]>=args.min_certified_prefix_hit_fraction for row in full),
          "dynamic_suffix_reuse_zero":all(row["max_dynamic_suffix_reuse_tokens"] == 0 for row in full),
          "net_warm_ttft_reduction_ge_threshold":all(row["net_ttft_reduction_vs_raw"]>=args.min_net_ttft_reduction for row in full),
          "new_prefill_reduction_ge_threshold":all(row["new_prefill_reduction_vs_raw"]>=args.min_new_prefill_reduction for row in full),
          "retained_prefix_gain_ge_threshold":all(row["retained_prefix_gain_rate"]>=args.min_retained_prefix_gain for row in full)}
    gate["gate_pass"]=len(full)==args.expected_full_cells and all(value for key,value in gate.items() if key not in {"rows","full_cells","gate_pass"})
    args.gate_output.write_text(json.dumps(gate,indent=2)+"\n",encoding="utf-8"); print(json.dumps(gate,indent=2))
    return 0 if gate["gate_pass"] else 2


if __name__=="__main__": raise SystemExit(main())
