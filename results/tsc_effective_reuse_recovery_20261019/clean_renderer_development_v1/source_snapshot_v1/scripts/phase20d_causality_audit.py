#!/usr/bin/env python3
"""Read-only audit of held-out quality failures across fresh policy processes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def index(rows: list[dict]) -> dict[tuple[str, int], dict]:
    return {(str(row.get("session_id")), int(row.get("turn_id", 0) or 0)): row
            for row in rows if row.get("row_type") == "future"}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,required=True);parser.add_argument("--tier1",type=Path,required=True)
    parser.add_argument("--two-tier",type=Path,required=True);parser.add_argument("--quality",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--summary-output",type=Path,required=True)
    args=parser.parse_args();raw_rows=load(args.raw);tier1_rows=load(args.tier1);two_rows=load(args.two_tier)
    raw=index(raw_rows);tier1=index(tier1_rows);two=index(two_rows)
    certified={str(row.get("session_id")) for row in two_rows if row.get("row_type")=="canary" and row.get("certificate_issued") is True}
    with args.quality.open(encoding="utf-8",newline="") as handle:
        quality={(row["policy"],row["session_id"],int(row["turn_id"])):row for row in csv.DictReader(handle)}
    rows=[]
    for key,raw_row in sorted(raw.items()):
        sid,turn=key
        if sid not in certified or key not in tier1 or key not in two:continue
        r=str(raw_row.get("output_text","") or "");a=str(tier1[key].get("output_text","") or "");b=str(two[key].get("output_text","") or "")
        qa=quality.get(("tier1-only",sid,turn),{});qb=quality.get(("contractkv-two-tier",sid,turn),{})
        va=str(qa.get("quality_violation","")).lower()=="true";vb=str(qb.get("quality_violation","")).lower()=="true"
        if va and vb and a==b:cause="reproducible_future_turn_layout_sensitivity"
        elif va and vb:cause="cross_process_variation_with_consistent_quality_loss"
        elif va or vb:cause="cross_process_variation_or_score_boundary"
        else:cause="no_quality_violation"
        rows.append({"session_id":sid,"turn_id":turn,"dataset":raw_row.get("dataset"),"task":raw_row.get("task"),
          "raw_hash":digest(r),"tier1_hash":digest(a),"two_tier_hash":digest(b),"tier1_two_tier_exact":a==b,
          "raw_tier1_exact":r==a,"raw_two_tier_exact":r==b,"tier1_quality_drop":qa.get("quality_drop_vs_raw",0),
          "two_tier_quality_drop":qb.get("quality_drop_vs_raw",0),"tier1_violation":va,"two_tier_violation":vb,"cause":cause})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    affected=sorted({row["session_id"] for row in rows if row["tier1_violation"] or row["two_tier_violation"]})
    causes={name:sum(row["cause"]==name for row in rows) for name in sorted({row["cause"] for row in rows})}
    summary={"certified_sessions":len(certified),"audited_future_rows":len(rows),"affected_sessions":affected,
      "affected_session_count":len(affected),"cause_rows":causes,
      "tier1_two_tier_certificate_set_equal":certified=={str(row.get("session_id")) for row in tier1_rows if row.get("row_type")=="canary" and row.get("certificate_issued") is True},
      "conclusion":"Turn-0 attestation is not a proof of future-turn quality under changed dynamic observations.",
      "claim_boundary":"Read-only audit of frozen held-out outputs; no regeneration or policy retuning."}
    args.summary_output.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8");print(json.dumps(summary,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
