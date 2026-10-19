"""Independent request/trace, cache and first-divergence audit of known controls."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_r2_margin_smoke import forced_rows
from scripts.tsc_revision_r2_margin_policy import minimum_margin_gate
from scripts.tsc_revision_summarize import first_divergence


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def write(path,rows):
    with path.open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.root;frozen=json.loads((root/'freeze.json').read_text(encoding='utf-8'));spec=frozen['protocol']
    source=read(root/'source_snapshot/results/tsc_revision_r4/known_case_v1/sessions.jsonl')[0]
    expected=json.loads((root/'source_snapshot/results/tsc_revision_r4/known_case_v1/actual_prompt_ids_v1.json').read_text(encoding='utf-8'))['prompt_ids']
    errors=[];cases=[];free_rows=[];full_rows=[];pairs=[];qualifications=[]
    for item in frozen['files']:
        if sha(root/'source_snapshot'/item['path'])!=item['sha256']:errors.append('snapshot:'+item['path'])
    for lane in (0,1):
        directory=root/'cells'/f'qwen_gpu{lane}';rows=read(directory/'raw.jsonl')
        closed=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
        manifest=json.loads((directory/'runtime_manifest.json').read_text(encoding='utf-8'))
        if not closed['execution_complete'] or sha(directory/'raw.jsonl')!=closed['raw_sha256']:errors.append(f'GPU{lane}:incomplete/raw')
        if manifest['freeze_sha256']!=sha(root/'freeze.json') or str(manifest['declared_gpu_lane'])!=str(lane):errors.append(f'GPU{lane}:runtime')
        metrics={r['request_id']:r for r in read(directory/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        steps=read(directory/'execution_trace.jsonl');byid=defaultdict(list)
        for step in steps:
            for rid in step['request_ids']:byid[rid].append(step)
        verify={r['request_id']:r for r in read(directory/'verify_trace.jsonl')}
        before={r['request_id']:r for r in rows if r['role'] in ('free_request','full_request','verification_request')}
        free={(r['repeat'],r['nominal_HTTP_concurrency'],r['condition'],r['turn'],r['twin']):r for r in rows if r['role']=='free'}
        joined=[];warm_hits=[];cold_hits=[];observed_pair_active=[]
        for row in rows:
            if row['role'] not in ('free','full_logprob','verification_request'):continue
            engine_id=row['request_id']+('-0' if row['role']=='full_logprob' else '')
            ids=row['payload']['prompt_token_ids'] if row['role']=='verification_request' else row['prompt_token_ids']
            event=metrics.get(engine_id)
            if not event or event['prompt_tokens']!=len(ids):errors.append(f'{engine_id}:metric')
            if engine_id not in byid:errors.append(f'{engine_id}:execution_trace')
            joined.append(engine_id)
            if row['role']=='verification_request':continue
            response=row['response'];payload=row['request_payload'];request=before.get(payload['request_id'])
            if not request or request['payload']!=payload or not request['recorded_before_dispatch']:errors.append(f'{engine_id}:pre_request')
            sampled=[]
            for step in byid[engine_id]:sampled.extend(step['sampled_token_ids'][step['request_ids'].index(engine_id)])
            if sampled!=response['choices'][0]['token_ids']:errors.append(f'{engine_id}:sampled_trace_IDs')
            if row['role']=='full_logprob':
                witness=free[row['repeat'],row['nominal_HTTP_concurrency'],'cold-raw',1,0]
                answer=witness['output_token_ids'];prefix=expected[f'{row["layout"]}_t{row["turn"]}']
                if ids!=prefix+answer or forced_rows(response,prefix,answer[:-1],answer[-1])!=row['target_rows']:errors.append(f'{engine_id}:full_rows')
                target=row['target_rows'][24]
                full_rows.append({'gpu':lane,'repeat':row['repeat'],'HTTP_concurrency':row['nominal_HTTP_concurrency'],
                                  'layout':row['layout'],'turn':row['turn'],'first_divergence_position':24,
                                  'target_rank':target['rank'],'target_margin':target['margin'],
                                  'all_witness_tokens_rank_one':row['all_target_rank_one'],
                                  'actual_active_counts':json.dumps(sorted({s['active_input_requests'] for s in byid[engine_id]}))})
                continue
            score,_,_=standard_score(source['dataset'],source['task'],row['output_text'],source.get('answer',''))
            choice=response['choices'][0]
            if score!=row['task_score'] or choice['token_ids']!=row['output_token_ids'] or response.get('prompt_token_ids')!=ids or ids!=expected[f'{row["layout"]}_t{row["turn"]}']:
                errors.append(f'{engine_id}:actual_IDs_or_score')
            if choice['message']['content']!=row['output_text'] or response['usage']['completion_tokens']!=len(row['output_token_ids']):errors.append(f'{engine_id}:text_usage')
            if digest(ids)!=request['expected_prompt_ids_sha256']:errors.append(f'{engine_id}:pre_prompt_hash')
            active=sorted({s['active_input_requests'] for s in byid[engine_id]})
            if row['nominal_HTTP_concurrency']==1 and active!=[1]:errors.append(f'{engine_id}:singleton_active')
            if row['nominal_HTTP_concurrency']==2:observed_pair_active.extend(active)
            hit=event['prefix_hit_tokens'] if event else None
            if row['condition']=='warm' and row['certificate_was_issued']:
                warm_hits.append(hit)
                if not hit or hit<=0:errors.append(f'{engine_id}:missing_certified_hit')
            elif row['condition']!='warm':
                cold_hits.append(hit)
                if hit!=0:errors.append(f'{engine_id}:unexpected_cold_hit')
            free_rows.append({'gpu':lane,'request_id':row['request_id'],'repeat':row['repeat'],
                              'HTTP_concurrency':row['nominal_HTTP_concurrency'],'twin':row['twin'],
                              'layout':row['layout'],'turn':row['turn'],'condition':row['condition'],
                              'score':row['task_score'],'output_tokens':len(row['output_token_ids']),
                              'output_IDs_sha256':digest(row['output_token_ids']),'prefix_hit_tokens':hit,
                              'actual_active_counts':json.dumps(active)})
        if 2 not in observed_pair_active:errors.append(f'GPU{lane}:no_actual_concurrent_batch')
        for row in rows:
            if row['role']!='verification_response':continue
            rid=row['request_id'];request=before[rid]['payload'];response=row['response'];trace=verify.get(rid)
            if not trace:errors.append(rid+':missing_verify_trace');continue
            if trace['raw_reference_margins']!=request['reference_raw_margins'] or trace['reference_answer_ids']!=request['reference_answer_ids']:errors.append(rid+':reference_trace')
            gate=minimum_margin_gate(trace['raw_reference_margins'],trace['candidate_margins'],trace['terminal_stop_margin'],spec['raw_margin_floor'],spec['candidate_and_eos_floor'])
            if trace['pointwise_gate']!=gate or response['minimum_margin_guard_passed']!=gate['passed']:errors.append(rid+':margin_guard')
            ranks=all(x==1 for x in trace['candidate_ranks']) and trace['terminal_stop_rank']==1
            if response['certificate_issued'] and not (ranks and gate['passed']):errors.append(rid+':invalid_publication')
            if not response['certificate_issued'] and response['committed_tokens']:errors.append(rid+':rejected_publication')
            qualifications.append({'gpu':lane,'request_id':rid,'issued':response['certificate_issued'],
                                   'raw_min_margin':response['raw_margin_min'],'candidate_min_margin':response['candidate_margin_min'],
                                   'candidate_margin_at_position24':trace['candidate_margins'][24],
                                   'candidate_rank_at_position24':trace['candidate_ranks'][24],
                                   'committed_tokens':response['committed_tokens'],'qualification_cached_prefix_read_tokens':response['cached_prefix_read_tokens']})
        for (repeat,concurrency,condition,turn,twin),row in free.items():
            if condition=='cold-raw':continue
            baseline=free[repeat,concurrency,'cold-raw',turn,twin]
            witness=free[repeat,concurrency,'cold-raw',1,twin]
            cold=free[repeat,concurrency,'cold-candidate',turn,twin]
            pairs.append({'gpu':lane,'repeat':repeat,'HTTP_concurrency':concurrency,'twin':twin,'turn':turn,'condition':condition,
                          'raw_score':baseline['task_score'],'candidate_score':row['task_score'],
                          'quality_drop':baseline['task_score']-row['task_score'],
                          'first_divergence_from_raw':first_divergence(baseline['output_token_ids'],row['output_token_ids']),
                          'same_as_witness':row['output_token_ids']==witness['output_token_ids'],
                          'same_as_cold_candidate':row['output_token_ids']==cold['output_token_ids']})
        cases.append({'cell':directory.name,'actual_requests':len(joined),'unique_engine_IDs':len(set(joined)),
                      'free':sum(r['role']=='free' for r in rows),'full':sum(r['role']=='full_logprob' for r in rows),
                      'qualification':sum(r['role']=='verification_request' for r in rows),'actual_ModelRunner_steps':len(steps),
                      'all_actual_active_counts':sorted({r['active_input_requests'] for r in steps}),
                      'actual_qualified_warm_generations':len(warm_hits),'warm_hit_min':min(warm_hits) if warm_hits else None,
                      'warm_hit_max':max(warm_hits) if warm_hits else None,'cold_control_hits_zero':all(x==0 for x in cold_hits)})
    if any(x['actual_requests']!=84 or x['unique_engine_IDs']!=84 for x in cases):errors.append('request_coverage')
    a.output.mkdir(parents=True,exist_ok=True)
    for name,values in [('free_generations_v1.csv',free_rows),('first_divergence_logprobs_v1.csv',full_rows),('paired_outputs_v1.csv',pairs),('qualifications_v1.csv',qualifications)]:write(a.output/name,values)
    result={'schema_version':'tsc-r4.known-control-audit.v1','execution_complete':not errors,'errors':errors,'cases':cases,
            'actual_requests':sum(r['actual_requests'] for r in cases),'candidate_pairs':len(pairs),
            'candidate_material_drops':sum(r['quality_drop']>.03 for r in pairs),
            'cold_warm_output_differences':sum(r['condition']=='warm' and not r['same_as_cold_candidate'] for r in pairs),
            'selected_known_failure_not_unseen_efficacy':True,'performance_claim':False,'all_scope_quality_failures_retained':True}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0 if not errors else 2


if __name__=='__main__':raise SystemExit(main())
