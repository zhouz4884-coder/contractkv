#!/usr/bin/env python3
"""Calibrate a task-name-free QC gate from paired Phase 13C outcomes."""
from __future__ import annotations
import argparse,csv,json,re,sys
from pathlib import Path
from collections import defaultdict
from typing import Any
if __package__ is None or __package__ == "": sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case,load_jsonl
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase12f_real_vllm_caposc_replay import compile_for_real_replay

HEAD=re.compile(r"(?im)^\s*(abstract|introduction|background|method|methods|results|discussion|conclusion|related work|experiments?)s?\b")
CUE=re.compile(r"(?i)\b(this paper|we propose|we present|our method|our approach|we evaluate|experimental results|baseline|dataset)\b")
FIELDS=['dataset','task','sample_id','split_trace','split_task','quality_drop_vs_raw','unsafe_quality_drop','hard_edge_valid','adjacency_preservation','edit_distance','ordered_discourse_signal','expected_prefix_gain','risk_bucket','risk_ucb','qc_fallback','safe_optimization','false_safe','claim_boundary']
SUM=['split','requests','unsafe_requests','fallback_rate','false_safe_rate','safe_optimization_coverage','unsafe_caught_rate','claim_boundary']
def score(v:Any)->float:
 try:return float(v)
 except:return 0.
def adjacency(a,b):
 return sum(p in set(zip(b,b[1:])) for p in zip(a,a[1:]))/max(1,len(a)-1)
def rows(samples,outcomes,eps=.03):
 pair=defaultdict(dict)
 for r in outcomes: pair[(r['dataset'],r['task'],str(r['sample_id']))][r['policy']]=r
 result=[]
 for s in samples:
  k=(s.get('dataset',''),s.get('task',''),str(s.get('sample_id','')))
  if 'raw-order' not in pair[k] or 'contractkv-caposc' not in pair[k]:continue
  case=build_case(s,stable_word_limit=2600); raw=[x['segment_id'] for x in case['segments']]
  cap=compile_for_real_replay('cache-aware-posc',case,SegmentPrefixLedger()); order=cap['topological_order']
  text='\n'.join(str(x.get('text','')) for x in case['segments'] if x.get('segment_type')=='RAG_CHUNK')
  discourse=len(HEAD.findall(text))+len(CUE.findall(text)); edit=sum(a!=b for a,b in zip(raw,order)); adj=adjacency(raw,order)
  drop=max(0.,score(pair[k]['raw-order'].get('score'))-score(pair[k]['contractkv-caposc'].get('score'))); unsafe=drop>eps
  # Generic structural UCB: ordered discourse moved across an insertion is fail-closed.
  high=(discourse>=2 and edit>0) or bool(cap.get('violated_edges')); ucb=0.05 if high else 0.0; fallback=ucb>eps
  sid=int(str(s.get('sample_id','0')) or 0)
  result.append({'dataset':k[0],'task':k[1],'sample_id':k[2],'split_trace':'held_out' if sid>=15 else 'calibration','split_task':'held_out_task' if k[1]=='qasper' else 'calibration_task','quality_drop_vs_raw':round(drop,6),'unsafe_quality_drop':unsafe,'hard_edge_valid':not bool(cap.get('violated_edges')),'adjacency_preservation':round(adj,6),'edit_distance':edit,'ordered_discourse_signal':discourse,'expected_prefix_gain':cap.get('estimated_lcp_tokens',0),'risk_bucket':'ordered_discourse' if high else 'low_structure','risk_ucb':ucb,'qc_fallback':fallback,'safe_optimization':(not fallback) and not unsafe,'false_safe':(not fallback) and unsafe,'claim_boundary':'Held-out evaluation uses task-name-free structural features and Phase13C task-sanity labels; not official benchmark scoring.'})
 return result
def summary(rs):
 groups={'all':rs,'held_out_trace':[r for r in rs if r['split_trace']=='held_out'],'held_out_task':[r for r in rs if r['split_task']=='held_out_task']};o=[]
 for n,g in groups.items():
  unsafe=[r for r in g if r['unsafe_quality_drop']]; accepted=[r for r in g if not r['qc_fallback']]; safe=[r for r in g if not r['unsafe_quality_drop']]
  o.append({'split':n,'requests':len(g),'unsafe_requests':len(unsafe),'fallback_rate':round(sum(r['qc_fallback'] for r in g)/len(g),6),'false_safe_rate':round(sum(r['false_safe'] for r in g)/max(1,len(accepted)),6),'safe_optimization_coverage':round(sum(r['safe_optimization'] for r in g)/max(1,len(safe)),6),'unsafe_caught_rate':round(sum(r['qc_fallback'] for r in unsafe)/max(1,len(unsafe)),6),'claim_boundary':'QC gate is a generic structural fail-closed baseline; held-out outcomes are Phase13C task-sanity labels.'})
 return o
def write(path,rs,fields):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rs)
def main():
 p=argparse.ArgumentParser();p.add_argument('--samples',type=Path,default=Path('results/datasets/sample_prompts.jsonl'));p.add_argument('--outcomes',type=Path,default=Path('results/end_to_end/phase13c_quality_raw_v0.jsonl'));p.add_argument('--raw-output',type=Path,default=Path('results/end_to_end/phase14c_qc_calibration_raw_v0.csv'));p.add_argument('--summary-output',type=Path,default=Path('results/end_to_end/phase14c_qc_calibration_summary_v0.csv'));a=p.parse_args();r=rows(load_jsonl(a.samples),load_jsonl(a.outcomes));write(a.raw_output,r,FIELDS);write(a.summary_output,summary(r),SUM);print('rows=',len(r))
if __name__=='__main__':main()
