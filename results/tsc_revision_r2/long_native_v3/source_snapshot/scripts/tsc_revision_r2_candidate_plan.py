"""One explicit candidate plan and an exact-ID verification request."""
import time
from scripts.phase17_live_common import digest,tokenize
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_verifier import split_terminal_stop_token


def candidate_plan(args,prepared,level):
    started=time.perf_counter(); case,raw_messages,maximum,budget,scope=prepared
    if level=='L0' or int(level[1:])>int(maximum[1:]): raise ValueError('Candidate outside inherited eligibility')
    order=layout_for_level(case,level,args.protocol['layout']['ladder'])['topological_order']
    messages=[raw_messages[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
    ids=tokenize(args.base_url,args.model,messages,True,args.timeout)
    by_id={s['segment_id']:s for s in case['segments']}; stable=[]
    for sid in order:
        if by_id[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}: break
        stable.append(sid)
    prefix=tokenize(args.base_url,args.model,[raw_messages[0],{'role':'user','content':_ordered_text(stable,case['segments'])}],False,args.timeout)
    end=lcp_length(prefix,ids)
    return {'level':level,'messages':messages,'prompt_token_ids':ids,'prompt_ids_sha256':digest(ids),
            'stable_prefix_end_token':end,'stable_full_blocks':end//16,'stable_content_hash':digest(ids[:end]),
            'layout_hash':digest(order),'dependency_graph_hash':digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
            'query_scope':scope,'output_budget':budget,'cpu_http_preparation_ms':(time.perf_counter()-started)*1000}


def verification_request(args,plan,business,rid,cache_salt,allow_prefix_read,version):
    if not business.get('witness_available'): raise ValueError('Actual business LP witness unavailable')
    answer,margins,stop=split_terminal_stop_token(business['output_token_ids'],business['reference_margins'],business['finish_reason'])
    forced=plan['prompt_token_ids']+answer+[stop]
    payload={'request_id':rid,'txn_id':rid+'-txn','prompt_token_ids':forced,
             'verify_start_token':len(plan['prompt_token_ids']),'reference_answer_ids':answer,
             'reference_raw_margins':margins,'terminal_stop_token_id':stop,
             'stable_prefix_end_token':plan['stable_prefix_end_token'],'policy_hash':args.policy_hash,
             'policy_version':version,'attestation_mode':'actual-business-raw-answer-eos-path',
             'stable_content_hash':plan['stable_content_hash'],'layout_hash':plan['layout_hash'],
             'dependency_graph_hash':plan['dependency_graph_hash'],'cache_salt':cache_salt,
             'allow_certified_prefix_read':allow_prefix_read,'timeout_s':args.timeout}
    evidence={'prompt_ids_sha256':digest(forced),'request_hash_computed_before_dispatch':True,
              'reference_prompt_ids_sha256':business['prompt_ids_sha256'],
              'raw_all_tokens_margin_min':min(business['reference_margins']),
              'raw_answer_margin_min':min(margins),'raw_eos_margin':business['reference_margins'][-1]}
    return payload,evidence
