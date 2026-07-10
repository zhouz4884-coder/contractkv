#!/usr/bin/env python3
"""Build an 8T-resident, deterministic full-pool Phase 14D workload."""
from __future__ import annotations
import argparse,csv,hashlib,json,random,sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
if __package__ is None or __package__ == "":sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_dataset_samples import _sample,_segment,_repo_prompt_segments,ruler_samples,write_jsonl

TASKS=("hotpotqa","qasper","narrativeqa")
def partition(dataset:str,task:str,sample_id:str,seed:int=14014,source_group_id:str="")->str:
 key=source_group_id or sample_id
 h=hashlib.sha256(f"{seed}|{dataset}|{task}|{key}".encode()).digest()[0]%10
 return "calibration" if h<2 else "held_out_quality" if h<4 else "live_serving"
def _length_bucket(text:str)->str:
 n=len(str(text).split())
 if n<1000:return "short"
 if n<4000:return "medium"
 return "long"
def _stratified_rows(rows:list[dict[str,Any]],count:int,seed:int,key_fn)->list[dict[str,Any]]:
 groups=defaultdict(list)
 for row in rows:groups[key_fn(row)].append(row)
 rng=random.Random(seed)
 for group in groups.values():rng.shuffle(group)
 selected=[]
 keys=sorted(groups)
 while len(selected)<min(count,len(rows)) and keys:
  progressed=False
  for key in list(keys):
   if groups[key]:
    selected.append(groups[key].pop())
    progressed=True
    if len(selected)>=min(count,len(rows)):break
   else:
    keys.remove(key)
  if not progressed:break
 return selected
def _stable_int(text:str)->int:
 return int(hashlib.sha256(text.encode()).hexdigest()[:8],16)
def _raw_data_dir(cache:str)->Path:
 candidates=list(Path(cache).glob("datasets/downloads/extracted/*/data"))
 for candidate in candidates:
  if (candidate/"hotpotqa.jsonl").exists():return candidate
 raise FileNotFoundError("cached LongBench JSONL data directory not found")
def _longbench(task:str,count:int,cache:str,seed:int)->list[dict[str,Any]]:
 path=_raw_data_dir(cache)/f"{task}.jsonl"
 data=[json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
 out=[]
 indexed=[dict(row, _source_index=i) for i,row in enumerate(data)]
 sampled=_stratified_rows(indexed,count,seed+_stable_int(task)%997,lambda r:(_length_bucket(r.get("context","")),str(r.get("answers",[""])[0])[:16],int(r.get("_source_index",0))%17))
 for i,row in enumerate(sampled):
  source_group=f"{task}:doc:{row.get('_source_index',i)}"
  seg=[_segment("SYS_PROMPT","Answer only from the supplied context.",None),_segment("RAG_CHUNK",str(row.get("context","")),None),_segment("USER_QUERY",str(row.get("input","")),None)]
  out.append(_sample("LongBench",task,str(i),seg,row.get("answers",[]),{"source_note":"THUDM/LongBench local HF cache","split":"test","evaluation_ready":True,"source_group_id":source_group,"source_index":row.get("_source_index",i)}))
 return out
def _repo(count:int,cache:str,seed:int)->list[dict[str,Any]]:
 import pyarrow.parquet as pq
 files=list(Path(cache).glob("hub/datasets--tianyang--repobench_python_v1.1/snapshots/*/data/in_file*.parquet"))
 if not files:raise FileNotFoundError("cached RepoBench in_file parquet not found")
 data=pq.read_table(files[0]).to_pylist()
 out=[]
 def repo_id(row):
  for field in ("repository","repo","repo_name","repo_id","file_path","path"):
   if row.get(field):return str(row.get(field)).split("/")[0]
  return str(row.get("task_id") or row.get("id") or "unknown")
 indexed=[dict(row, _source_index=i, _repo_group=repo_id(row)) for i,row in enumerate(data)]
 sampled=_stratified_rows(indexed,count,seed+431,lambda r:(_length_bucket(" ".join(str(r.get(k,"")) for k in ("cropped_code","code","context"))),r.get("_repo_group","unknown")))
 for i,row in enumerate(sampled):
  row=dict(row);answer=row.get("next_line") or row.get("target") or row.get("answer") or ""
  out.append(_sample("RepoBench","python_v1.1",str(i),_repo_prompt_segments(row,None),answer,{"source_note":"tianyang/repobench_python_v1.1 local HF cache","evaluation_ready":False,"split":"cached","source_group_id":row.get("_repo_group","unknown"),"source_index":row.get("_source_index",i)}))
 return out
def build(cache:str,seed:int=14014)->list[dict[str,Any]]:
 rows=ruler_samples(200,None)
 for i,r in enumerate(rows):r["metadata"]["source_group_id"]=f"ruler:{i}"
 for task in TASKS:rows.extend(_longbench(task,200,cache,seed))
 rows.extend(_repo(500,cache,seed))
 for r in rows:
  source_group=str(r.get("metadata",{}).get("source_group_id",""))
  r["metadata"]["phase14_partition"]=partition(r["dataset"],r["task"],r["sample_id"],seed,source_group)
 return rows
def write_summary(path:Path,rows:list[dict[str,Any]],seed:int):
 c=Counter((r['dataset'],r['task'],r['metadata']['phase14_partition']) for r in rows);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=['dataset','task','partition','count','seed','claim_boundary']);w.writeheader()
  for (d,t,p),n in sorted(c.items()):w.writerow({'dataset':d,'task':t,'partition':p,'count':n,'seed':seed,'claim_boundary':'Full local-cache pool manifest; live serving and held-out quality partitions are disjoint.'})
def main():
 p=argparse.ArgumentParser();p.add_argument('--hf-cache-dir',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);p.add_argument('--seed',type=int,default=14014);a=p.parse_args();rows=build(a.hf_cache_dir,a.seed);write_jsonl(a.output,rows);write_summary(a.summary,rows,a.seed);print('full_pool_rows=',len(rows));print(Counter(r['metadata']['phase14_partition'] for r in rows))
if __name__=='__main__':main()
