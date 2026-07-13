#!/usr/bin/env python3
"""Freeze non-Qwen sessions and a model-specific ContractKV policy manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "": sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.contractkv_frozen_policy import GREEDY_CONFIG, digest, runtime_identity


def load_jsonl(path: Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def key(row:dict[str,Any])->str: return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--full-pool",type=Path,required=True);p.add_argument("--phase19b-sessions",type=Path,required=True)
    p.add_argument("--model-id",required=True);p.add_argument("--model-path",type=Path,required=True);p.add_argument("--vllm-version",default="0.10.2")
    p.add_argument("--calibration-per-task",type=int,default=2);p.add_argument("--heldout-per-task",type=int,default=4)
    p.add_argument("--calibration-output",type=Path,required=True);p.add_argument("--heldout-output",type=Path,required=True);p.add_argument("--policy-output",type=Path,required=True);a=p.parse_args()
    used={key(x) for x in load_jsonl(a.phase19b_sessions)}
    tasks=[("ruler",lambda x:x.get("dataset")=="RULER"),("hotpotqa",lambda x:x.get("task")=="hotpotqa"),("narrativeqa",lambda x:x.get("task")=="narrativeqa"),("qasper",lambda x:x.get("task")=="qasper"),("repobench",lambda x:x.get("dataset")=="RepoBench")]
    calibration=[];heldout=[];pool=load_jsonl(a.full_pool)
    for name,pred in tasks:
        candidates=[x for x in pool if pred(x) and x.get("metadata",{}).get("phase14_partition")=="live_serving" and key(x) not in used]
        candidates.sort(key=lambda x:hashlib.sha256(f"phase19c:{name}:{x.get('metadata',{}).get('source_group_id')}:{x.get('sample_id')}".encode()).hexdigest())
        unique=[];groups=set()
        for x in candidates:
            group=str(x.get("metadata",{}).get("source_group_id",""))
            if not group or group in groups:continue
            groups.add(group); unique.append({**x,"phase19b_session_id":f"phase19c-{name}-{x.get('sample_id')}"})
            if len(unique)==a.calibration_per_task+a.heldout_per_task:break
        if len(unique)<a.calibration_per_task+a.heldout_per_task:raise RuntimeError(f"insufficient {name}")
        calibration.extend({**x,"phase19c_partition":"calibration"} for x in unique[:a.calibration_per_task])
        heldout.extend({**x,"phase19c_partition":"held_out"} for x in unique[a.calibration_per_task:])
    for path,rows in ((a.calibration_output,calibration),(a.heldout_output,heldout)):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8")
    identity=runtime_identity(a.model_id,a.model_path,a.vllm_version)
    manifest={"schema_version":"phase19c.model-policy.v1",**asdict(identity),"attestation_mode":"same-backend-teacher-forced-strict-top1",
              "tau_raw":-1e9,"tau_abs":-1e9,"tau_drop":1e9,"quality_epsilon":.03,
              "calibration_split_hash":digest(sorted(key(x) for x in calibration)),"heldout_split_hash":digest(sorted(key(x) for x in heldout)),
              "decode_config":GREEDY_CONFIG,"thresholds_retuned_from_heldout":False}
    manifest["policy_hash"]=digest(manifest);a.policy_output.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"calibration":len(calibration),"heldout":len(heldout),"overlap_phase19b":sum(key(x) in used for x in calibration+heldout),"policy_hash":manifest["policy_hash"]},indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
