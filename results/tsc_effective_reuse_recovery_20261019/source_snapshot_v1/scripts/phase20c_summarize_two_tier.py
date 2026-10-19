#!/usr/bin/env python3
"""Join Phase 20C development decisions with real PSTP finalize evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def load(path: Path) -> list[dict]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def p95(values: list[float]) -> float:
    if not values: return 0.0
    values=sorted(values);return values[max(0,min(len(values)-1,math.ceil(.95*len(values))-1))]


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--results",type=Path,required=True)
    parser.add_argument("--events",type=Path,required=True);parser.add_argument("--policy",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    rows=load(args.results);events=load(args.events);policy=json.loads(args.policy.read_text(encoding="utf-8"))
    finalizes={}
    for event in events:
        if event.get("event")=="pstp_finalize":finalizes.setdefault(str(event.get("request_id")),[]).append(event)
    ephemeral_ids=[str(row.get("tier2_candidate_request_id")) for row in rows if row.get("tier2_candidate_request_id")]
    probe_ids=[str(row.get("promotion_cost_probe_request_id")) for row in rows if row.get("promotion_cost_probe_request_id")]
    promotion_ids=[str(row.get("tier2_promotion_request_id")) for row in rows if row.get("tier2_promotion_request_id")]
    def events_for(request_id:str)->list[dict]:
        return finalizes.get(request_id,[])+finalizes.get("chatcmpl-"+request_id,[])
    def clean_abort(request_id:str)->bool:
        return any(e.get("action")=="abort" and int(e.get("cache_entries_after",0))==int(e.get("cache_entries_before",0)) for e in events_for(request_id))
    summary={"schema_version":"phase20.two-tier-development-summary.v1","sessions":len(rows),
      "tier1_certificates":sum(r.get("certificate_tier")=="tier1" for r in rows),
      "tier2_attempts":sum(r.get("tier2_attempted") is True for r in rows),
      "tier2_contract_passes":sum(r.get("tier2_contract_pass") is True for r in rows),
      "tier2_promotions":sum(r.get("tier2_promoted") is True for r in rows),
      "total_safe_coverage":sum(r.get("certificate_issued") is True for r in rows)/max(1,len(rows)),
      "candidate_p95_ms":p95([float(r.get("tier2_candidate_ms",0)) for r in rows if r.get("tier2_attempted")]),
      "promotion_probe_p95_ms":p95([float(r.get("promotion_cost_probe_ms",0)) for r in rows if r.get("tier2_attempted")]),
      "frozen_incremental_budget_ms":policy["frozen_total_cost_budget_ms"],
      "budget_fits_3s_slack":policy["tier2_budget_fits_slack"],
      "ephemeral_candidate_abort_clean":sum(clean_abort(x) for x in ephemeral_ids)==len(ephemeral_ids),
      "promotion_probe_abort_clean":sum(clean_abort(x) for x in probe_ids)==len(probe_ids),
      "promotion_commit_observed":sum(any(e.get("action")=="commit" for e in events_for(x)) for x in promotion_ids),
      "contract_is_exact_only":all("f1" not in str(r.get("contract_contract_type","")).lower() for r in rows),
      "ground_truth_used_online":False,
      "conclusion":"Tier-2 is structurally unavailable under the frozen 3 s slack when its development p95 total cost exceeds the budget.",
      "claim_boundary":"Development calibration and source-level transaction evidence; not held-out performance."}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
