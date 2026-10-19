#!/usr/bin/env python3
"""Summarize sealed Phase 20 held-out live replay and apply frozen gates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(values: list[float], q: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); return ordered[max(0, min(len(ordered)-1, math.ceil(q*len(ordered))-1))]


def mean(rows: list[dict], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) not in {"", None}]
    return statistics.fmean(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", action="append", required=True, help="policy=path")
    parser.add_argument("--sessions", type=Path, required=True); parser.add_argument("--tool-slack-ms", type=float, default=3000)
    parser.add_argument("--summary-output", type=Path, required=True); parser.add_argument("--quality-output", type=Path, required=True)
    parser.add_argument("--slo-output", type=Path, required=True); parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args(); sessions = {str(x["phase20_session_id"]): x for x in load(args.sessions)}
    cells = {item.split("=",1)[0]: load(Path(item.split("=",1)[1])) for item in args.cell}
    quality_rows = []
    raw_scores: dict[tuple[str,int], float] = {}
    for policy, rows in cells.items():
        for row in rows:
            if row.get("row_type") not in {"future", "canary"}: continue
            sid = str(row.get("session_id")); sample = sessions.get(sid, {})
            output = str(row.get("output_text", row.get("raw_output", "")) or "")
            score, metric, error = standard_score(str(sample.get("dataset", row.get("dataset", ""))),
                                                  str(sample.get("task", row.get("task", ""))),
                                                  output, sample.get("answer", ""))
            turn = int(row.get("turn_id", 0) or 0); key = (sid, turn)
            quality_rows.append({"policy": policy, "session_id": sid, "turn_id": turn,
                                 "dataset": sample.get("dataset", row.get("dataset")), "task": sample.get("task", row.get("task")),
                                 "sample_id": sample.get("sample_id", row.get("sample_id")), "metric": metric,
                                 "score": score, "scoring_error": error})
            if policy == "raw-order": raw_scores[key] = score
    for row in quality_rows:
        raw = raw_scores.get((row["session_id"], row["turn_id"]), row["score"])
        row["raw_score"] = raw; row["quality_drop_vs_raw"] = max(0.0, raw - row["score"])
        row["quality_violation"] = row["quality_drop_vs_raw"] > .03

    summaries = []
    for policy, rows in cells.items():
        future = [row for row in rows if row.get("row_type") == "future"]
        canary = [row for row in rows if row.get("row_type") == "canary"]
        successful = [row for row in future if row.get("success") is True]
        quality = [row for row in quality_rows if row["policy"] == policy]
        ttft = [float(row.get("ttft_ms",0)) for row in successful]
        prefix = [float(row["prefix_hit_tokens"]) for row in successful if row.get("prefix_hit_tokens") not in {"",None}]
        new_prefill = [float(row["new_prefill_tokens"]) for row in successful if row.get("new_prefill_tokens") not in {"",None}]
        summaries.append({"policy": policy, "requests": len(future), "completed_requests": len(successful),
            "completion_rate": len(successful)/max(1,len(future)), "capacity_failures": len(future)-len(successful),
            "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0, "p95_ttft_ms": pct(ttft,.95),
            "mean_tpot_ms": mean(successful,"tpot_ms"), "p95_tpot_ms": pct([float(x.get("tpot_ms",0)) for x in successful],.95),
            "mean_latency_ms": mean(successful,"latency_ms"), "mean_prefix_hit_tokens": statistics.fmean(prefix) if prefix else 0,
            "mean_new_prefill_tokens": statistics.fmean(new_prefill) if new_prefill else 0,
            "safe_coverage": sum(x.get("certificate_issued") is True for x in canary)/max(1,len(canary)) if canary else 0,
            "tier1_coverage": sum(x.get("certificate_tier")=="tier1" for x in canary)/max(1,len(canary)) if canary else 0,
            "tier2_incremental_coverage": sum(x.get("certificate_tier")=="tier2" for x in canary)/max(1,len(canary)) if canary else 0,
            "quality_violation_rate": sum(x["quality_violation"] for x in quality)/max(1,len(quality)),
            "max_quality_drop": max([x["quality_drop_vs_raw"] for x in quality],default=0),
            "unsafe_certified": sum(x.get("certificate_issued") is True and any(q["quality_violation"] for q in quality if q["session_id"]==str(x.get("session_id"))) for x in canary)})
    by_policy = {row["policy"]: row for row in summaries}; raw = by_policy["raw-order"]; two = by_policy["contractkv-two-tier"]
    raw_prefix=max(raw["mean_prefix_hit_tokens"],1); raw_prefill=max(raw["mean_new_prefill_tokens"],1)
    two["retained_prefix_gain_vs_raw"]=(two["mean_prefix_hit_tokens"]-raw["mean_prefix_hit_tokens"])/raw_prefix
    two["new_prefill_reduction_vs_raw"]=(raw["mean_new_prefill_tokens"]-two["mean_new_prefill_tokens"])/raw_prefill
    two["net_ttft_reduction_vs_raw"]=(raw["mean_ttft_ms"]-two["mean_ttft_ms"])/max(raw["mean_ttft_ms"],1)
    two_rows=cells["contractkv-two-tier"]; canary=[x for x in two_rows if x.get("row_type")=="canary"]
    overruns=[max(0.0,float(x.get("tier2_total_ms",0))-args.tool_slack_ms)/max(args.tool_slack_ms,1) for x in canary if x.get("tier2_attempted")]
    two["tier2_p95_slack_overrun_fraction"]=pct(overruns,.95)
    cert_future=[x for x in two_rows if x.get("row_type")=="future" and x.get("certificate_issued") is True and x.get("prefix_hit_tokens") not in {"",None}]
    two["certified_prefix_reuse_fraction"]=statistics.fmean(min(1.0,float(x.get("prefix_hit_tokens",0))/max(1,float(x.get("stable_prefix_tokens",0)))) for x in cert_future) if cert_future else 0
    two["max_dynamic_suffix_reuse_tokens"]=max([int(x.get("dynamic_suffix_reuse_tokens",0) or 0) for x in cert_future],default=0)
    tier1_reference=by_policy.get("tier1-only",raw)
    # Isolate incremental Tier-2 interference from the identical Tier-1
    # lifecycle.  The physical upper bound intentionally changes coverage and
    # is not a valid foreground-overhead control.
    two["foreground_p95_extra_interference_ms"]=two["p95_ttft_ms"]-tier1_reference["p95_ttft_ms"]
    attempted_count=sum(x.get("tier2_attempted") is True for x in canary)
    promoted_count=sum(x.get("tier2_promoted") is True for x in canary)
    two["tier2_invocation_rate"]=attempted_count/max(1,len(canary))
    two["tier2_budget_admission_rate"]=sum(x.get("tier2_admitted") is True for x in canary)/max(1,len(canary))
    two["tier2_contract_pass_rate"]=sum(x.get("tier2_contract_pass") is True for x in canary)/max(1,attempted_count)
    two["promotion_success_rate"]=promoted_count/max(1,sum(x.get("tier2_contract_pass") is True for x in canary))
    two["ephemeral_abort_clean_rate"]=(sum(x.get("ephemeral_abort_clean") is True for x in canary if x.get("tier2_attempted"))/attempted_count if attempted_count else 1.0)
    two["tier2_attempted_count"]=attempted_count
    two["tier2_promoted_count"]=promoted_count
    two["promotion_commit_observed_rate"]=(
        sum(x.get("promotion_commit_observed") is True for x in canary
            if x.get("tier2_promoted"))/promoted_count
        if promoted_count else None)

    slo_rows=[]
    for policy, rows in cells.items():
        future=[x for x in rows if x.get("row_type")=="future" and x.get("success") is True]
        batches={}
        for row in future:
            key=str(row.get("batch_id") or row.get("request_id"))
            batches[key]=max(batches.get(key,0.0),float(row.get("batch_wall_ms",0) or 0))
        wall_s=sum(batches.values())/1000.0
        for slo in (500,750,1000,1250,1500,2000):
            compliant=sum(float(x.get("ttft_ms",1e18))<=slo for x in future)
            slo_rows.append({"policy":policy,"slo_ms":slo,"completed":len(future),"slo_compliant":compliant,
                             "slo_compliant_fraction":compliant/max(1,len(future)),"slo_compliant_req_per_sec":compliant/max(wall_s,1e-9)})

    gates={"completion_100":two["completion_rate"]==1.0,"unsafe_certified_zero":two["unsafe_certified"]==0,
      "quality_violation_zero":two["quality_violation_rate"]==0,"safe_coverage_ge_50pct":two["safe_coverage"]>=.50,
      "retained_prefix_gain_ge_50pct":two["retained_prefix_gain_vs_raw"]>=.50,
      "new_prefill_reduction_ge_30pct":two["new_prefill_reduction_vs_raw"]>=.30,
      "net_ttft_reduction_ge_30pct":two["net_ttft_reduction_vs_raw"]>=.30,
      "certified_prefix_reuse_ge_95pct":two["certified_prefix_reuse_fraction"]>=.95,
      "dynamic_suffix_reuse_zero":two["max_dynamic_suffix_reuse_tokens"]==0,
      "tier2_p95_slack_overrun_le_1pct":two["tier2_p95_slack_overrun_fraction"]<=.01,
      "foreground_p95_extra_interference_le_10ms":two["foreground_p95_extra_interference_ms"]<=10,
      "ephemeral_abort_clean":two["ephemeral_abort_clean_rate"]==1.0,
      "promotion_commit_observed":promoted_count>0 and two["promotion_commit_observed_rate"]==1.0}
    gate={"schema_version":"phase20.heldout-gate.v1","gates":gates,"gate_pass":all(gates.values()),
          "stop_experiments_after_phase20":True,"claim_boundary":"One-shot sealed Llama held-out result; no retuning or third-model rescue."}
    for path,rows in ((args.summary_output,summaries),(args.quality_output,quality_rows),(args.slo_output,slo_rows)):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=sorted({key for row in rows for key in row}));writer.writeheader();writer.writerows(rows)
    args.gate_output.write_text(json.dumps(gate,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"two_tier":two,"gate":gate},indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
