"""Known-case causal controls with exact returned prompt IDs; no efficacy claim."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_live import generation_payload, read_jsonl, load_metrics
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.contractkv_verifier import split_terminal_stop_token, target_rank_and_margin, quantile
from scripts.contractkv_pstp import lcp_length
from scripts.phase20a_official_quality import standard_score


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_prompt_ids(response, expected, chat):
    actual = response.get('prompt_token_ids') if chat else response['choices'][0].get('prompt_token_ids')
    if actual != expected:
        raise ValueError('Server-returned prompt IDs differ or are unavailable')
    return digest(actual)


def forced_rows(response, ids, answer, stop):
    forced = ids + answer + [stop]
    check_prompt_ids(response, forced, False)
    logs = response['choices'][0].get('prompt_logprobs') or []
    if len(logs) != len(forced):
        raise ValueError('Full prompt logprob rows incomplete')
    rows = []
    for pos, token in enumerate(answer + [stop], start=len(ids)):
        rank, margin = target_rank_and_margin(logs[pos], token)
        rows.append({'position':pos, 'target_id':token, 'rank':rank, 'margin':margin,
                     'is_stop':pos == len(forced)-1, 'entry':logs[pos]})
    return rows


def main():
    p = argparse.ArgumentParser()
    for name in ('config', 'protocol', 'sessions', 'output', 'metrics'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--case', choices=('llama','mistral'), required=True)
    p.add_argument('--base-url', required=True)
    p.add_argument('--policy-hash', required=True)
    a = p.parse_args()
    if a.output.exists():
        raise RuntimeError('Preserve existing diagnostics; use a separate attempt')
    config = json.loads(a.config.read_text())
    spec = next(c for c in config['cases'] if c['key']==a.case)
    source = next(r for r in read_jsonl(a.sessions) if r['revision_session_id']==spec['source_session'])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(protocol=json.loads(a.protocol.read_text()), model=spec['served_model'],
                           model_identity=spec['model'], policy_hash=a.policy_hash,
                           base_url=a.base_url, timeout=600, experiment='free-generation', output_budget=0)
    rows = []; free_count = full_count = internal_count = 0
    def append(row):
        rows.append(row)
        with a.output.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
    def prepared(tenant, turn):
        s = deepcopy(source); s['shared_template_id']=s['revision_session_id']
        s['revision_session_id']+=f'-tenant{tenant:02d}'
        return s, prepare(args, s, turn)
    def generate(messages, ids, budget, rid, role, repeat, turn, level):
        nonlocal free_count
        started=time.perf_counter()
        response=post_json(a.base_url.rstrip('/')+'/chat/completions',
            {**generation_payload(args.model,messages,budget,14014), 'request_id':rid,
             'logprobs':True,'top_logprobs':2,'cache_salt':rid}, 600)
        try:
            echo=check_prompt_ids(response,ids,True)
            tokens,margins,finish,_=extract_raw_tokens_and_margins(response)
        except Exception as exc:
            append({'role':'incomplete_generation_response','request_payload_id':rid,
                    'expected_prompt_ids':ids,'response':response,'error':str(exc)})
            raise
        if len(tokens)!=response['usage']['completion_tokens']:
            raise ValueError('Actual output IDs/usage mismatch')
        text=response['choices'][0]['message'].get('content') or ''
        score,metric,metric_source=standard_score(source['dataset'],source['task'],text,source.get('answer',''))
        row={'role':role,'repeat':repeat,'turn':turn,'level':level,'model':args.model_identity,
             'request_id':response['id'],'request_payload_id':rid,'messages':messages,
             'prompt_token_ids':ids,'prompt_ids_sha256':echo,'prompt_ids_echo_equal':True,
             'output_token_ids':tokens,'raw_margins':margins,'finish_reason':finish,
             'text':text,'score':score,'metric':metric,'metric_source':metric_source,
             'wall_ms':(time.perf_counter()-started)*1000,'response':response}
        append(row); free_count+=1
        return row
    for repeat in range(1,config['sequential_repeats_in_same_process']+1):
        witness_sample,wp=prepared(spec['witness_tenant'],spec['witness_turn'])
        wc,wm,_,budget,scope=wp
        wid=tokenize(a.base_url,args.model,wm,True,600)
        prefix=f'r2-dx-{a.case}-r{repeat}'
        witness=generate(wm,wid,budget,prefix+'-witness','raw_witness',repeat,spec['witness_turn'],'L0')
        answer,margins,stop=split_terminal_stop_token(witness['output_token_ids'],witness['raw_margins'],witness['finish_reason'])
        levels=spec['levels'] if repeat%2 else list(reversed(spec['levels']))
        for variant,tenant,turn in (('witness',spec['witness_tenant'],spec['witness_turn']),('future',spec['future_tenant'],spec['future_turn'])):
            sample,pr=prepared(tenant,turn); case,raw_messages,_,budget,query=pr
            if query!=scope:
                raise ValueError('Planned metadata-only pair has different query scope')
            for level in levels:
                order=layout_for_level(case,level,args.protocol['layout']['ladder'])['topological_order']
                messages=[raw_messages[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
                ids=tokenize(a.base_url,args.model,messages,True,600)
                rid=f'{prefix}-{variant}-{level}'
                out=generate(messages,ids,budget,rid+'-free','free_'+variant,repeat,turn,level)
                forced=ids+answer+[stop]
                started=time.perf_counter()
                response=post_json(a.base_url.rstrip('/')+'/completions',
                    {'model':args.model,'prompt':forced,'max_tokens':1,'temperature':0,'top_p':1,'seed':14014,
                     'prompt_logprobs':2,'return_token_ids':True,'request_id':rid+'-full',
                     'cache_salt':rid+'-full'},600)
                try:
                    lp=forced_rows(response,ids,answer,stop)
                except Exception as exc:
                    append({'role':'incomplete_full_logprob_response','request_payload_id':rid+'-full',
                            'expected_prompt_ids':forced,'response':response,'error':str(exc)})
                    raise
                full_count+=1
                append({'role':'full_logprob_'+variant,'repeat':repeat,'turn':turn,'level':level,
                        'request_id':response['id'],'request_payload_id':rid+'-full',
                        'prompt_token_ids':forced,'prompt_ids_sha256':digest(forced),'prompt_ids_echo_equal':True,
                        'target_rows':lp,'rank_one_answer_and_stop':all(r['rank']==1 for r in lp),
                        'candidate_margin_q05':quantile([r['margin'] for r in lp[:-1]],.05),
                        'terminal_stop_margin':lp[-1]['margin'],'response':response,
                        'wall_ms':(time.perf_counter()-started)*1000})
                if level=='L0':
                    continue
                by_id={s['segment_id']:s for s in case['segments']}; stable=[]
                for sid in order:
                    if by_id[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}: break
                    stable.append(sid)
                stable_ids=tokenize(a.base_url,args.model,[raw_messages[0],{'role':'user','content':_ordered_text(stable,case['segments'])}],False,600)
                stable_end=lcp_length(stable_ids,ids)
                payload={'request_id':rid+'-internal','txn_id':rid+'-txn','prompt_token_ids':forced,
                         'verify_start_token':len(ids),'reference_answer_ids':answer,'reference_raw_margins':margins,
                         'terminal_stop_token_id':stop,'stable_prefix_end_token':stable_end,
                         'policy_hash':a.policy_hash,'policy_version':'r2-diagnosis-v1',
                         'attestation_mode':'selected-known-case-diagnostic',
                         'stable_content_hash':digest(ids[:stable_end]),'layout_hash':digest(order),
                         'dependency_graph_hash':digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
                         'cache_salt':rid+'-internal','allow_certified_prefix_read':False,'timeout_s':600}
                response=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,600)
                internal_count+=1
                append({'role':'internal_'+variant,'repeat':repeat,'turn':turn,'level':level,
                        'request_id':response.get('request_id'),'payload':payload,'response':response,
                        'fresh_witness_score':witness['score'],'free_output_score':out['score'],
                        'free_matches_witness':out['output_token_ids']==witness['output_token_ids'],
                        'full_rank_one':all(r['rank']==1 for r in lp)})
        print(json.dumps({'case':a.case,'repeat':repeat,'free_generations':free_count,'full_logprob_calls':full_count,'internal_calls':internal_count}),flush=True)
    time.sleep(.5)
    events=load_metrics(a.metrics)
    metric_rows=[]
    for row in rows:
        if not row['role'].startswith(('raw_witness','free_','full_logprob_')): continue
        event=events.get(row['request_id'])
        metric_rows.append({'request_id':row['request_id'],'role':row['role'],'metric_join':bool(event),
                            'event':event,'prompt_ids_echo_equal':row['prompt_ids_echo_equal']})
    complete=(free_count==config['expected_free_generations'][a.case] and full_count==config['expected_full_logprob_calls'][a.case]
              and internal_count==config['expected_internal_calls'][a.case] and all(r['metric_join'] for r in metric_rows))
    summary={'schema_version':'tsc-r2.known-case-diagnostic-completion.v1','case':a.case,'free_generations':free_count,
             'full_logprob_calls':full_count,'internal_calls':internal_count,'all_echoed_prompt_ids_equal':True,
             'execution_complete':complete,'metric_rows':metric_rows,'raw_sha256':sha(a.output),
             'selected_known_failures_are_development_only':True,'heldout_or_performance_claim':False,
             'sequential_repeats_are_not_fresh_process_repeats':True,'cache_condition':config['cache_condition']}
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='metric_rows'}),flush=True)
    return 0 if complete else 2


if __name__=='__main__':
    raise SystemExit(main())
