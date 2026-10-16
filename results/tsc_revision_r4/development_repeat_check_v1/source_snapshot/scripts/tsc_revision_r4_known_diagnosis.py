"""Known Qwen metadata counterfactuals with actual IDs, cache and batch traces."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import Barrier,Lock
import time
import sys
from types import SimpleNamespace
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_live import read_jsonl,generation_payload,load_metrics
from scripts.tsc_revision_r2_candidate_plan import candidate_plan,verification_request
from scripts.tsc_revision_r2_margin_smoke import check_prompt_ids,forced_rows
from scripts.phase17_live_common import tokenize,post_json,api_root,digest
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.phase20a_official_quality import standard_score


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    for key in ('protocol','config','sessions','prompt-evidence','output','metrics','summary'):
        parser.add_argument('--'+key,type=Path,required=True)
    for key in ('base-url','policy-hash','cell-id'):parser.add_argument('--'+key,required=True)
    a=parser.parse_args()
    if a.output.exists():raise RuntimeError('Preserve every diagnostic attempt')
    config=json.loads(a.config.read_text(encoding='utf-8'))
    source=read_jsonl(a.sessions)[0];expected=json.loads(a.prompt_evidence.read_text(encoding='utf-8'))['prompt_ids']
    args=SimpleNamespace(protocol=json.loads(a.protocol.read_text(encoding='utf-8')),model='qwen3-8b',model_identity='Qwen3-8B',
                         policy_hash=a.policy_hash,base_url=a.base_url,timeout=600,experiment='free-generation',output_budget=0,cell_id=a.cell_id)
    a.output.parent.mkdir(parents=True,exist_ok=True);rows=[];lock=Lock();geometry={}
    def append(row):
        with lock:
            rows.append(row)
            with a.output.open('a',encoding='utf-8') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')
    for turn in (1,7):
        prepared=prepare(args,source,turn);plan=candidate_plan(args,prepared,'L3')
        for layout,messages,ids in [('raw',prepared[1],tokenize(a.base_url,args.model,prepared[1],True,600)),
                                    ('candidate',plan['messages'],plan['prompt_token_ids'])]:
            if ids!=expected[f'{layout}_t{turn}']:raise ValueError('Prompt identity changed from actual R3 record')
            geometry[layout,turn]=(messages,ids,prepared[3],plan)
    def generate(layout,turn,condition,repeat,concurrency,salt,issued=False):
        messages,ids,budget,_=geometry[layout,turn];barrier=Barrier(concurrency)
        def send(twin):
            rid=f'{a.cell_id}-r{repeat}-c{concurrency}-{condition}-t{turn}-n{twin}'
            payload={**generation_payload(args.model,messages,budget,14014),'request_id':rid,
                     'logprobs':True,'top_logprobs':2,'cache_salt':salt if condition=='warm' else rid}
            append({'role':'free_request','request_id':rid,'payload':payload,
                    'expected_prompt_ids_sha256':digest(ids),'recorded_before_dispatch':True})
            barrier.wait();started=time.perf_counter();body=post_json(a.base_url.rstrip('/')+'/chat/completions',payload,600);ended=time.perf_counter()
            try:
                check_prompt_ids(body,ids,True);tokens,margins,finish,_=extract_raw_tokens_and_margins(body)
                if body['usage']['completion_tokens']!=len(tokens):raise ValueError('Output ID/usage mismatch')
            except Exception as error:
                append({'role':'failed_response','request_payload':payload,'response':body,'error':repr(error)})
                raise
            text=body['choices'][0]['message'].get('content') or ''
            score,metric,metric_source=standard_score(source['dataset'],source['task'],text,source.get('answer',''))
            row={'role':'free','layout':layout,'turn':turn,'condition':condition,'repeat':repeat,'nominal_HTTP_concurrency':concurrency,
                 'twin':twin,'request_id':body['id'],'request_payload':payload,'prompt_token_ids':ids,'prompt_ids_sha256':digest(ids),
                 'output_token_ids':tokens,'reference_margins':margins,'output_text':text,'finish_reason':finish,
                 'witness_available':True,'task_score':score,'task_metric':metric,'metric_source':metric_source,
                 'start_time':started,'end_time':ended,'certificate_was_issued':issued,'response':body}
            append(row);return row
        with ThreadPoolExecutor(max_workers=concurrency) as pool:return list(pool.map(send,range(concurrency)))
    for repeat in range(1,config['sequential_repeats']+1):
        for concurrency in ((1,2) if repeat%2 else (2,1)):
            witness=generate('raw',1,'cold-raw',repeat,concurrency,'')[0]
            generate('raw',7,'cold-raw',repeat,concurrency,'')
            for turn in ((1,7) if repeat%2 else (7,1)):generate('candidate',turn,'cold-candidate',repeat,concurrency,'')
            answer,margins,stop=split_terminal_stop_token(witness['output_token_ids'],witness['reference_margins'],witness['finish_reason'])
            # Force the same actual witness on all four exact prompt variants.
            for layout in ('raw','candidate'):
                for turn in (1,7):
                    _,ids,_,_=geometry[layout,turn];rid=f'{a.cell_id}-r{repeat}-c{concurrency}-full-{layout}-t{turn}'
                    payload={'model':args.model,'prompt':ids+answer+[stop],'max_tokens':1,'temperature':0,'top_p':1,'seed':14014,
                             'prompt_logprobs':2,'return_token_ids':True,'request_id':rid,'cache_salt':rid}
                    append({'role':'full_request','request_id':rid,'payload':payload,
                            'prompt_ids_sha256':digest(payload['prompt']),'recorded_before_dispatch':True})
                    body=post_json(a.base_url.rstrip('/')+'/completions',payload,600)
                    target=forced_rows(body,ids,answer,stop)
                    append({'role':'full_logprob','layout':layout,'turn':turn,'repeat':repeat,'nominal_HTTP_concurrency':concurrency,
                            'request_id':body['id'],'request_payload':payload,'prompt_token_ids':payload['prompt'],
                            'target_rows':target,'all_target_rank_one':all(r['rank']==1 for r in target),'response':body})
            plan=geometry['candidate',1][3];salt=f'{a.cell_id}-r{repeat}-c{concurrency}-certificate'
            rid=salt+'-verify';payload,evidence=verification_request(args,plan,witness,rid,salt,False,'r4-known-case-diagnosis-v1')
            append({'role':'verification_request','request_id':rid,'payload':payload,**evidence})
            body=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,600)
            if not body.get('certificate_issued') and int(body.get('committed_tokens',0)):
                raise RuntimeError('Rejected verification published tokens')
            append({'role':'verification_response','request_id':rid,'response':body})
            for turn in ((7,1) if repeat%2 else (1,7)):
                generate('candidate',turn,'warm',repeat,concurrency,salt,bool(body.get('certificate_issued')))
        print(json.dumps({'cell':a.cell_id,'repeat':repeat,'free':sum(r['role']=='free' for r in rows)}),flush=True)
    time.sleep(.5);events=load_metrics(a.metrics);joins=[]
    for row in rows:
        if row['role'] not in ('free','full_logprob','verification_request'):continue
        rid=row['request_id']+('-0' if row['role']=='full_logprob' else '')
        event=events.get(rid);ids=row['payload']['prompt_token_ids'] if row['role']=='verification_request' else row['prompt_token_ids']
        match=bool(event) and event['prompt_tokens']==len(ids)
        joins.append({'request_id':row['request_id'],'engine_request_id':rid,'role':row['role'],'matches':match,
                      'prefix_hit_tokens':event.get('prefix_hit_tokens') if event else None,
                      'scheduler_running_requests':event.get('scheduler_running_requests') if event else None})
    counts={role:sum(r['role']==role for r in rows) for role in ('free','full_logprob','verification_request','verification_response')}
    complete=counts==config['expected_rows_per_gpu'] and all(r['matches'] for r in joins)
    result={'schema_version':'tsc-r4.known-case-diagnosis.v1','cell':a.cell_id,'execution_complete':complete,
            'counts':counts,'metric_rows':joins,'actual_historical_prompt_IDs_all_match':True,'raw_sha256':sha(a.output),
            'selected_known_failure_not_unseen_validation':True,'performance_claim':False,
            'batch_boundary':'Concurrency label denotes simultaneous HTTP twins; actual ModelRunner shapes recorded separately. Full-logprob and verification calls are sequential singleton controls.'}
    a.summary.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='metric_rows'}),flush=True)
    return 0 if complete else 2


if __name__=='__main__':raise SystemExit(main())
