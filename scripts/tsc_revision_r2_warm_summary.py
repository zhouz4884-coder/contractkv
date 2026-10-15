"""Check matching-salt cache intervention and same-prompt behavioral effects."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_summarize import first_divergence


def warm_pair(raw,cold,warm,qualification,observation):
    if cold['prompt_token_ids']!=warm['prompt_token_ids']:
        raise ValueError('Cold/warm intervention changed prompt IDs')
    response=qualification['response']; passed=bool(response['certificate_issued'])
    hit=int(observation['prefix_hit_tokens'])
    return {'raw_score':raw['score'],'cold_score':cold['score'],'warm_score':warm['score'],
            'cold_quality_drop':raw['score']-cold['score'],'warm_quality_drop':raw['score']-warm['score'],
            'cold_warm_score_difference':cold['score']-warm['score'],
            'cold_warm_first_divergence':first_divergence(cold['output_token_ids'],warm['output_token_ids']),
            'cold_warm_prompt_ids_equal':True,'qualification_issued':passed,
            'qualified_committed_tokens':response.get('committed_tokens',0),
            'qualification_read_tokens':response.get('cached_prefix_read_tokens',0),
            'warm_prefix_hit_tokens':hit,'qualified_reuse_exercised':passed and hit>0,
            'raw_text':raw['text'],'cold_text':cold['text'],'warm_text':warm['text']}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    freeze=json.loads((a.root/'freeze.json').read_text(encoding='utf-8')); errors=[]; pairs=[]; cases=[]
    caseconfig=json.loads((a.root/'source_snapshot'/freeze['protocol']['case_config']).read_text(encoding='utf-8'))
    for item in freeze['files']:
        if hashlib.sha256((a.root/'source_snapshot'/item['path']).read_bytes()).hexdigest()!=item['sha256']: errors.append('snapshot:'+item['path'])
    sourcepath=a.root/'source_snapshot/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl'
    sources={r['revision_session_id']:r for line in sourcepath.read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
    for name in freeze['protocol']['selected_known_development_cases']:
        spec=next(c for c in caseconfig['cases'] if c['key']==name); source=sources[spec['source_session']]
        rawpath=a.root/name/'raw.jsonl'; closed=json.loads(rawpath.with_suffix('.summary.json').read_text(encoding='utf-8'))
        if not closed['execution_complete'] or hashlib.sha256(rawpath.read_bytes()).hexdigest()!=closed['raw_sha256']: errors.append(name+':completion_or_hash')
        rows=[json.loads(line) for line in rawpath.read_text(encoding='utf-8').splitlines() if line.strip()]
        events={r['request_id']:r for line in (a.root/name/'metrics.jsonl').read_text(encoding='utf-8').splitlines()
                if (r:=json.loads(line)).get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        bykey={(r['repeat'],r['role'],r.get('variant')):r for r in rows}
        if len(bykey)!=len(rows): errors.append(name+':duplicate_coordinate')
        request_ids=set()
        for r in rows:
            request_ids.add(r['request_id']); event=events.get(r['request_id'])
            ids=r['payload']['prompt_token_ids'] if r['role']=='qualification' else r['prompt_token_ids']
            if not event or int(event['prompt_tokens'])!=len(ids): errors.append(name+':metric_join')
            if r['role']=='qualification':
                result=r['response']; commit=int(result.get('committed_tokens',0))
                if (not result['certificate_issued'] and commit) or commit%16 or commit>r['payload']['stable_prefix_end_token']: errors.append(name+':publication_boundary')
                if result.get('cached_prefix_read_tokens',0)!=0: errors.append(name+':qualification_not_cold')
            else:
                response=r['response']; choice=response['choices'][0]
                if response.get('prompt_token_ids')!=ids or digest(ids)!=r['prompt_ids_sha256']: errors.append(name+':prompt_echo')
                if choice.get('token_ids')!=r['output_token_ids'] or response['usage']['completion_tokens']!=len(r['output_token_ids']): errors.append(name+':output_ids_usage')
                text=choice['message'].get('content') or ''
                score,_,_=standard_score(source['dataset'],source['task'],text,source.get('answer',''))
                if text!=r['text'] or score!=r['score']: errors.append(name+':score_text')
                if r['role'] in {'reference','raw','cold'} and int(event['prefix_hit_tokens'])!=0: errors.append(name+':cold_control_had_hit')
        if len(request_ids)!=len(rows): errors.append(name+':duplicate_request_id')
        group=[]
        for repeat in range(1,freeze['protocol']['sequential_repeats_per_fresh_server']+1):
            qualification=bykey[(repeat,'qualification',None)]
            for variant in ('witness','future'):
                raw=bykey[(repeat,'raw',variant)]; cold=bykey[(repeat,'cold',variant)]; warm=bykey[(repeat,'certified_salt',variant)]
                row={'case':name,'repeat':repeat,'variant':variant,**warm_pair(raw,cold,warm,qualification,events[warm['request_id']])}
                if row['qualification_issued'] and not row['qualified_reuse_exercised']: errors.append(name+':qualified_reuse_not_exercised')
                group.append(row); pairs.append(row)
        cases.append({'case':name,'free_generations':sum(r['role']!='qualification' for r in rows),
                      'qualifications':sum(r['role']=='qualification' for r in rows),'actual_metric_joins':len(rows),
                      'same_prompt_cold_warm_pairs':len(group),'qualified_reuse_pairs':sum(r['qualified_reuse_exercised'] for r in group),
                      'cold_material_drops':sum(r['cold_quality_drop']>.03 for r in group),
                      'warm_material_drops':sum(r['warm_quality_drop']>.03 for r in group),
                      'cold_warm_token_divergences':sum(r['cold_warm_first_divergence']!=-1 for r in group)})
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'pairs_v1.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0])); writer.writeheader(); writer.writerows(pairs)
    record={'schema_version':'tsc-r2.certified-warm-control-audit.v1','execution_complete':not errors,'errors':errors,'cases':cases,
            'selected_development_not_heldout':True,'performance_claim':False,
            'same_prompt_reuse_and_cold_order_counterbalanced_within_process':True}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record)); return 0 if not errors else 2


if __name__=='__main__': raise SystemExit(main())
