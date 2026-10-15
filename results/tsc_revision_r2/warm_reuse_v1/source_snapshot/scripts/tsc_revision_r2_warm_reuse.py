"""Compare same-ID cold decode with actual use of an attested KV prefix."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_diagnose import check_prompt_ids
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_live import generation_payload,read_jsonl,load_metrics
from scripts.phase17_live_common import api_root,digest,post_json,tokenize
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.contractkv_pstp import lcp_length
from scripts.phase20a_official_quality import standard_score


def main():
    p=argparse.ArgumentParser()
    for name in ('config','protocol','sessions','output','metrics'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',choices=('llama','mistral'),required=True)
    p.add_argument('--base-url',required=True); p.add_argument('--policy-hash',required=True)
    a=p.parse_args(); config=json.loads(a.config.read_text(encoding='utf-8'))
    cases=json.loads(Path(config['case_config']).read_text(encoding='utf-8'))
    spec=next(c for c in cases['cases'] if c['key']==a.case)
    source=next(s for s in read_jsonl(a.sessions) if s['revision_session_id']==spec['source_session'])
    args=SimpleNamespace(protocol=json.loads(a.protocol.read_text(encoding='utf-8')),model=spec['served_model'],
                         model_identity=spec['model'],policy_hash=a.policy_hash,base_url=a.base_url,
                         timeout=600,experiment='free-generation',output_budget=0)
    if a.output.exists(): raise RuntimeError('Preserve prior attempt')
    a.output.parent.mkdir(parents=True,exist_ok=True); records=[]
    def append(row):
        records.append(row)
        with a.output.open('a',encoding='utf-8') as stream: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    def prepare_turn(tenant,turn):
        sample=deepcopy(source); sample['shared_template_id']=sample['revision_session_id']
        sample['revision_session_id']+=f'-tenant{tenant:02d}'
        return prepare(args,sample,turn)
    def generate(messages,ids,budget,rid,salt,role,repeat,variant):
        response=post_json(a.base_url.rstrip('/')+'/chat/completions',
            {**generation_payload(args.model,messages,budget,14014),'request_id':rid,
             'cache_salt':salt,'logprobs':True,'top_logprobs':2},600)
        try:
            prompt_hash=check_prompt_ids(response,ids,True)
            tokens,margins,finish,_=extract_raw_tokens_and_margins(response)
            if len(tokens)!=response['usage']['completion_tokens']: raise ValueError('Output usage mismatch')
        except Exception as exc:
            append({'role':'incomplete_response','response':response,'expected_prompt_ids':ids,'error':str(exc)})
            raise
        text=response['choices'][0]['message'].get('content') or ''
        score,metric,metric_source=standard_score(source['dataset'],source['task'],text,source.get('answer',''))
        row={'role':role,'variant':variant,'repeat':repeat,'request_id':response['id'],
             'messages':messages,'prompt_token_ids':ids,'prompt_ids_sha256':prompt_hash,
             'output_token_ids':tokens,'raw_margins':margins,'finish_reason':finish,'text':text,
             'score':score,'metric':metric,'metric_source':metric_source,'cache_salt':salt,'response':response}
        append(row); return row
    for repeat in range(1,config['sequential_repeats_per_fresh_server']+1):
        prefix=f'r2-warm-{a.case}-r{repeat}'; salt=a.policy_hash+':'+prefix
        wp=prepare_turn(spec['witness_tenant'],spec['witness_turn'])
        case,raw_messages,_,budget,scope=wp
        ids=tokenize(a.base_url,args.model,raw_messages,True,600)
        witness=generate(raw_messages,ids,budget,prefix+'-reference',salt+'-raw-reference','reference',repeat,'witness')
        answer,margins,stop=split_terminal_stop_token(witness['output_token_ids'],witness['raw_margins'],witness['finish_reason'])
        order=layout_for_level(case,config['level'],args.protocol['layout']['ladder'])['topological_order']
        candidate=[raw_messages[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
        candidate_ids=tokenize(a.base_url,args.model,candidate,True,600)
        by_id={s['segment_id']:s for s in case['segments']}; stable=[]
        for sid in order:
            if by_id[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}: break
            stable.append(sid)
        stable_ids=tokenize(a.base_url,args.model,[raw_messages[0],{'role':'user','content':_ordered_text(stable,case['segments'])}],False,600)
        stable_end=lcp_length(stable_ids,candidate_ids)
        payload={'request_id':prefix+'-verify','txn_id':prefix+'-txn','prompt_token_ids':candidate_ids+answer+[stop],
                 'verify_start_token':len(candidate_ids),'reference_answer_ids':answer,'reference_raw_margins':margins,
                 'terminal_stop_token_id':stop,'stable_prefix_end_token':stable_end,'policy_hash':a.policy_hash,
                 'policy_version':'r2-warm-diagnostic-v1','attestation_mode':'selected-case-matching-salt-replay',
                 'stable_content_hash':digest(candidate_ids[:stable_end]),'layout_hash':digest(order),
                 'dependency_graph_hash':digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
                 'cache_salt':salt,'allow_certified_prefix_read':False,'timeout_s':600}
        verification=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,600)
        append({'role':'qualification','repeat':repeat,'request_id':verification['request_id'],'payload':payload,'response':verification})
        for variant,tenant,turn in (('witness',spec['witness_tenant'],spec['witness_turn']),('future',spec['future_tenant'],spec['future_turn'])):
            case,raw_messages,_,budget,current_scope=prepare_turn(tenant,turn)
            if current_scope!=scope: raise ValueError('Query scope changed')
            raw_ids=tokenize(a.base_url,args.model,raw_messages,True,600)
            generate(raw_messages,raw_ids,budget,prefix+'-'+variant+'-raw',salt+'-raw-'+variant,'raw',repeat,variant)
            order=layout_for_level(case,config['level'],args.protocol['layout']['ladder'])['topological_order']
            messages=[raw_messages[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
            ids=tokenize(a.base_url,args.model,messages,True,600)
            conditions=('cold','certified_salt') if repeat%2 else ('certified_salt','cold')
            for condition in conditions:
                rid=prefix+'-'+variant+'-'+condition
                generate(messages,ids,budget,rid,salt if condition=='certified_salt' else salt+'-cold-'+variant,condition,repeat,variant)
        print(json.dumps({'case':a.case,'repeat':repeat,'records':len(records)}),flush=True)
    time.sleep(.5); events=load_metrics(a.metrics); joined=[]
    for row in records:
        event=events.get(row['request_id'])
        ids=row['payload']['prompt_token_ids'] if row['role']=='qualification' else row['prompt_token_ids']
        if not event or event['prompt_tokens']!=len(ids): raise ValueError('Actual engine metric identity/count missing')
        joined.append({'role':row['role'],'variant':row.get('variant'),'repeat':row['repeat'],
                       'request_id':row['request_id'],'prompt_tokens':event['prompt_tokens'],
                       'prefix_hit_tokens':event['prefix_hit_tokens']})
    free=sum(r['role']!='qualification' for r in records); internal=sum(r['role']=='qualification' for r in records)
    complete=free==config['expected_free_generations_per_model'] and internal==config['expected_internal_calls_per_model']
    summary={'schema_version':'tsc-r2.warm-reuse-diagnostic.v1','case':a.case,'execution_complete':complete,
             'free_generations':free,'internal_calls':internal,'actual_metric_joins':len(joined),'observations':joined,
             'raw_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
             'selected_development_not_heldout':True,'performance_claim':False,
             'positive_reuse_evidence_requires_actual_prefix_hit_and_passed_qualification':True}
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return 0 if complete else 2


if __name__=='__main__': raise SystemExit(main())
