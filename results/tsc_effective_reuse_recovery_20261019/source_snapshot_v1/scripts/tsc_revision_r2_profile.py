"""Independent development level controls for a later single-shot policy."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_live import FROZEN_LEVELS,read_jsonl,load_metrics
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_r2_candidate_plan import candidate_plan,verification_request
from scripts.phase17_live_common import api_root,digest,post_json
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase20a_official_quality import standard_score

MODELS={'qwen':('qwen3-8b','Qwen3-8B'),'mistral':('mistral7b','Mistral-7B-Instruct-v0.3'),
        'llama':('llama31-8b','Llama-3.1-8B-Instruct')}


def main():
    p=argparse.ArgumentParser()
    for key in ('protocol','profile-config','sessions','output','metrics'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--model-key',choices=MODELS,required=True);p.add_argument('--base-url',required=True)
    p.add_argument('--policy-hash',required=True);a=p.parse_args()
    config=json.loads(a.profile_config.read_text(encoding='utf-8'))
    if hashlib.sha256(a.sessions.read_bytes()).hexdigest()!=config['development_sessions_sha256']:raise ValueError('Development input changed')
    if a.output.exists():raise RuntimeError('Preserve profile attempt')
    samples=read_jsonl(a.sessions)
    if len(samples)!=config['development_sources']:raise ValueError('Development source count')
    served,identity=MODELS[a.model_key]
    args=SimpleNamespace(protocol=json.loads(a.protocol.read_text(encoding='utf-8')),model=served,model_identity=identity,
                         policy_hash=a.policy_hash,base_url=a.base_url,timeout=600,experiment='free-generation',output_budget=0)
    a.output.parent.mkdir(parents=True,exist_ok=True);records=[];slots=issued=0
    def append(row):
        records.append(row)
        with a.output.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    def prepared(sample,tenant,turn):
        clone=deepcopy(sample);clone['shared_template_id']=clone['revision_session_id'];clone['revision_session_id']+=f'-tenant{tenant:02d}'
        return prepare(args,clone,turn)
    def pair(sample,point,role,query,level,salt,qualified=None):
        jobs=[]
        for tenant in range(point['first_tenant'],point['first_tenant']+2):
            pr=prepared(sample,tenant,point['turn']);case,messages,maximum,budget,scope=pr
            if scope!=query:raise ValueError('Metadata stress point changed the exact query')
            if level!='L0':
                order=layout_for_level(case,level,args.protocol['layout']['ladder'])['topological_order']
                messages=[messages[0],{'role':'user','content':_ordered_text(order,case['segments'])}]
            rid=f'r2-profile-{a.model_key}-{sample["revision_session_id"]}-q{point["turn"]%3}-{role}-{level}-t{point["turn"]}-n{tenant}'
            jobs.append((tenant,pr,messages,rid))
        def call(job):
            started=time.perf_counter()
            result=business_generate(args,job[2],job[1][3],job[3],role=='reference',salt)
            return result,started
        with ThreadPoolExecutor(max_workers=2) as pool:outputs=list(pool.map(call,jobs))
        result=[]
        for (tenant,pr,messages,rid),(out,started) in zip(jobs,outputs):
            score,metric,source=standard_score(sample['dataset'],sample['task'],out['output_text'],sample.get('answer',''))
            row={'row_type':'generation','role':role,'model':identity,'source_group':sample['revision_source_group'],
                 'session_id':sample['revision_session_id'],'family':sample['revision_family'],'tenant':tenant,
                 'turn':point['turn'],'query_scope':query,'level':level,'messages':messages,
                 'request_payload_id':rid,'cache_salt':salt,'qualification_request_id':qualified,
                 'client_call_started':started,'task_score':score,'task_metric':metric,'metric_source':source,**out}
            append(row);result.append(row)
            if not out['success'] or not out['prompt_ids_available'] or not out['token_ids_available']:
                raise RuntimeError('Real streaming generation/evidence failed; partial records preserved')
        return result
    for index,sample in enumerate(samples):
        maximum=FROZEN_LEVELS[identity][sample['revision_family']]
        if maximum=='L0':
            append({'row_type':'static_ineligible','source_group':sample['revision_source_group'],
                    'family':sample['revision_family'],'model':identity,'reason':'inherited_family_L0'})
            continue
        levels=[f'L{i}' for i in range(1,int(maximum[1:])+1)]
        for probe in config['query_probes']:
            first=prepared(sample,0,probe['witness_turn']);scope=first[4]
            raw_salt=a.policy_hash+':'+sample['revision_session_id']+':raw'
            references=pair(sample,{'turn':probe['witness_turn'],'first_tenant':0},'reference',scope,'L0',raw_salt)
            reference=references[0];qualifications={}
            order=levels if (index+probe['witness_turn'])%2==0 else list(reversed(levels))
            for level in order:
                slots+=1;rid=f'r2-profile-{a.model_key}-{sample["revision_session_id"]}-q{probe["witness_turn"]}-{level}-verify'
                salt=a.policy_hash+':'+sample['revision_session_id']+':'+scope+':'+level
                complete_start=time.perf_counter()
                try:
                    plan=candidate_plan(args,first,level)
                    payload,evidence=verification_request(args,plan,reference,rid,salt,False,'r2-independent-development-level-v1')
                except ValueError as exc:
                    append({'row_type':'level_slot','source_group':sample['revision_source_group'],'family':sample['revision_family'],
                            'model':identity,'query_scope':scope,'witness_turn':probe['witness_turn'],'level':level,
                            'attempted':False,'reason':str(exc),'reference_request_id':reference['request_id']})
                    qualifications[level]=None;continue
                append({'row_type':'qualification_request','request_id':rid,'payload':payload,**evidence})
                started=time.perf_counter()
                try:response=post_json(api_root(a.base_url)+'/v1/contractkv/verify',payload,600)
                except Exception as exc:
                    append({'row_type':'qualification_error','request_id':rid,'error':repr(exc)})
                    raise
                row={'row_type':'level_slot','source_group':sample['revision_source_group'],'family':sample['revision_family'],
                     'model':identity,'query_scope':scope,'witness_turn':probe['witness_turn'],'level':level,
                     'attempted':True,'request_id':response['request_id'],'reference_request_id':reference['request_id'],
                     'verification_http_ms':(time.perf_counter()-started)*1000,
                     'complete_qualification_ms':(time.perf_counter()-complete_start)*1000,
                     'plan':plan,'payload':payload,'request_evidence':evidence,'response':response}
                append(row);qualifications[level]=row
                issued+=response['certificate_issued']
            for point in probe['future_points']:
                pair(sample,point,'raw_future',scope,'L0',raw_salt)
                for level in order:
                    qualification=qualifications[level]
                    if qualification and qualification['response']['certificate_issued']:
                        pair(sample,point,'candidate_future',scope,level,qualification['payload']['cache_salt'],qualification['request_id'])
        print(json.dumps({'model':a.model_key,'source_index':index,'level_slots':slots,
                          'actual_generations':sum(r['row_type']=='generation' for r in records),'issued':issued}),flush=True)
    time.sleep(.5);events=load_metrics(a.metrics);joins=[];failures=[]
    for row in records:
        if row['row_type']=='generation':ids=row['prompt_token_ids']
        elif row['row_type']=='level_slot' and row['attempted']:ids=row['payload']['prompt_token_ids']
        else:continue
        event=events.get(row['request_id']);matched=bool(event) and event['prompt_tokens']==len(ids)
        if not matched:failures.append(row['request_id'])
        joins.append({'request_id':row['request_id'],'role':row.get('role','qualification'),'matched':matched,
                      'prefix_hit_tokens':event.get('prefix_hit_tokens') if event else None,
                      'scheduled_tokens':event.get('scheduled_tokens') if event else None,
                      'scheduler_running_requests':event.get('scheduler_running_requests') if event else None})
    generations=sum(r['row_type']=='generation' for r in records)
    complete=slots==config['expected_level_slots'][a.model_key] and not failures
    result={'schema_version':'tsc-r2.development-level-profile.v1','model':a.model_key,'execution_complete':complete,
            'level_slots':slots,'actual_generations':generations,'issued_qualifications':issued,'request_metric_joins':joins,
            'metric_join_failures':failures,'raw_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
            'candidate_generation_count_is_outcome_dependent':True,'no_generated_candidate_for_rejected_qualification':True,
            'not_a_production_multi_level_policy_rollout':True,'not_serving_efficacy_evidence':True}
    a.output.with_suffix('.summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='request_metric_joins'}),flush=True)
    return 0 if complete else 2


if __name__=='__main__':raise SystemExit(main())
