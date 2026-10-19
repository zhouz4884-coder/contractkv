"""Separate selected-case diagnostic outcomes without changing frozen admission."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_r2_diagnose import forced_rows


def join_observation(row, events):
    full=row['role'].startswith('full_logprob_')
    # Frozen serving_completion.py line 194 uses one engine request per prompt.
    # This driver submits one token-ID prompt, hence exactly index zero.
    key=row['request_id']+'-0' if full else row['request_id']
    event=events.get(key)
    ids=row['payload']['prompt_token_ids'] if row['role'].startswith('internal_') else row['prompt_token_ids']
    if not event or int(event['prompt_tokens'])!=len(ids):
        raise ValueError('Missing exact engine ID/prompt-count observation: '+key)
    return {'api_request_id':row['request_id'],'engine_request_id':key,
            'mapping':'single_prompt_completions_engine_index_zero' if full else 'exact_id',
            'prompt_tokens':len(ids),'prefix_hit_tokens':int(event['prefix_hit_tokens'])}


def summarize(rows):
    free={(r['role'],r['repeat'],r['level']):r for r in rows if r['role'].startswith('free_')}
    witnesses={r['repeat']:r for r in rows if r['role']=='raw_witness'}
    full={(r['role'],r['repeat'],r['level']):r for r in rows if r['role'].startswith('full_logprob_')}
    internal={(r['role'],r['repeat'],r['level']):r for r in rows if r['role'].startswith('internal_')}
    result=[]
    for (role,repeat,level),row in sorted(free.items()):
        variant=role.removeprefix('free_'); raw=free[(role,repeat,'L0')]
        witness=witnesses[repeat]; control=full[('full_logprob_'+variant,repeat,level)]
        check=internal.get(('internal_'+variant,repeat,level))
        if control['prompt_token_ids']!=row['prompt_token_ids']+witness['output_token_ids']:
            raise ValueError('Full-logprob and free prompts/reference IDs differ')
        response=check['response'] if check else {}
        result.append({'repeat':repeat,'variant':variant,'level':level,
                       'prompt_ids_sha256':row['prompt_ids_sha256'],
                       'raw_score':raw['score'],'candidate_score':row['score'],
                       'quality_drop':raw['score']-row['score'],
                       'fresh_witness_score':witness['score'],
                       'raw_ids_equal_witness':raw['output_token_ids']==witness['output_token_ids'],
                       'candidate_ids_equal_witness':row['output_token_ids']==witness['output_token_ids'],
                       'candidate_ids_equal_same_input_raw':row['output_token_ids']==raw['output_token_ids'],
                       'full_rank_one':control['rank_one_answer_and_stop'],
                       'full_margin_min':min(r['margin'] for r in control['target_rows']),
                       'full_candidate_q05':control['candidate_margin_q05'],
                       'internal_certificate':response.get('certificate_issued','not_applicable'),
                       'internal_read_tokens':response.get('cached_prefix_read_tokens','not_applicable'),
                       'internal_candidate_q05':response.get('candidate_margin_q05','not_applicable'),
                       'full_internal_decision_disagreement':(control['rank_one_answer_and_stop']!=response['certificate_issued']) if check else 'not_applicable',
                       'full_pass_but_free_differs':control['rank_one_answer_and_stop'] and row['output_token_ids']!=witness['output_token_ids'],
                       'raw_text':raw['text'],'candidate_text':row['text'],'witness_text':witness['text']})
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    freeze=json.loads((a.root/'freeze.json').read_text()); errors=[]; pairs=[]; per_case=[]
    for item in freeze['files']:
        path=a.root/'source_snapshot'/item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']: errors.append('snapshot:'+item['path'])
    for spec in freeze['protocol']['cases']:
        name=spec['key']; path=a.root/name/'raw.jsonl'
        closed=json.loads(path.with_suffix('.summary.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=closed['raw_sha256']: errors.append(name+':raw_hash')
        rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        source_path=a.root/'source_snapshot/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl'
        source=next(r for line in source_path.read_text().splitlines() if (r:=json.loads(line))['revision_session_id']==spec['source_session'])
        events={r['request_id']:r for line in (a.root/name/'metrics.jsonl').read_text().splitlines()
                if (r:=json.loads(line)).get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        joined=[]
        for row in rows:
            try: joined.append(join_observation(row,events))
            except (ValueError,KeyError) as exc: errors.append(name+':'+str(exc))
        if len({r['engine_request_id'] for r in joined})!=len(rows): errors.append(name+':duplicate_or_missing_engine_identity')
        for field,expected in [('free_generations','expected_free_generations'),('full_logprob_calls','expected_full_logprob_calls'),('internal_calls','expected_internal_calls')]:
            actual=sum(r['role'].startswith(('raw_witness','free_')) for r in rows) if field=='free_generations' else sum(r['role'].startswith('full_logprob_' if field=='full_logprob_calls' else 'internal_') for r in rows)
            if actual!=freeze['protocol'][expected][name] or actual!=closed[field]: errors.append(name+':'+field)
        group=summarize(rows)
        for r in group: pairs.append({'case':name,**r})
        free=[r for r in rows if r['role'].startswith(('raw_witness','free_'))]
        identity=defaultdict(set)
        for r in free:
            identity[(r['role'],r['level'])].add(r['prompt_ids_sha256'])
            response=r['response']; choice=response['choices'][0]
            if not r['prompt_ids_echo_equal'] or response.get('prompt_token_ids')!=r['prompt_token_ids'] or digest(r['prompt_token_ids'])!=r['prompt_ids_sha256']: errors.append(name+':prompt_echo')
            if choice.get('token_ids')!=r['output_token_ids'] or response['usage']['completion_tokens']!=len(r['output_token_ids']): errors.append(name+':output_ids_or_usage')
            score,_,_=standard_score(source['dataset'],source['task'],r['text'],source.get('answer',''))
            if score!=r['score']: errors.append(name+':score_recalculation')
        witnesses={r['repeat']:r for r in free if r['role']=='raw_witness'}
        for r in rows:
            if r['role'].startswith('full_logprob_'):
                witness=witnesses[r['repeat']]['output_token_ids']
                ids=r['prompt_token_ids'][:-len(witness)]
                actual=forced_rows(r['response'],ids,witness[:-1],witness[-1])
                if actual!=r['target_rows'] or r['rank_one_answer_and_stop']!=all(x['rank']==1 for x in actual): errors.append(name+':full_target_rows')
            if r['role'].startswith('internal_'):
                response=r['response']; commit=int(response.get('committed_tokens',0))
                if (not response.get('certificate_issued') and commit) or commit>r['payload']['stable_prefix_end_token'] or commit%16: errors.append(name+':publication_boundary')
        if any(len(values)!=1 for values in identity.values()): errors.append(name+':repeat_prompt_identity')
        actual_reads=[r['internal_read_tokens'] for r in group if r['level']!='L0']
        if any(x!=0 for x in actual_reads): errors.append(name+':unexpected_internal_read')
        prefix=[r['prefix_hit_tokens'] for r in joined]
        future_raw=[r for r in free if r['role']=='free_future' and r['level']=='L0']
        per_case.append({'case':name,'free_generations':closed['free_generations'],
                         'full_logprob_calls':closed['full_logprob_calls'],'internal_calls':closed['internal_calls'],
                         'frozen_driver_execution_complete':closed['execution_complete'],
                         'postexecution_actual_metric_joins':len(joined),
                         'same_input_raw_future_unique_outputs':len({tuple(r['output_token_ids']) for r in future_raw}),
                         'all_repeated_prompt_identities_equal':all(len(v)==1 for v in identity.values()),
                         'observed_max_generic_or_business_prefix_hit':max(prefix) if prefix else 'unavailable',
                         'candidate_layout_material_drops':sum(r['quality_drop']>.03 and r['level']!='L0' for r in group),
                         'full_internal_decision_disagreements':sum(r['full_internal_decision_disagreement'] is True for r in group),
                         'full_rank_one_but_free_different':sum(r['full_pass_but_free_differs'] for r in group),
                         'all_internal_read_tokens_zero':all(x==0 for x in actual_reads)})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,records in [('pairs_v2.csv',pairs),('summary_v2.csv',per_case)]:
        with (a.output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    record={'schema_version':'tsc-r2.selected-case-diagnostic-audit.v2','execution_complete':not errors,
            'errors':errors,'cases':per_case,'selected_known_development_not_heldout':True,
            'no_performance_or_unique_cause_claim':True,'phase1_data_not_modified':True,
            'frozen_driver_join_error_retained':'The frozen driver uses API response IDs for all metric lookups; completions engine IDs append -0 for this single prompt. Its execution_complete=false remains unchanged. This additional audit joins the exact source-defined engine IDs and checks prompt counts for all requests, including internal calls.',
            'method_comparison_limit':'Generic full logprobs and chunked internal checks have different arithmetic shapes; disagreement alone does not establish an indexing bug.'}
    (a.output/'completion_audit_v2.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))
    return 0 if not errors else 2


if __name__=='__main__':
    raise SystemExit(main())
