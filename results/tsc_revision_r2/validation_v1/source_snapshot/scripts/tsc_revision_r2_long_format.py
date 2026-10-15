"""Explicit-format and separately declared larger-content long-output controls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_r1r_long_horizon import score as original_score
from scripts.phase17_live_common import api_root,digest,post_json,tokenize
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.contractkv_pstp import lcp_length
from scripts.tsc_revision_live import load_metrics
from scripts.tsc_revision_summarize import first_divergence

def scores(text,size,start):
    clean=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    try:value=json.loads(clean)
    except (ValueError,TypeError):value=None
    strict=isinstance(value,list) and all(type(x) is int for x in value) and value==list(range(start,start+size))
    return {'original_128_score':original_score(text) if size==128 else None,'strict_plain_json_integer_sequence':strict,
            'separate_160_task_score':strict if size==160 else None}

def main():
    p=argparse.ArgumentParser()
    for name in ('protocol','catalog','output','metrics'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('model','base-url','policy-hash'):p.add_argument('--'+name,required=True)
    p.add_argument('--repeat',type=int,required=True);p.add_argument('--timeout',type=float,default=600);a=p.parse_args()
    config=json.loads(a.protocol.read_text(encoding='utf-8'));catalog=json.loads(a.catalog.read_text(encoding='utf-8'))
    if a.output.exists():raise RuntimeError('Preserve every long-format attempt')
    a.output.parent.mkdir(parents=True,exist_ok=True);rows=[]
    def emit(row):
        rows.append(row)
        with a.output.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    for size in config['array_sizes']:
        for condition in config['conditions']:
            system={'role':'system','content':config['original_system' if condition=='original-instruction' else 'explicit_system']}
            stable='[STABLE_DOCUMENT]\n'+' '.join('reference'+str(i) for i in range(500))+'\n'
            start=config['array_start'];end=start+size-1
            query=f'[QUERY]\nReturn a JSON array containing every integer from {start} through {end} inclusive, in increasing order. Include all {size} integers. Output only the complete JSON array, without commentary.'
            def messages(turn,compiled):
                obs=f'[PRIVATE_TOOL_METADATA] turn={turn}; status=ready; no additional answer evidence.\n'
                return [system,{'role':'user','content':(stable+obs if compiled else obs+stable)+query}]
            stem=f'r2-format-{a.model}-r{a.repeat}-{condition}-n{size}';salt=a.policy_hash+':'+stem
            coordinates={'model':a.model,'repeat':a.repeat,'condition':condition,'array_size':size,'cap':config['output_cap']}
            reference=business_generate(a,messages(0,False),config['output_cap'],stem+'-reference',True)
            emit({'row_type':'reference',**coordinates,'messages':messages(0,False),**reference,**scores(reference['output_text'],size,start)})
            if not reference['success']:raise RuntimeError('Long raw generation failed')
            decision={'certificate_issued':False,'committed_tokens':0,'failure_reason':'uncertifiable_reference','request_id':None}
            if reference.get('witness_available') and reference['finish_reason']=='stop' and min(reference['reference_margins'])>=catalog['raw_token_margin_floor']:
                answer,margins,stop=split_terminal_stop_token(reference['output_token_ids'],reference['reference_margins'],reference['finish_reason'])
                ids=tokenize(a.base_url,a.model,messages(0,True),True,a.timeout)
                prefix=tokenize(a.base_url,a.model,[system,{'role':'user','content':stable.rstrip()}],False,a.timeout)
                stable_end=lcp_length(prefix,ids)
                payload={'request_id':stem+'-verify','txn_id':stem+'-txn','prompt_token_ids':ids+answer+[stop],
                    'verify_start_token':len(ids),'reference_answer_ids':answer,'reference_raw_margins':margins,'terminal_stop_token_id':stop,
                    'stable_prefix_end_token':stable_end,'policy_hash':a.policy_hash,'policy_version':'r2-explicit-format-long-v1',
                    'attestation_mode':'actual-raw-business-answer-eos-path','stable_content_hash':digest(ids[:stable_end]),
                    'layout_hash':digest(messages(0,True)),'dependency_graph_hash':digest(['STABLE','PRIVATE_METADATA','QUERY']),
                    'cache_salt':salt,'allow_certified_prefix_read':True,'timeout_s':a.timeout}
                emit({'row_type':'verification_request',**coordinates,'request_id':payload['request_id'],'payload':payload,
                      'prompt_ids_sha256':digest(payload['prompt_token_ids']),'request_hash_computed_before_dispatch':True})
                decision=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,a.timeout)
            elif reference.get('witness_available'):
                decision['failure_reason']='raw_answer_or_eos_margin_below_floor' if reference['finish_reason']=='stop' else 'length_stop_no_certificate'
            emit({'row_type':'verification',**coordinates,'raw_full_margin_min':min(reference['reference_margins']) if reference.get('witness_available') else None,**decision})
            if not decision['certificate_issued'] and decision['committed_tokens']:raise RuntimeError('Rejected long qualification published')
            for turn in range(1,config['futures_per_condition']+1):
                raw=business_generate(a,messages(turn,False),config['output_cap'],stem+f'-raw-t{turn}')
                admitted=decision['certificate_issued'];policy=business_generate(a,messages(turn,admitted),config['output_cap'],stem+f'-policy-t{turn}',salt=salt if admitted else None)
                emit({'row_type':'paired_future',**coordinates,'turn':turn,'compiled':admitted,'raw':raw,'policy':policy,
                      'raw_score':scores(raw['output_text'],size,start),'policy_score':scores(policy['output_text'],size,start),
                      'first_divergence':first_divergence(raw['output_token_ids'],policy['output_token_ids'])})
                if not raw['success'] or not policy['success']:raise RuntimeError('Long actual generation failed')
    time.sleep(.5);events=load_metrics(a.metrics);errors=[];actual=[]
    for row in rows:
        if row['row_type']=='reference':actual.append(row)
        elif row['row_type']=='paired_future':actual.extend((row['raw'],row['policy']))
        elif row['row_type']=='verification_request':
            event=events.get(row['request_id'])
            if not event or event['prompt_tokens']!=len(row['payload']['prompt_token_ids']):errors.append('verification_metric')
    for row in actual:
        event=events.get(row['request_id'])
        if not event or event['prompt_tokens']!=len(row['prompt_token_ids']) or row['prompt_ids_sha256']!=digest(row['prompt_token_ids']):errors.append('business_identity_or_metric')
    result={'schema_version':'tsc-r2.long-format-cell.v1','execution_complete':not errors and len(actual)==20,'errors':errors,'actual_generations':len(actual),'paired_futures':sum(r['row_type']=='paired_future' for r in rows),'raw_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'conditions':[{'array_size':r['array_size'],'condition':r['condition'],'issued':r['certificate_issued'],'reason':r['failure_reason'],'raw_full_margin_min':r['raw_full_margin_min']} for r in rows if r['row_type']=='verification']}
    a.output.with_suffix('.summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));return 0 if result['execution_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
