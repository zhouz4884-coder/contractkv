"""Controlled natural-stop long outputs; never a benchmark quality surrogate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_business_stream import business_generate
from scripts.phase17_live_common import api_root,digest,post_json,tokenize
from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.tsc_revision_summarize import first_divergence


def score(text):
    clean=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    clean=re.sub(r'^```(?:json)?\s*|\s*```$','',clean).strip()
    try: values=json.loads(clean)
    except (ValueError,TypeError): return {'complete_correct_array':False,'valid_array':False}
    return {'complete_correct_array':values==list(range(1001,1129)),'valid_array':isinstance(values,list)}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--protocol',type=Path,required=True); p.add_argument('--model',required=True)
    p.add_argument('--base-url',required=True); p.add_argument('--repeat',type=int,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--policy-hash',required=True); p.add_argument('--timeout',type=float,default=600); a=p.parse_args()
    if a.output.exists(): raise RuntimeError('Preserve previous long-horizon attempt')
    protocol=json.loads(a.protocol.read_text()); records=[]
    system={'role':'system','content':'/no_think Follow the request exactly. Complete the entire requested array.'}
    stable='[STABLE_DOCUMENT]\n'+' '.join('reference'+str(i) for i in range(500))+'\n'
    query='[QUERY]\n'+protocol['query']
    def messages(turn,compiled):
        obs=f'[PRIVATE_TOOL_METADATA] turn={turn}; status=ready; no additional answer evidence.\n'
        return [system,{'role':'user','content':(stable+obs if compiled else obs+stable)+query}]
    def emit(row):
        records.append(row); a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    for cap in protocol['output_caps']:
        stem=f'long-{a.model}-r{a.repeat}-cap{cap}'; salt=a.policy_hash+':'+stem
        reference=business_generate(a,messages(0,False),cap,stem+'-reference',True)
        emit({'row_type':'reference','model':a.model,'repeat':a.repeat,'cap':cap,**reference,**score(reference['output_text'])})
        decision={'certificate_issued':False,'committed_tokens':0,'failure_reason':'uncertifiable_reference'}
        try:
            answer,margins,stop=split_terminal_stop_token(reference['output_token_ids'],reference['reference_margins'],reference['finish_reason'])
            candidate=messages(0,True); ids=tokenize(a.base_url,a.model,candidate,True,a.timeout)
            prefix=tokenize(a.base_url,a.model,[system,{'role':'user','content':stable.rstrip()}],False,a.timeout)
            stable_end=lcp_length(prefix,ids)
            payload={'request_id':stem+'-verify','txn_id':stem+'-txn','prompt_token_ids':ids+answer+[stop],
                     'verify_start_token':len(ids),'reference_answer_ids':answer,'reference_raw_margins':margins,
                     'terminal_stop_token_id':stop,'stable_prefix_end_token':stable_end,'policy_hash':a.policy_hash,
                     'policy_version':'r1r-controlled-long-v1','attestation_mode':'strict-raw-answer-eos',
                     'stable_content_hash':digest(ids[:stable_end]),'layout_hash':digest(candidate),
                     'dependency_graph_hash':digest(['STABLE','PRIVATE_METADATA','QUERY']),
                     'cache_salt':salt,'allow_certified_prefix_read':True,'timeout_s':a.timeout}
            decision=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,a.timeout)
        except Exception as exc:
            decision['failure_reason']=str(exc)
        emit({'row_type':'verification','model':a.model,'repeat':a.repeat,'cap':cap,
              'reference_finish':reference['finish_reason'],'reference_tokens':len(reference['output_token_ids']),**decision})
        for turn in range(1,protocol['futures_per_cap']+1):
            raw=business_generate(a,messages(turn,False),cap,stem+f'-raw-t{turn}')
            admitted=decision['certificate_issued']
            policy=business_generate(a,messages(turn,admitted),cap,stem+f'-policy-t{turn}',salt=salt if admitted else None)
            emit({'row_type':'paired_future','model':a.model,'repeat':a.repeat,'cap':cap,'turn':turn,
                  'compiled':admitted,'raw':raw,'policy':policy,'raw_score':score(raw['output_text']),
                  'policy_score':score(policy['output_text']),
                  'first_diverging_token':first_divergence(raw['output_token_ids'],policy['output_token_ids'])})
    summary={'schema_version':'tsc-r1r.controlled-long-result.v1','model':a.model,'repeat':a.repeat,
             'raw_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'paired_futures':sum(r['row_type']=='paired_future' for r in records),
             'rejected_published_tokens':sum(r.get('committed_tokens',0) for r in records if r['row_type']=='verification' and not r['certificate_issued']),
             'length_reference_admissions':sum(r['certificate_issued'] and r['reference_finish']=='length' for r in records if r['row_type']=='verification')}
    business=[r for r in records if r['row_type']=='reference']
    business += [r[k] for r in records if r['row_type']=='paired_future' for k in ('raw','policy')]
    summary['successful_actual_generations']=sum(r['success'] and r['token_ids_available'] for r in business)
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary),flush=True)
    return 0 if summary['paired_futures']==6 and summary['successful_actual_generations']==15 and not summary['rejected_published_tokens'] and not summary['length_reference_admissions'] else 2


if __name__=='__main__': raise SystemExit(main())
