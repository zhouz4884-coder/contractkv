"""Audit both members of every paired-tenant cache-state control."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_batch_reuse import twin_payload
from scripts.tsc_revision_r2_warm_summary import warm_pair
from scripts.tsc_revision_live import generation_payload
from scripts.phase20a_official_quality import standard_score


def read(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(Path(__file__).with_name('tsc_revision_r2_warm_summary.py')),
                    '--root',str(a.root),'--output',str(a.output/'primary')],check=True)
    primary_audit=json.loads((a.output/'primary/completion_audit_v1.json').read_text(encoding='utf-8'))
    freeze=json.loads((a.root/'freeze.json').read_text(encoding='utf-8')); config=freeze['protocol']
    specs=json.loads((a.root/'source_snapshot'/config['case_config']).read_text(encoding='utf-8'))['cases']
    protocol=json.loads((a.root/'source_snapshot/configs/tsc_revision_r1r_validation_protocol_v1.json').read_text(encoding='utf-8'))
    sources={r['revision_session_id']:r for r in read(a.root/'source_snapshot/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl')}
    errors=[]; twin_pairs=[]; cases=[]
    for name in config['selected_known_development_cases']:
        spec=next(s for s in specs if s['key']==name); source=sources[spec['source_session']]
        rows=read(a.root/name/'raw.jsonl'); twins=read(a.root/name/'twins.jsonl')
        closed=json.loads((a.root/name/'batch_summary.json').read_text(encoding='utf-8'))
        if not closed['execution_complete']: errors.append(name+':batch_not_complete')
        if hashlib.sha256((a.root/name/'twins.jsonl').read_bytes()).hexdigest()!=closed['twins_sha256']: errors.append(name+':twin_hash')
        primary={r['request_id']:r for r in rows}; converted={}; matched_ids=set(primary)
        events={r['request_id']:r for r in read(a.root/name/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        qualifiers={r['repeat']:r for r in rows if r['role']=='qualification'}
        for twin in twins:
            # Frozen serving_chat assigns the exact chatcmpl- prefix to this payload ID.
            parent=primary.get('chatcmpl-'+twin['primary_request_payload_id'])
            if parent is None: raise ValueError('Twin has no exact primary response ID')
            budget=protocol['free_generation']['budgets'][source['revision_family']]
            expected=twin_payload({**generation_payload(spec['served_model'],parent['messages'],budget,14014),
                                   'request_id':twin['primary_request_payload_id'],'cache_salt':parent['cache_salt'],
                                   'logprobs':True,'top_logprobs':2})
            if expected!=twin['twin_payload']: errors.append(name+':uncontrolled_twin_payload_change')
            response=twin['response']; ids=twin['expected_twin_prompt_ids']; choice=response['choices'][0]
            if response.get('prompt_token_ids')!=ids: errors.append(name+':twin_prompt_echo')
            if choice.get('token_ids')!=twin['output_token_ids'] or response['usage']['completion_tokens']!=len(twin['output_token_ids']): errors.append(name+':twin_output_usage')
            text=choice['message'].get('content') or ''; score,_,_=standard_score(source['dataset'],source['task'],text,source.get('answer',''))
            if text!=twin['text'] or score!=twin['score']: errors.append(name+':twin_score')
            overlap=max(twin['primary_interval']['begin'],twin['twin_interval']['begin'])<min(twin['primary_interval']['end'],twin['twin_interval']['end'])
            if not overlap or not twin['http_intervals_overlap']: errors.append(name+':pair_HTTP_not_overlapping')
            event=events.get(twin['request_id'])
            if not event or int(event['prompt_tokens'])!=len(ids): raise ValueError('Missing exact twin metrics')
            if parent['role'] in {'reference','raw','cold'} and int(event['prefix_hit_tokens'])!=0: errors.append(name+':twin_cold_had_hit')
            if twin['request_id'] in matched_ids: errors.append(name+':duplicate_engine_ID')
            matched_ids.add(twin['request_id'])
            key=(parent['repeat'],parent['role'],parent['variant'])
            if key in converted: errors.append(name+':duplicate_twin_coordinate')
            converted[key]={'request_id':twin['request_id'],'prompt_token_ids':ids,'output_token_ids':twin['output_token_ids'],
                            'score':score,'text':text}
        group=[]
        for repeat in range(1,config['sequential_repeats_per_fresh_server']+1):
            for variant in ('witness','future'):
                raw=converted[(repeat,'raw',variant)]; cold=converted[(repeat,'cold',variant)]; warm=converted[(repeat,'certified_salt',variant)]
                row={'case':name,'repeat':repeat,'variant':variant,'lane':'twin',
                     **warm_pair(raw,cold,warm,qualifiers[repeat],events[warm['request_id']])}
                if row['qualification_issued'] and not row['qualified_reuse_exercised']: errors.append(name+':twin_qualified_reuse_not_exercised')
                group.append(row); twin_pairs.append(row)
        max_active=max(int(r['scheduler_running_requests']) for r in events.values())
        if max_active<2: errors.append(name+':two_active_requests_not_observed')
        if len(twins)!=config['expected_twin_free_generations_per_model'] or len(matched_ids)!=config['expected_total_engine_requests_per_model']: errors.append(name+':actual_counts')
        parent_case=next(c for c in primary_audit['cases'] if c['case']==name)
        cases.append({'case':name,'primary_free_generations':parent_case['free_generations'],'twin_free_generations':len(twins),
                      'qualifications':len(qualifiers),'actual_engine_metric_joins':len(matched_ids),
                      'observed_max_scheduler_active_requests':max_active,'primary_control':parent_case,
                      'twin_qualified_reuse_pairs':sum(r['qualified_reuse_exercised'] for r in group),
                      'twin_cold_material_drops':sum(r['cold_quality_drop']>.03 for r in group),
                      'twin_warm_material_drops':sum(r['warm_quality_drop']>.03 for r in group),
                      'twin_cold_warm_token_divergences':sum(r['cold_warm_first_divergence']!=-1 for r in group)})
    with (a.output/'twin_pairs_v1.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(twin_pairs[0])); writer.writeheader(); writer.writerows(twin_pairs)
    record={'schema_version':'tsc-r2.paired-tenant-cache-control-audit.v1','execution_complete':not errors,'errors':errors,
            'cases':cases,'selected_development_not_heldout':True,'performance_claim':False,
            'scheduler_two_active_is_not_per_step_kernel_batch_telemetry':True,
            'controlled_adaptation_not_full_original_streaming_workload_replay':True}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record)); return 0 if not errors else 2


if __name__=='__main__': raise SystemExit(main())
