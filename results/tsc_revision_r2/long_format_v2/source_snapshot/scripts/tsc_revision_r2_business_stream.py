"""Real streaming business responses with mandatory prompt/output ID evidence."""
import json
import time
import urllib.request

from scripts.phase17_live_common import digest
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.tsc_revision_live import generation_payload


class StreamEvidenceError(ValueError):
    def __init__(self,message,evidence):
        super().__init__(message)
        self.evidence=evidence


def consume_stream(lines,request_id,started,witness=False):
    first=last=None; prompt_ids=None; ids=[]; lp=[]; chunks=[]; usage={}; finish=''; done=False; actual_id=None
    def evidence():
        ended=time.perf_counter(); text=''.join(chunks)
        return {'success':False,'request_id':actual_id or request_id,'output_text':text,'output_token_ids':ids,
                'token_ids_available':bool(ids),'prompt_token_ids':prompt_ids,
                'prompt_ids_available':prompt_ids is not None,'prompt_ids_sha256':digest(prompt_ids) if prompt_ids is not None else None,
                'prompt_hash_encoding':'scripts.phase17_live_common.digest(JSON array of integer IDs)',
                'finish_reason':finish,'completion_tokens':usage.get('completion_tokens'),'prompt_tokens':usage.get('prompt_tokens'),
                'ttft_ms':(first-started)*1000 if first is not None else 0,'latency_ms':(ended-started)*1000,
                'tpot_ms':(last-first)*1000/max(len(ids)-1,1) if first is not None and last is not None else 0,
                'first_time':first,'end_time':ended,'stream_done':done,'witness_requested':witness,
                'error_type':'none','error_message':''}
    try:
        for line in lines:
            value=line.decode('utf-8').strip() if isinstance(line,bytes) else line.strip()
            if not value.startswith('data:'): continue
            data=value[5:].strip()
            if data=='[DONE]': done=True; break
            item=json.loads(data)
            if item.get('id'):
                if actual_id is not None and actual_id!=item['id']: raise ValueError('Response ID changed during stream')
                actual_id=item['id']
            echo=item.get('prompt_token_ids')
            if echo is not None:
                if not isinstance(echo,list) or not echo or any(type(x) is not int or x<0 for x in echo):
                    raise ValueError('Invalid server prompt ID array')
                if prompt_ids is not None and prompt_ids!=echo: raise ValueError('Prompt IDs changed during stream')
                prompt_ids=echo
            usage=item.get('usage') or usage
            for choice in item.get('choices',[]):
                content=(choice.get('delta') or {}).get('content') or ''; delta_ids=choice.get('token_ids') or []
                if any(type(x) is not int or x<0 for x in delta_ids): raise ValueError('Invalid output token ID')
                now=time.perf_counter()
                if content: first=now if first is None else first; chunks.append(content)
                if delta_ids: last=now; ids.extend(delta_ids)
                lp.extend((choice.get('logprobs') or {}).get('content') or [])
                finish=choice.get('finish_reason') or finish
        if not done or first is None or finish not in {'stop','length'}: raise ValueError('Incomplete content/finish/DONE stream')
        if actual_id is None or not ids: raise ValueError('Actual response/output token IDs unavailable')
        if prompt_ids is None: raise ValueError('Complete prompt IDs unavailable; token-count inference is forbidden')
        if usage.get('prompt_tokens')!=len(prompt_ids) or usage.get('completion_tokens')!=len(ids):
            raise ValueError('Actual token-ID/usage mismatch or missing usage')
    except Exception as exc:
        result=evidence(); result.update(error_type=type(exc).__name__,error_message=str(exc))
        raise StreamEvidenceError(str(exc),result) from exc
    result=evidence(); result['success']=True
    if witness:
        body={'choices':[{'token_ids':ids,'logprobs':{'content':lp},'finish_reason':finish,
                          'message':{'content':result['output_text']}}]}
        try:
            _,margins,_,_=extract_raw_tokens_and_margins(body)
            result.update(reference_margins=margins,witness_available=True,
                          raw_generation_logprob_content=lp,
                          raw_all_tokens_margin_min=min(margins),raw_stop_margin=margins[-1])
        except Exception as exc:
            result.update(witness_available=False,witness_failure=str(exc),raw_generation_logprob_content=lp)
    return result


def business_generate(args,messages,budget,rid,witness=False,salt=None):
    payload={**generation_payload(args.model,messages,budget,14014),'request_id':rid,
             'stream':True,'stream_options':{'include_usage':True}}
    if witness: payload.update(logprobs=True,top_logprobs=2)
    if salt is not None: payload['cache_salt']=salt
    request=urllib.request.Request(args.base_url.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),
                                   headers={'Content-Type':'application/json'},method='POST')
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=args.timeout) as response:
            return consume_stream(response,rid,started,witness)
    except StreamEvidenceError as exc:
        return exc.evidence
    except Exception as exc:
        return {'success':False,'request_id':rid,'output_text':'','output_token_ids':[],'token_ids_available':False,
                'prompt_token_ids':None,'prompt_ids_available':False,'prompt_ids_sha256':None,
                'finish_reason':'error','completion_tokens':0,'ttft_ms':0,'latency_ms':(time.perf_counter()-started)*1000,
                'tpot_ms':0,'first_time':None,'end_time':time.perf_counter(),'witness_available':False,
                'error_type':type(exc).__name__,'error_message':str(exc)}
