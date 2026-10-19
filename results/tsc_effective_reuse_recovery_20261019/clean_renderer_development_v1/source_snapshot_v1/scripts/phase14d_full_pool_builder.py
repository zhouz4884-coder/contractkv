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
def _answer_length_bucket(answer:Any)->str:
 n=len(str(answer).split())
 if n<4:return "short"
 if n<16:return "medium"
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
 sampled=_stratified_rows(indexed,count,seed+_stable_int(task)%997,lambda r:(_length_bucket(r.get("context","")),_answer_length_bucket((r.get("answers") or [""])[0])))
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
  for field in ("repository","repo","repo_name","repo_id"):
   if row.get(field):return str(row.get(field)).strip("/\\") or "unknown"
  for field in ("file_path","path"):
   if row.get(field):
    parts=[part for part in str(row.get(field)).replace("\\","/").split("/") if part and part not in {".",".."}]
    if len(parts)>=2:return "/".join(parts[:2])
    if parts:return parts[0]
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
def write_audit(path:Path,rows:list[dict[str,Any]]):
 path.parent.mkdir(parents=True,exist_ok=True)
 fields=['dataset','task','partition','samples','unique_source_groups','largest_group_size','empty_or_unknown_groups','groups_crossing_partitions','context_tokens_p50','context_tokens_p95','answer_words_p50','answer_words_p95','claim_boundary']
 grouped=defaultdict(list)
 group_partitions=defaultdict(set)
 for row in rows:
  meta=row.get('metadata',{});group=str(meta.get('source_group_id',''))
  grouped[(row['dataset'],row['task'],meta.get('phase14_partition',''))].append(row)
  group_partitions[(row['dataset'],row['task'],group)].add(meta.get('phase14_partition',''))
 def percentile(values,p):
  values=sorted(values)
  return values[min(len(values)-1,int((len(values)-1)*p))] if values else 0
 with path.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for (dataset,task,part),group_rows in sorted(grouped.items()):
   ids=[str(r.get('metadata',{}).get('source_group_id','')) for r in group_rows]
   sizes=Counter(ids);context_tokens=[];answer_words=[]
   for row in group_rows:
    context_tokens.append(sum(int(seg.get('token_count') or 0) for seg in row.get('segments',[]) if seg.get('type') not in {'SYS_PROMPT','USER_QUERY'}))
    answer_words.append(len(str(row.get('answer','')).split()))
   crossing=sum(len(parts)>1 for (d,t,_),parts in group_partitions.items() if d==dataset and t==task)
   w.writerow({'dataset':dataset,'task':task,'partition':part,'samples':len(group_rows),'unique_source_groups':len(set(ids)),'largest_group_size':max(sizes.values()) if sizes else 0,'empty_or_unknown_groups':sum(value in {'','unknown'} for value in ids),'groups_crossing_partitions':crossing,'context_tokens_p50':percentile(context_tokens,.5),'context_tokens_p95':percentile(context_tokens,.95),'answer_words_p50':percentile(answer_words,.5),'answer_words_p95':percentile(answer_words,.95),'claim_boundary':'Deterministic split audit; zero cross-partition source groups is required.'})
def main():
 p=argparse.ArgumentParser();p.add_argument('--hf-cache-dir',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);p.add_argument('--audit-output',type=Path,default=Path('results/workload/phase14d_full_pool_audit.csv'));p.add_argument('--seed',type=int,default=14014);a=p.parse_args();rows=build(a.hf_cache_dir,a.seed);write_jsonl(a.output,rows);write_summary(a.summary,rows,a.seed);write_audit(a.audit_output,rows);print('full_pool_rows=',len(rows));print(Counter(r['metadata']['phase14_partition'] for r in rows))
if __name__=='__main__':main()
