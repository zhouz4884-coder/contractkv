"""Query-bound serving with business-output witnesses and measured readiness."""
from __future__ import annotations
import argparse
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_live as original
from scripts.tsc_revision_r1r_query_scope import query_scope, level_descent
from scripts.tsc_revision_r1r_business_stream import business_generate
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.phase20a_official_quality import standard_score


def prepare(args,sample,turn):
    case,raw,candidate,raw_messages,_=original.make_turn(args,sample,turn)
    if sample.get("shared_template_id"):
        raw_messages[0]["content"]=raw_messages[0]["content"].replace(sample["revision_session_id"],sample["shared_template_id"])
    budget=original.budget_for(args,sample)
    try:
        scope=query_scope(case,raw_messages[0],budget,args.model_identity,args.policy_hash)
        maximum=candidate["layout_level"]
    except ValueError:
        scope="unqualified:"+digest([case,raw_messages[0],budget,args.model_identity,args.policy_hash])
        maximum="L0"
    return case,raw_messages,maximum,budget,scope


def register(args,sample,prepared,business,turn):
    case,raw_messages,maximum,budget,scope=prepared
    begin=time.perf_counter(); attempts=[]
    rejected={"certificate_issued":False,"selected_level":"L0","query_scope":scope,"stable_prefix_tokens":0,
              "stable_prefix_hash":"","complete_verification_ms":0,"attempts":attempts,"failure_reason":""}
    if maximum=="L0": return {**rejected,"failure_reason":"frozen_family_raw"}
    try:
        if not business.get("witness_available"):
            raise ValueError(business.get("witness_failure","business witness unavailable"))
        answer,margins,stop=split_terminal_stop_token(business["output_token_ids"],business["reference_margins"],business["finish_reason"])
        for level in level_descent(maximum):
            layout=layout_for_level(case,level,args.protocol["layout"]["ladder"])
            order=layout["topological_order"]
            candidate=[raw_messages[0],{"role":"user","content":_ordered_text(order,case["segments"])}]
            by_id={s["segment_id"]:s for s in case["segments"]}; stable=[]
            for sid in order:
                if by_id[sid]["segment_type"] in {"TOOL_OBS","USER_QUERY","CHAT_HISTORY","SCRATCHPAD"}: break
                stable.append(sid)
            ids=tokenize(args.base_url,args.model,candidate,True,args.timeout)
            prefix=tokenize(args.base_url,args.model,[raw_messages[0],{"role":"user","content":_ordered_text(stable,case["segments"])}],False,args.timeout)
            stable_end=lcp_length(prefix,ids)
            payload={"request_id":f"{args.cell_id}-verify-{sample['revision_session_id']}-{scope[:12]}-{level}",
                     "txn_id":f"{args.cell_id}-txn-{sample['revision_session_id']}-{scope[:12]}-{level}",
                     "prompt_token_ids":ids+answer+[stop],"verify_start_token":len(ids),
                     "reference_answer_ids":answer,"reference_raw_margins":margins,"terminal_stop_token_id":stop,
                     "stable_prefix_end_token":stable_end,"policy_hash":args.policy_hash,"policy_version":"r1r-query-bound-v1",
                     "attestation_mode":"business-raw-strict-path-stop","stable_content_hash":digest(ids[:stable_end]),
                     "layout_hash":digest(order),"dependency_graph_hash":digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
                     "cache_salt":args.policy_hash+":"+sample.get("shared_template_id",sample["revision_session_id"]),
                     "allow_certified_prefix_read":args.policy=="query-prefix","timeout_s":args.timeout}
            started=time.perf_counter(); result=post_json(api_root(args.base_url)+"/v1/contractkv/verify",payload,args.timeout)
            attempt={"level":level,"verification_ms":(time.perf_counter()-started)*1000,**result}; attempts.append(attempt)
            if result.get("certificate_issued"):
                return {**rejected,**result,"selected_level":level,"stable_prefix_tokens":stable_end,
                        "stable_prefix_hash":digest(ids[:stable_end]),"complete_verification_ms":(time.perf_counter()-begin)*1000,
                        "attempts":attempts,"reference_source":"real_raw_business_output; no duplicate raw generation"}
        return {**rejected,"complete_verification_ms":(time.perf_counter()-begin)*1000,"failure_reason":"all_allowed_levels_rejected"}
    except Exception as exc:
        return {**rejected,"complete_verification_ms":(time.perf_counter()-begin)*1000,"failure_reason":str(exc)}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--protocol",type=Path,required=True); p.add_argument("--sessions",type=Path,required=True)
    p.add_argument("--model",required=True); p.add_argument("--model-identity",choices=original.FROZEN_LEVELS,required=True)
    p.add_argument("--policy",choices=["raw-order","query-full","query-prefix"],required=True)
    p.add_argument("--base-url",required=True); p.add_argument("--cell-id",required=True); p.add_argument("--policy-hash",required=True)
    p.add_argument("--repeat",type=int,required=True); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--summary",type=Path,required=True); p.add_argument("--metrics-events",type=Path,required=True)
    p.add_argument("--slack-ms",type=float,default=0); p.add_argument("--timeout",type=float,default=600)
    p.add_argument("--tenants-per-template",type=int,default=1)
    p.add_argument("--study",default="development")
    args=p.parse_args(); protocol_path=args.protocol
    args.protocol=json.loads(protocol_path.read_text()); args.experiment="free-generation"; args.output_budget=0
    samples=original.read_jsonl(args.sessions); rows=[]; certificates={}; verification_rows=[]
    if args.tenants_per_template>1:
        expanded=[]
        for sample in samples:
            template_id=sample["revision_session_id"]
            for tenant in range(args.tenants_per_template):
                clone=deepcopy(sample); clone["shared_template_id"]=template_id
                clone["revision_session_id"]=template_id+f"-tenant{tenant:02d}"
                expanded.append(clone)
        samples=expanded
    if args.output.exists(): raise RuntimeError("Preserve existing cell; no partial resume")
    args.output.parent.mkdir(parents=True,exist_ok=True); cell_start=time.perf_counter()
    def append(row):
        rows.append(row)
        with args.output.open('a',encoding='utf-8') as stream: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    for start in range(0,len(samples),args.protocol["runtime"]["concurrency"]):
        cohort=samples[start:start+args.protocol["runtime"]["concurrency"]]
        ready=time.perf_counter()
        for turn in range(10):
            jobs=[]; pending=[]
            for sample in cohort:
                prepared=prepare(args,sample,turn); case,raw_messages,maximum,budget,scope=prepared
                sid=sample["revision_session_id"]; namespace=sample.get("shared_template_id",sid); key=(namespace,scope); cert=certificates.get(key)
                compiled=args.policy!="raw-order" and bool(cert and cert.get("certificate_issued"))
                level=cert["selected_level"] if compiled else "L0"
                messages=raw_messages
                if compiled:
                    layout=layout_for_level(case,level,args.protocol["layout"]["ladder"])
                    messages=[raw_messages[0],{"role":"user","content":_ordered_text(layout["topological_order"],case["segments"])}]
                witness=args.policy!="raw-order" and cert is None and maximum!="L0"
                jobs.append((sample,prepared,messages,compiled,level,witness))
            time.sleep(max(0,ready-time.perf_counter()))
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                outputs=list(pool.map(lambda j:business_generate(args,j[2],j[1][3],f"{args.cell_id}-{j[0]['revision_session_id']}-t{turn}",j[5],
                                                                args.policy_hash+":"+j[0].get("shared_template_id",j[0]["revision_session_id"]) if j[3] else None),jobs))
            wave_end=max(o["end_time"] for o in outputs)
            for job,output in zip(jobs,outputs):
                sample,prepared,_,compiled,level,witness=job; case,_,maximum,budget,scope=prepared
                sid=sample["revision_session_id"]; score,metric,source=standard_score(sample["dataset"],sample["task"],output["output_text"],sample.get("answer",""))
                row={"row_type":"warm" if turn==0 else "future","session_id":sid,"source_group":sample["revision_source_group"],
                     "family":sample["revision_family"],"model":args.model_identity,"policy":args.policy,"repeat":args.repeat,"turn_id":turn,"study":args.study,
                     "query_scope":scope,"scope_previously_certified":compiled,"scope_first_raw_business":witness,
                     "certificate_namespace":sample.get("shared_template_id",sid),"tenant_id":sid,
                     "effective_level":level,"scope_invalid_admission":False,"output_budget":budget,
                     "task_score":score,"task_metric":metric,"metric_source":source,
                     **{k:v for k,v in output.items() if k not in {"reference_margins","first_time","end_time"}},
                     "ready_ttft_ms":(output["first_time"]-ready)*1000 if output["first_time"] else 0,
                     "reference_source":"actual business stream" if witness else "not_requested"}
                append(row)
                if witness:
                    namespace=sample.get("shared_template_id",sid)
                    if not any(j[0].get("shared_template_id",j[0]["revision_session_id"])==namespace and j[1][4]==scope for j in pending):
                        pending.append((sample,prepared,output))
            ready=wave_end+args.slack_ms/1000
            if pending:
                with ThreadPoolExecutor(max_workers=len(pending)) as pool:
                    results=list(pool.map(lambda j:register(args,j[0],j[1],j[2],turn),pending))
                for (sample,prepared,_),cert in zip(pending,results):
                    namespace=sample.get("shared_template_id",sample["revision_session_id"])
                    certificates[(namespace,prepared[4])]=cert
                    record={"row_type":"verification","session_id":sample["revision_session_id"],"certificate_namespace":namespace,"family":sample["revision_family"],"turn_id":turn,**cert}
                    verification_rows.append(record); append(record)
            print(json.dumps({"cell":args.cell_id,"cohort":start,"turn":turn,"futures":sum(r["row_type"]=="future" for r in rows)}),flush=True)
    time.sleep(.5); metrics=original.load_metrics(args.metrics_events)
    for row in rows:
        if row["row_type"] not in {"future","warm"}: continue
        event=metrics.get(row["request_id"],{}); row["metric_join_success"]=bool(event)
        row["prefix_hit_tokens"]=event.get("prefix_hit_tokens","unavailable")
        row["new_prefill_tokens"]=int(event["prompt_tokens"])-int(event["prefix_hit_tokens"]) if event else "unavailable"
    args.output.write_text("".join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    future=[r for r in rows if r["row_type"]=="future"]
    summary={"schema_version":"tsc-revision-r1r-live.v1","cell":args.cell_id,"study":args.study,"expected_futures":len(samples)*9,
             "sessions_sha256":hashlib.sha256(args.sessions.read_bytes()).hexdigest(),
             "protocol_sha256":hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
             "tenants_per_template":args.tenants_per_template,
             "futures":len(future),"successful_futures":sum(r["success"] for r in future),
             "metric_join_futures":sum(r["metric_join_success"] for r in future),
             "token_evidence_futures":sum(r["token_ids_available"] for r in future),
             "wall_s_including_all_setup_and_verification":time.perf_counter()-cell_start,
             "verification_calls":sum(len(r["attempts"]) for r in verification_rows),
             "verification_ms_total":sum(r["complete_verification_ms"] for r in verification_rows),
             "actual_cached_prefix_read_tokens":sum(int(a.get("cached_prefix_read_tokens",0)) for r in verification_rows for a in r["attempts"]),
             "compiled_future_requests":sum(r["effective_level"]!="L0" for r in future),
             "raw_file_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest(),
             "boundary":"Actual readiness-to-first-token includes controller waits; no offline subtraction. New queries initially served raw; their business outputs supply the witness."}
    args.summary.write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary),flush=True)
    return 0 if len(future)==len(samples)*9 and summary["successful_futures"]==len(future) and summary["metric_join_futures"]==len(future) else 2


if __name__=="__main__": raise SystemExit(main())
