"""Audit actual pointwise rejection, model-step shapes and first-divergence LPs."""
from collections import defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_diagnose_summary import join_observation
from scripts.tsc_revision_r2_margin_smoke import forced_rows
from scripts.tsc_revision_r2_margin_policy import minimum_margin_gate
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_summarize import first_divergence


def read(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def original_failure(project,spec):
    repeat=3 if spec['key']=='llama' else 1
    base=project/'results/tsc_revision_r1r/validation'
    with (base/'summary/launcher_gpu_assignment_v1.csv').open(encoding='utf-8',newline='') as stream:
        lanes={r['cell']:int(r['gpu_lane']) for r in csv.DictReader(stream)}
    result={'case':spec['key'],'historical_failed_compiled_LPs_unavailable':True,
            'historical_actual_prompt_IDs_unavailable':True}
    for policy in ('raw-order','query-prefix'):
        cell=f'template-fanout_{spec["key"]}_{policy}_r{repeat}'
        directory=base/'cells'/cell; path=directory/'raw.jsonl'
        closed=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
        if sha(path)!=closed['raw_file_sha256']: raise ValueError('Original failure evidence changed')
        rows=read(path); sid=spec['source_session']+f'-tenant{spec["future_tenant"]:02d}'
        row=next(r for r in rows if r['row_type']=='future' and r['session_id']==sid and r['turn_id']==spec['future_turn'])
        result[policy]={'cell':cell,'source_raw_sha256':sha(path),'gpu_lane':lanes[cell],
                        'output_token_ids':row['output_token_ids'],'text':row['output_text'],'score':row['task_score']}
        if policy=='query-prefix':
            witness=next(r for r in rows if r['row_type'] in {'warm','future'} and r['scope_first_raw_business'] and r['query_scope']==row['query_scope'])
            result['business_witness_ids']=witness['output_token_ids']
    result['first_divergence']=first_divergence(result['raw-order']['output_token_ids'],result['query-prefix']['output_token_ids'])
    if result['first_divergence'] not in (12,22): raise ValueError('Preidentified historical divergence changed')
    return result


def shape_set(events):
    keys=('active_input_requests','scheduled_token_count','padded_input_token_count','hidden_states_shape','sampling_logits_shape','prompt_logprob_shapes','cudagraph_mode')
    return sorted({json.dumps({k:e[k] for k in keys},sort_keys=True) for e in events})


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); root=a.root.resolve(); project=root.parents[2]
    freeze=json.loads((root/'freeze.json').read_text(encoding='utf-8')); config=freeze['protocol']
    sources={r['revision_session_id']:r for r in read(root/'source_snapshot/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl')}
    errors=[]; cases=[]; first_rows=[]; references=[]; identities=[]
    for item in freeze['files']:
        if sha(root/'source_snapshot'/item['path'])!=item['sha256']: errors.append('snapshot:'+item['path'])
    for spec in config['cases']:
        name=spec['key']; base=root/name; rows=read(base/'raw.jsonl'); source=sources[spec['source_session']]
        closed=json.loads((base/'raw.summary.json').read_text(encoding='utf-8'))
        if not closed['execution_complete'] or sha(base/'raw.jsonl')!=closed['raw_sha256']: errors.append(name+':completion_or_hash')
        events={r['request_id']:r for r in read(base/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        steps=read(base/'execution_trace.jsonl'); byid=defaultdict(list)
        for event in steps:
            for rid in event['request_ids']: byid[rid].append(event)
            if event['active_input_requests']!=1: errors.append(name+':actual_model_batch_not_one')
        verify={r['request_id']:r for r in read(base/'verify_trace.jsonl')}
        witness={r['repeat']:r for r in rows if r['role']=='raw_witness'}
        full={(r['repeat'],r['role'],r['level']):r for r in rows if r['role'].startswith('full_logprob_')}
        free={(r['repeat'],r['role'],r['level']):r for r in rows if r['role'].startswith('free_')}
        internal={(r['repeat'],r['role'],r['level']):r for r in rows if r['role'].startswith('internal_')}
        rejected=issued=pub=guarded=rank_only=0; matched=[]
        for row in rows:
            joined=join_observation(row,events); eid=joined['engine_request_id']; matched.append(eid)
            ids=row['payload']['prompt_token_ids'] if row['role'].startswith('internal_') else row['prompt_token_ids']
            identities.append({'case':name,'role':row['role'],'request_id':row['request_id'],'engine_request_id':eid,
                               'prompt_ids_sha256':digest(ids),'hash_is_derived_from_immutable_request_ID_array':True})
            if eid not in byid: errors.append(name+':missing_actual_execution_trace')
            if row['role'].startswith(('raw_witness','free_')):
                response=row['response']; choice=response['choices'][0]
                if response.get('prompt_token_ids')!=ids or choice['token_ids']!=row['output_token_ids'] or response['usage']['completion_tokens']!=len(row['output_token_ids']): errors.append(name+':actual_ID_usage')
                score,_,_=standard_score(source['dataset'],source['task'],row['text'],source.get('answer',''))
                if score!=row['score'] or row['text']!=(choice['message'].get('content') or ''): errors.append(name+':score')
            if row['role'].startswith('full_logprob_'):
                ref=witness[row['repeat']]['output_token_ids']; prefix=ids[:-len(ref)]
                if forced_rows(row['response'],prefix,ref[:-1],ref[-1])!=row['target_rows']: errors.append(name+':full_rows')
            if not row['role'].startswith('internal_'):
                sampled=[]
                for step in byid[eid]:
                    index=step['request_ids'].index(eid)
                    sampled.extend(step['sampled_token_ids'][index])
                if sampled!=row['response']['choices'][0]['token_ids']: errors.append(name+':sample_trace_vs_returned_IDs')
                continue
            result=row['response']; trace=verify.get(row['request_id'])
            if not trace: errors.append(name+':missing_verify_trace'); continue
            if trace['raw_reference_margins']!=row['payload']['reference_raw_margins'] or trace['reference_answer_ids']!=row['payload']['reference_answer_ids']: errors.append(name+':reference_trace')
            gate=minimum_margin_gate(trace['raw_reference_margins'],trace['candidate_margins'],trace['terminal_stop_margin'],config['min_raw_token_margin'],config['min_candidate_token_margin'])
            if gate!=trace['pointwise_gate'] or result['minimum_margin_guard_passed']!=gate['passed']: errors.append(name+':pointwise_gate')
            for field in ('raw_margin_min','candidate_margin_min','raw_margin_min_index','candidate_margin_min_index'):
                if result[field]!=gate[field]: errors.append(name+':minimum_stat')
            path_ok=all(r==1 for r in trace['candidate_ranks']) and trace['terminal_stop_rank']==1
            rank_only+=path_ok; guarded+=path_ok and gate['passed']
            issued+=result['certificate_issued']; rejected+=not result['certificate_issued']
            if result['certificate_issued'] and not (path_ok and gate['passed']): errors.append(name+':invalid_admission')
            if not result['certificate_issued']: pub+=int(result['committed_tokens'])
        if len(set(matched))!=len(rows) or pub: errors.append(name+':identity_or_rejected_publication')
        for role,key in [('free_','expected_free_generations'),('full_logprob_','expected_full_logprob_calls'),('internal_','expected_internal_calls')]:
            actual=sum(r['role'].startswith(role) or (role=='free_' and r['role']=='raw_witness') for r in rows)
            if actual!=config[key][name]: errors.append(name+':role_count')
        prior=original_failure(project,spec); references.append(prior); position=prior['first_divergence']
        manifest=json.loads((base/'runtime_manifest.json').read_text(encoding='utf-8'))
        for repeat in witness:
            for variant in ('witness','future'):
                lp=full[(repeat,'full_logprob_'+variant,'L2')]; decision=internal[(repeat,'internal_'+variant,'L2')]
                generated=free[(repeat,'free_'+variant,'L2')]; raw=free[(repeat,'free_'+variant,'L0')]
                trace=verify[decision['request_id']]; entry=lp['target_rows'][position]
                sorted_lp=sorted((float(v['logprob']) for v in entry['entry'].values()),reverse=True)
                first_rows.append({'case':name,'repeat':repeat,'variant':variant,'original_divergence_index':position,
                    'current_gpu_lane':manifest['declared_gpu_lane'],'original_compiled_gpu_lane':prior['query-prefix']['gpu_lane'],
                    'current_witness_IDs_match_original_witness':witness[repeat]['output_token_ids']==prior['business_witness_ids'],
                    'current_free_output_matches_original_bad_output':generated['output_token_ids']==prior['query-prefix']['output_token_ids'],
                    'current_raw_compiled_histories_match_before_index':raw['output_token_ids'][:position]==generated['output_token_ids'][:position],
                    'full_target_rank':entry['rank'],'full_target_margin':entry['margin'],'full_top1_top2_margin':sorted_lp[0]-sorted_lp[1],
                    'internal_target_rank':trace['candidate_ranks'][position],'internal_target_margin':trace['candidate_margins'][position],
                    'actual_raw_decode_margin':raw['raw_margins'][position],'actual_candidate_decode_margin':generated['raw_margins'][position],
                    'raw_answer_min':decision['response']['raw_margin_min'],'candidate_answer_min':decision['response']['candidate_margin_min'],
                    'certificate_issued':decision['response']['certificate_issued'],
                    'full_execution_shapes':json.dumps(shape_set(byid[lp['request_id']+'-0'])),
                    'internal_execution_shapes':json.dumps(shape_set(byid[decision['request_id']])),
                    'free_execution_shapes':json.dumps(shape_set(byid[generated['request_id']]))})
        cases.append({'case':name,'actual_requests':len(rows),'metric_and_execution_ID_joins':len(matched),
                      'model_runner_steps':len(steps),'actual_active_request_counts':sorted({e['active_input_requests'] for e in steps}),
                      'rank_only_path_passes':rank_only,'rank_and_pointwise_passes':guarded,'issued':issued,'rejected':rejected,
                      'rejected_published_tokens':pub,'current_gpu_lane':manifest['declared_gpu_lane'],
                      'original_compiled_gpu_lane':prior['query-prefix']['gpu_lane']})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,records in [('first_divergence_v1.csv',first_rows),('request_prompt_hashes_v1.csv',identities)]:
        with (a.output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    (a.output/'original_failure_reference_v1.json').write_text(json.dumps(references,indent=2)+'\n',encoding='utf-8')
    result={'schema_version':'tsc-r2.pointwise-preflight-audit.v1','execution_complete':not errors,'errors':errors,'cases':cases,
            'preflight_not_final_threshold_selection_or_heldout_efficacy':True,
            'historical_failed_compiled_token_LPs_unavailable':True,
            'fixed_current_device_and_model_steps_are_not_claimed_to_reproduce_every_historical_execution_condition':True}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result)); return 0 if not errors else 2


if __name__=='__main__': raise SystemExit(main())
