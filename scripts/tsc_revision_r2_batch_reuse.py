"""Controlled two-tenant adaptation of the unchanged warm-reuse driver."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
import time

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r2_warm_reuse as base


def twin_payload(payload):
    twin=deepcopy(payload); changes=0
    pattern=r'(\[PRIVATE_TOOL_OBS\] revision_session=[A-Za-z0-9_-]+-tenant)(\d{2})(; turn=)'
    def replace(match):
        return match[1]+f'{int(match[2])+1:02d}'+match[3]
    for message in twin['messages']:
        message['content'],count=re.subn(pattern,replace,message['content'])
        changes+=count
    if changes!=1: raise ValueError('Exactly one controlled tenant metadata field required')
    twin['request_id']+='-twin'
    if not payload['request_id'].endswith('-certified_salt'):
        twin['cache_salt']+='-twin'
    return twin


def main():
    parser=argparse.ArgumentParser(add_help=False)
    for key in ('output','metrics','sessions','config'): parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--case',required=True); parser.add_argument('--base-url',required=True)
    args,_=parser.parse_known_args()
    config=json.loads(args.config.read_text(encoding='utf-8'))
    caseconfig=json.loads(Path(config['case_config']).read_text(encoding='utf-8'))
    spec=next(c for c in caseconfig['cases'] if c['key']==args.case)
    source=next(s for s in base.read_jsonl(args.sessions) if s['revision_session_id']==spec['source_session'])
    path=args.output.with_name('twins.jsonl')
    if path.exists() or args.output.exists(): raise RuntimeError('Preserve existing batch attempt')
    path.parent.mkdir(parents=True,exist_ok=True); twins=[]; original_http=base.post_json
    def send(url,payload,timeout):
        begin=time.perf_counter()
        try:
            response=original_http(url,payload,timeout)
            return {'begin':begin,'end':time.perf_counter(),'response':response}
        except Exception as exc: return {'begin':begin,'end':time.perf_counter(),'error':repr(exc)}
    def paired(url,payload,timeout):
        if not url.endswith('/chat/completions'): return original_http(url,payload,timeout)
        twin=twin_payload(payload)
        ids=base.tokenize(args.base_url,spec['served_model'],twin['messages'],True,600)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(send,url,payload,timeout); second=pool.submit(send,url,twin,timeout)
            primary,other=first.result(),second.result()
        row={'primary_request_payload_id':payload['request_id'],'twin_payload':twin,'expected_twin_prompt_ids':ids,
             'primary_interval':{k:primary.get(k) for k in ('begin','end')},
             'twin_interval':{k:other.get(k) for k in ('begin','end')},'primary_error':primary.get('error'),
             'twin_error':other.get('error'),'response':other.get('response')}
        row['http_intervals_overlap']=max(primary['begin'],other['begin'])<min(primary['end'],other['end'])
        if 'response' in other:
            try:
                response=other['response']; base.check_prompt_ids(response,ids,True)
                choice=response['choices'][0]; text=choice['message'].get('content') or ''
                if len(choice['token_ids'])!=response['usage']['completion_tokens'] or choice['finish_reason'] not in {'stop','length'}: raise ValueError('Twin actual output IDs/usage incomplete')
                score,metric,metric_source=base.standard_score(source['dataset'],source['task'],text,source.get('answer',''))
                row.update(request_id=response['id'],output_token_ids=choice['token_ids'],text=text,
                           score=score,metric=metric,metric_source=metric_source)
            except Exception as exc: row['twin_error']=repr(exc)
        twins.append(row)
        with path.open('a',encoding='utf-8') as stream: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        if row['primary_error'] or row['twin_error']: raise RuntimeError('Paired HTTP/identity failure; responses retained')
        return primary['response']
    base.post_json=paired
    try: status=base.main()
    finally: base.post_json=original_http
    events=base.load_metrics(args.metrics); observations=[]
    for row in twins:
        event=events.get(row['request_id'])
        if not event or event['prompt_tokens']!=len(row['expected_twin_prompt_ids']): raise ValueError('Twin metric identity/count missing')
        observations.append({'request_id':row['request_id'],'prefix_hit_tokens':event['prefix_hit_tokens'],
                             'scheduler_running_requests':event['scheduler_running_requests']})
    max_active=max(r['scheduler_running_requests'] for r in events.values())
    complete=(status==0 and len(twins)==config['expected_twin_free_generations_per_model']
              and max_active>=2 and all(r['http_intervals_overlap'] for r in twins))
    result={'schema_version':'tsc-r2.batch-reuse-adapter.v1','execution_complete':complete,
            'primary_driver_status':status,'twin_free_generations':len(twins),'twin_metric_joins':len(observations),
            'twin_observations':observations,'twins_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'all_http_pairs_overlap':all(r['http_intervals_overlap'] for r in twins),'observed_max_scheduler_active_requests':max_active,
            'selected_development_not_heldout':True,'performance_claim':False,
            'scheduler_active_two_is_not_per_step_kernel_batch_telemetry':True}
    args.output.with_name('batch_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True); return 0 if complete else 2


if __name__=='__main__': raise SystemExit(main())
