"""Audit original score, strict format, actual horizon and pointwise long admission."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.tsc_revision_r2_long_format import scores
from scripts.tsc_revision_live import load_metrics
from scripts.phase17_live_common import digest
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.tsc_revision_r1r_output_horizon import horizon_measures

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def wire_schema(text,size,start):
    try:value=json.loads(text)
    except (ValueError,TypeError):return False
    return isinstance(value,list) and all(type(x) is int for x in value) and value==list(range(start,start+size))

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    freeze=json.loads((a.root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol'];catalog=json.loads((a.root/'source_snapshot'/config.get('selected_catalog','configs/tsc_revision_r2_selected_catalog_v1.json')).read_text(encoding='utf-8'))
    errors=[];missing=[];cells=[];pairs=[];lengths=[];decisions=[];assignments={};exits={}
    if (a.root/'execution_dispatch_freeze_v1.json').exists():
        events=read(a.root/'execution_dispatch_v1/execution_events.jsonl') if (a.root/'execution_dispatch_v1/execution_events.jsonl').exists() else []
        assignments={r['cell']:r for r in events if r['event']=='prospective_cell_assignment'}
        exits={r['cell']:r for r in events if r['event']=='cell_process_exit'}
    for model,repeat in itertools.product(config['models'],range(1,config['fresh_repeats']+1)):
        cell=f'{config.get("cell_prefix","long-format")}_{model}_r{repeat}';base=a.root/'cells'/cell
        if not (base/'raw.summary.json').exists():missing.append(cell);continue
        rows=read(base/'raw.jsonl');closed=json.loads((base/'raw.summary.json').read_text(encoding='utf-8'));events=load_metrics(base/'metrics.jsonl')
        if not closed['execution_complete'] or sha(base/'raw.jsonl')!=closed['raw_sha256']:errors.append(cell+':completion/hash')
        manifest=json.loads((base/'runtime_manifest.json').read_text(encoding='utf-8'))
        if manifest['freeze_sha256']!=sha(a.root/'freeze.json'):errors.append(cell+':runtimefreeze')
        if (a.root/'execution_dispatch_freeze_v1.json').exists():
            assignment=assignments.get(cell);exited=exits.get(cell)
            if not assignment or int(manifest['declared_gpu_lane'])!=assignment['gpu_lane'] or not exited or exited['returncode']!=0:errors.append(cell+':prospective GPU dispatch/exit')
        expected=set(itertools.product(config['array_sizes'],config['conditions']));references={};requests={};registered={};actual=0;pub=0
        for r in rows:
            key=(r['array_size'],r['condition'])
            if r['row_type']=='reference':references[key]=r
            elif r['row_type']=='verification_request':requests[key]=r
            elif r['row_type']=='verification':registered[key]=r
        if set(references)!=expected or set(registered)!=expected:errors.append(cell+':condition coverage')
        seen=set()
        def generation(row,key,role):
            nonlocal actual
            actual+=1;event=events.get(row['request_id']);ids=row['prompt_token_ids']
            if row['request_id'] in seen:errors.append(cell+':duplicate request')
            seen.add(row['request_id'])
            if not row['success'] or row['completion_tokens']!=len(row['output_token_ids']) or row['prompt_tokens']!=len(ids) or row['prompt_ids_sha256']!=digest(ids) or not event or event['prompt_tokens']!=len(ids):errors.append(cell+':business ID/metric')
            result=scores(row['output_text'],key[0],config['array_start'])
            lengths.append({'cell':cell,'model':model,'repeat':repeat,'array_size':key[0],'condition':key[1],'role':role,'actual_output_tokens':len(row['output_token_ids']),'finish':row['finish_reason'],'canonical_integer_schema_after_think_strip':result['strict_plain_json_integer_sequence'],'raw_wire_integer_schema':wire_schema(row['output_text'],key[0],config['array_start']),'primary128_score':result['original_128_score']['complete_correct_array'] if key[0]==128 else None,'separate160_score':result['separate_160_task_score'],'actual_gt512':len(row['output_token_ids'])>512,'prefix_hit_tokens':event['prefix_hit_tokens'] if event else None})
            return result
        for key,reference in references.items():
            result=generation(reference,key,'reference')
            if reference.get('witness_available'):
                body={'choices':[{'token_ids':reference['output_token_ids'],'finish_reason':reference['finish_reason'],
                     'message':{'content':reference['output_text']},'logprobs':{'content':reference['raw_generation_logprob_content']}}]}
                _,margins,_,_=extract_raw_tokens_and_margins(body)
                if margins!=reference['reference_margins']:errors.append(cell+':actual reference LP recomputation')
            if any(reference[k]!=v for k,v in result.items()):errors.append(cell+':reference score')
            decision=registered[key];req=requests.get(key)
            if req:
                payload=req['payload'];event=events.get(req['request_id'])
                if req['prompt_ids_sha256']!=digest(payload['prompt_token_ids']) or not req['request_hash_computed_before_dispatch'] or not event or event['prompt_tokens']!=len(payload['prompt_token_ids']):errors.append(cell+':verification ID/hash/metric')
                if payload['prompt_token_ids'][payload['verify_start_token']:]!=reference['output_token_ids'] or payload['reference_raw_margins']!=reference['reference_margins'][:-1]:errors.append(cell+':forced raw path')
            if decision['certificate_issued']:
                if req is None or reference['finish_reason']!='stop' or min(reference['reference_margins'])<catalog['raw_token_margin_floor'] or decision['candidate_margin_min']<catalog['candidate_token_margin_floor'] or decision['terminal_stop_margin']<catalog['candidate_token_margin_floor'] or not decision['minimum_margin_guard_passed']:errors.append(cell+':admission')
            else:pub+=int(decision['committed_tokens'])
            decisions.append({'cell':cell,'model':model,'repeat':repeat,'array_size':key[0],'condition':key[1],'raw_tokens':len(reference['output_token_ids']),'raw_finish':reference['finish_reason'],'canonical_integer_schema_after_think_strip':result['strict_plain_json_integer_sequence'],'raw_wire_integer_schema':wire_schema(reference['output_text'],key[0],config['array_start']),'issued':decision['certificate_issued'],'raw_min':decision['raw_full_margin_min'],'candidate_min':decision.get('candidate_margin_min'),'candidate_eos':decision.get('terminal_stop_margin'),'reason':decision['failure_reason']})
        coordinates=[]
        for row in rows:
            if row['row_type']!='paired_future':continue
            key=(row['array_size'],row['condition']);coordinates.append((*key,row['turn']))
            rawscore=generation(row['raw'],key,'raw_future');policyscore=generation(row['policy'],key,'policy_future')
            if rawscore!=row['raw_score'] or policyscore!=row['policy_score'] or row['compiled']!=registered[key]['certificate_issued'] or row['first_divergence']!=first_divergence(row['raw']['output_token_ids'],row['policy']['output_token_ids']):errors.append(cell+':paired route/score')
            if row['compiled']:
                payload=requests[key]['payload'];commit=registered[key]['committed_tokens']
                if row['policy']['prompt_token_ids'][:commit]!=payload['prompt_token_ids'][:commit] or events[row['policy']['request_id']]['prefix_hit_tokens']<commit:errors.append(cell+':actual qualified reuse')
            wire_raw=wire_schema(row['raw']['output_text'],key[0],config['array_start']);wire_policy=wire_schema(row['policy']['output_text'],key[0],config['array_start'])
            pairs.append({'cell':cell,'model':model,'repeat':repeat,'array_size':key[0],'condition':key[1],'turn':row['turn'],'compiled':row['compiled'],'raw_actual_tokens':len(row['raw']['output_token_ids']),'policy_actual_tokens':len(row['policy']['output_token_ids']),'raw_finish':row['raw']['finish_reason'],'policy_finish':row['policy']['finish_reason'],'raw_canonical_integer_schema':rawscore['strict_plain_json_integer_sequence'],'policy_canonical_integer_schema':policyscore['strict_plain_json_integer_sequence'],'raw_wire_integer_schema':wire_raw,'policy_wire_integer_schema':wire_policy,'canonical_quality_drop':int(rawscore['strict_plain_json_integer_sequence'])-int(policyscore['strict_plain_json_integer_sequence']),'raw_wire_quality_drop':int(wire_raw)-int(wire_policy),'first_divergence':row['first_divergence'],**horizon_measures(len(references[key]['output_token_ids']),row['policy']['output_token_ids'],references[key]['output_token_ids'])})
        if set(coordinates)!={(n,c,t) for n,c in expected for t in range(1,config['futures_per_condition']+1)} or len(coordinates)!=8 or actual!=20 or pub:errors.append(cell+':counts/publication')
        control=read(base/'pre_measurement_full_ids.jsonl')
        if len(control)!=21:errors.append(cell+':control complete logging')
        for r in control:
            if r['row_type']=='control_verification_request' and r['prompt_ids_sha256']!=digest(r['payload']['prompt_token_ids']):errors.append(cell+':control requesthash')
            if r['row_type']=='control_raw_generation' and (r['prompt_ids_sha256']!=digest(r['prompt_token_ids']) or r['response']['prompt_token_ids']!=r['prompt_token_ids']):errors.append(cell+':control rawhash')
        if 'native_template_options' in config:
            options=read(base/'native_template_options.jsonl')
            actual_business=[r for r in rows if r['row_type']=='reference']+[r[k] for r in rows if r['row_type']=='paired_future' for k in ('raw','policy')]
            indexed={r['actual_request_id']:r for r in options}
            if len(indexed)!=20:errors.append(cell+':native option trace count')
            expected_options={r['request_id']:config['native_template_options'][r['condition']] for r in rows if r['row_type']=='reference'}
            for r in rows:
                if r['row_type']=='paired_future':
                    for role in ('raw','policy'):expected_options[r[role]['request_id']]=config['native_template_options'][r['condition']]
            for r in actual_business:
                trace=indexed.get(r['request_id'])
                if not trace or trace['chat_template_kwargs']!=expected_options[r['request_id']] or trace['prompt_ids_sha256']!=r['prompt_ids_sha256'] or trace['actual_output_ids_sha256']!=digest(r['output_token_ids']):errors.append(cell+':native option actual identity')
        cells.append({'cell':cell,'actual_generations':actual,'paired_futures':len(coordinates),'rejected_published_tokens':pub})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,values in [('actual_lengths_and_scores_v1.csv',lengths),('paired_futures_v1.csv',pairs),('admissions_v1.csv',decisions)]:
        if values:write(a.output/name,values)
    result={'schema_version':'tsc-r2.long-format-audit.v1','execution_complete':not errors and not missing and len(cells)==len(config['models'])*config['fresh_repeats'],'errors':sorted(set(errors)),'missing_cells':missing,'cases':cells,'actual_generations':sum(c['actual_generations'] for c in cells),'paired_futures':len(pairs),'original128_scoring_imported_unchanged':True,'observed_array_sizes':config['array_sizes'],'original128_task_executed':128 in config['array_sizes'],'larger_content_tasks_are_separate_conditions':True,'frozen_field_named_strict_plain_json_integer_sequence_strips_model_think_tags':True,'raw_wire_json_reported_separately_without_think_stripping':True,'experimental_execution_is_not_all_models_positive_success':True}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ('cases','missing_cells')}));return 0 if result['execution_complete'] or a.allow_partial else 2

if __name__=='__main__':raise SystemExit(main())
