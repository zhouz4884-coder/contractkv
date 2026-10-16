"""Stream the real business response and optionally retain its witness LPs."""
import json
import time
import urllib.request

from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.tsc_revision_live import generation_payload


def business_generate(args, messages, budget, rid, witness=False, salt=None):
    payload = {**generation_payload(args.model,messages,budget,14014), "request_id":rid,
               "stream":True,"stream_options":{"include_usage":True}}
    if witness: payload.update(logprobs=True,top_logprobs=2)
    if salt is not None: payload["cache_salt"] = salt
    request = urllib.request.Request(args.base_url.rstrip("/")+"/chat/completions",data=json.dumps(payload).encode(),
                                     headers={"Content-Type":"application/json"},method="POST")
    started = time.perf_counter(); first=last=None; ids=[]; lp=[]; text=[]; usage={}; finish=""; actual_id=rid; done=False
    try:
        with urllib.request.urlopen(request,timeout=args.timeout) as response:
            for line in response:
                value=line.decode(errors="replace").strip()
                if not value.startswith("data:"): continue
                data=value[5:].strip()
                if data=="[DONE]": done=True; break
                item=json.loads(data); actual_id=item.get("id",actual_id); usage=item.get("usage") or usage
                for choice in item.get("choices",[]):
                    content=(choice.get("delta") or {}).get("content") or ""
                    delta_ids=choice.get("token_ids") or []
                    now=time.perf_counter()
                    if content: first=now if first is None else first; text.append(content)
                    if delta_ids: last=now; ids.extend(int(i) for i in delta_ids)
                    lp.extend((choice.get("logprobs") or {}).get("content") or [])
                    finish=choice.get("finish_reason") or finish
        ended=time.perf_counter(); output="".join(text)
        result={"success":done and first is not None and finish in {"stop","length"},"request_id":actual_id,
                "output_text":output,"output_token_ids":ids,"token_ids_available":bool(ids),"finish_reason":finish,
                "completion_tokens":int(usage.get("completion_tokens",len(ids))),"prompt_tokens":usage.get("prompt_tokens","unavailable"),
                "ttft_ms":(first-started)*1000 if first else 0,"latency_ms":(ended-started)*1000,
                "tpot_ms":(last-first)*1000/max(len(ids)-1,1) if first and last else 0,
                "first_time":first,"end_time":ended,"error_type":"none","error_message":""}
        if witness:
            body={"choices":[{"token_ids":ids,"logprobs":{"content":lp},"finish_reason":finish,"message":{"content":output}}]}
            try:
                _, margins, _, _=extract_raw_tokens_and_margins(body)
                result["reference_margins"] = margins
                result["witness_available"] = True
            except Exception as exc:
                result["witness_available"] = False
                result["witness_failure"] = str(exc)
        return result
    except Exception as exc:
        return {"success":False,"request_id":rid,"output_text":"","output_token_ids":[],"token_ids_available":False,
                "finish_reason":"error","completion_tokens":0,"ttft_ms":0,"latency_ms":(time.perf_counter()-started)*1000,
                "tpot_ms":0,"first_time":None,"end_time":time.perf_counter(),"witness_available":False,
                "error_type":type(exc).__name__,"error_message":str(exc)}
