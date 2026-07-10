#!/usr/bin/env python3
"""Build an 8T-resident, deterministic full-pool Phase 14D workload."""
from __future__ import annotations
import argparse,csv,hashlib,json,random,sys
from collections import Counter
from pathlib import Path
from typing import Any
if __package__ is None or __package__ == "":sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_dataset_samples import _sample,_segment,_repo_prompt_segments,ruler_samples,write_jsonl

TASKS=("hotpotqa","qasper","narrativeqa")
def partition(dataset:str,task:str,sample_id:str,seed:int=14014)->str:
 h=hashlib.sha256(f"{seed}|{dataset}|{task}|{sample_id}".encode()).digest()[0]%10
 return "calibration" if h<2 else "held_out_quality" if h<4 else "live_serving"
def _raw_data_dir(cache:str)->Path:
 candidates=list(Path(cache).glob("datasets/downloads/extracted/*/data"))
 for candidate in candidates:
  if (candidate/"hotpotqa.jsonl").exists():return candidate
 raise FileNotFoundError("cached LongBench JSONL data directory not found")
def _longbench(task:str,count:int,cache:str)->list[dict[str,Any]]:
 path=_raw_data_dir(cache)/f"{task}.jsonl"
 data=[json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
 out=[]
 for i,row in enumerate(data[:min(count,len(data))]):
  seg=[_segment("SYS_PROMPT","Answer only from the supplied context.",None),_segment("RAG_CHUNK",str(row.get("context","")),None),_segment("USER_QUERY",str(row.get("input","")),None)]
  out.append(_sample("LongBench",task,str(i),seg,row.get("answers",[]),{"source_note":"THUDM/LongBench local HF cache","split":"test","evaluation_ready":True}))
 return out
def _repo(count:int,cache:str)->list[dict[str,Any]]:
 import pyarrow.parquet as pq
 files=list(Path(cache).glob("hub/datasets--tianyang--repobench_python_v1.1/snapshots/*/data/in_file*.parquet"))
 if not files:raise FileNotFoundError("cached RepoBench in_file parquet not found")
 data=pq.read_table(files[0]).to_pylist()
 out=[]
 for i,row in enumerate(data[:min(count,len(data))]):
  row=dict(row);answer=row.get("next_line") or row.get("target") or row.get("answer") or ""
  out.append(_sample("RepoBench","python_v1.1",str(i),_repo_prompt_segments(row,None),answer,{"source_note":"tianyang/repobench_python_v1.1 local HF cache","evaluation_ready":False,"split":"cached"}))
 return out
def build(cache:str)->list[dict[str,Any]]:
 rows=ruler_samples(200,None)
 for task in TASKS:rows.extend(_longbench(task,200,cache))
 rows.extend(_repo(500,cache))
 for r in rows:r["metadata"]["phase14_partition"]=partition(r["dataset"],r["task"],r["sample_id"])
 return rows
def write_summary(path:Path,rows:list[dict[str,Any]],seed:int):
 c=Counter((r['dataset'],r['task'],r['metadata']['phase14_partition']) for r in rows);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=['dataset','task','partition','count','seed','claim_boundary']);w.writeheader()
  for (d,t,p),n in sorted(c.items()):w.writerow({'dataset':d,'task':t,'partition':p,'count':n,'seed':seed,'claim_boundary':'Full local-cache pool manifest; live serving and held-out quality partitions are disjoint.'})
def main():
 p=argparse.ArgumentParser();p.add_argument('--hf-cache-dir',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);p.add_argument('--seed',type=int,default=14014);a=p.parse_args();rows=build(a.hf_cache_dir);write_jsonl(a.output,rows);write_summary(a.summary,rows,a.seed);print('full_pool_rows=',len(rows));print(Counter(r['metadata']['phase14_partition'] for r in rows))
if __name__=='__main__':main()
