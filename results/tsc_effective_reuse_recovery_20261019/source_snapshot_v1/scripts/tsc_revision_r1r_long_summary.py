"""Actual length/stop/quality and metric audit for controlled long outputs."""
import argparse
from collections import defaultdict
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write
from scripts.tsc_revision_live import load_metrics
from scripts.tsc_revision_r1r_long_horizon import score
from scripts.tsc_revision_summarize import first_divergence
from scripts.tsc_revision_r1r_output_horizon import horizon_measures


def schema_diagnostic(text,finish):
    """Post hoc description only; never changes the frozen primary predicate."""
    if finish=='length': return {'category':'budget_truncation','detail':'','output_prefix':text[:80]}
    if score(text)['complete_correct_array']: return {'category':'frozen_predicate_pass','detail':'','output_prefix':text[:80]}
    clean=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    clean=re.sub(r'^```(?:json)?\s*|\s*```$','',clean).strip()
    try: values=json.loads(clean)
    except ValueError as exc: return {'category':'json_parse_error','detail':str(exc),'output_prefix':clean[:80]}
    if not isinstance(values,list): return {'category':'not_array','detail':type(values).__name__,'output_prefix':clean[:80]}
    types=dict(Counter(type(value).__name__ for value in values))
    category='element_type_mismatch' if any(type(value) is not int for value in values) else 'value_sequence_mismatch'
    return {'category':category,'detail':json.dumps({'items':len(values),'item_types':types},sort_keys=True),'output_prefix':clean[:80]}


def structure_findings(rows,model,repeat,caps,futures_per_cap):
    """Check frozen coordinates and reported scores against actual response text."""
    findings=[]
    if any(r.get('model')!=model or r.get('repeat')!=repeat for r in rows): findings.append('model_or_repeat_identity')
    if any(r.get('row_type') not in {'reference','verification','paired_future'} for r in rows): findings.append('unexpected_row_type')
    references=[r for r in rows if r.get('row_type')=='reference']
    registrations=[r for r in rows if r.get('row_type')=='verification']
    pairs=[r for r in rows if r.get('row_type')=='paired_future']
    for name,items in (('reference',references),('verification',registrations)):
        if len(items)!=len(caps) or {r['cap'] for r in items}!=set(caps): findings.append(name+'_cap_set')
    coordinates=[(r['cap'],r['turn']) for r in pairs]
    expected={(cap,turn) for cap in caps for turn in range(1,futures_per_cap+1)}
    if len(coordinates)!=len(expected) or set(coordinates)!=expected: findings.append('future_cap_turn_set')
    ref_by_cap={r['cap']:r for r in references}; reg_by_cap={r['cap']:r for r in registrations}
    for cap,registration in reg_by_cap.items():
        reference=ref_by_cap.get(cap)
        if reference is None: continue
        if {key:reference.get(key) for key in ('complete_correct_array','valid_array')}!=score(reference['output_text']):
            findings.append('reported_reference_array_score_mismatch')
        if (registration['reference_finish'],registration['reference_tokens'])!=(reference['finish_reason'],len(reference['output_token_ids'])):
            findings.append('verification_reference_mismatch')
        if registration['certificate_issued'] and (reference['finish_reason']!='stop' or not reference.get('witness_available')):
            findings.append('uncertifiable_reference_admitted')
    for row in pairs:
        registration=reg_by_cap.get(row['cap'])
        if registration is None or row['compiled']!=registration['certificate_issued']: findings.append('future_route_mismatch')
        for key in ('raw','policy'):
            if row[key+'_score']!=score(row[key]['output_text']): findings.append('reported_array_score_mismatch')
            if len(row[key]['output_token_ids'])>row['cap']: findings.append('output_exceeds_cap')
        if row['first_diverging_token']!=first_divergence(row['raw']['output_token_ids'],row['policy']['output_token_ids']):
            findings.append('reported_token_divergence_mismatch')
    return sorted(set(findings))


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cells=[]; pairs=[]; registrations=[]; failures=[]; actual=0; joins=0; formats=[]
    protocol=json.loads((a.root/'source_snapshot/configs/tsc_revision_r1r_long_horizon_protocol_v1.json').read_text())
    model_names={'qwen':'qwen3-8b','mistral':'mistral7b','llama':'llama31-8b'}
    for model in ('qwen','mistral','llama'):
        for repeat in (1,2,3):
            name=f'long-horizon_{model}_r{repeat}'; directory=a.root/name; raw=directory/'raw.jsonl'
            if not raw.with_suffix('.summary.json').is_file(): failures.append(name+':missing'); continue
            summary=json.loads(raw.with_suffix('.summary.json').read_text()); rows=read(raw)
            reference_by_cap={r['cap']:r for r in rows if r['row_type']=='reference'}
            if hashlib.sha256(raw.read_bytes()).hexdigest()!=summary['raw_sha256']: failures.append(name+':hash')
            failures.extend(name+':'+item for item in structure_findings(rows,model_names[model],repeat,protocol['output_caps'],protocol['futures_per_cap']))
            business=[r for r in rows if r['row_type']=='reference']+[r[k] for r in rows if r['row_type']=='paired_future' for k in ('raw','policy')]
            events=load_metrics(directory/'metrics.jsonl'); actual+=len(business)
            if len(business)!=15 or len({r['request_id'] for r in business})!=15: failures.append(name+':generation_count_or_ids')
            for r in business:
                if not r['success'] or not r['token_ids_available'] or not r['output_token_ids'] or len(r['output_token_ids'])!=r['completion_tokens'] or r['finish_reason'] not in {'stop','length'}:
                    failures.append(name+':missing_actual_generation')
                if r['request_id'] in events: joins+=1
                else: failures.append(name+':missing_metric_join')
            for r in rows:
                if r['row_type']=='reference':
                    formats.append({'cell':name,'model':r['model'],'repeat':r['repeat'],'cap':r['cap'],'turn':0,'role':'reference',
                                    'compiled_policy':False,**schema_diagnostic(r['output_text'],r['finish_reason'])})
                if r['row_type']=='verification':
                    registrations.append({'cell':name,**r})
                    if r['reference_finish']=='length' and r['certificate_issued']: failures.append(name+':length_admission')
                    if not r['certificate_issued'] and r['committed_tokens']: failures.append(name+':rejected_publication')
                if r['row_type']=='paired_future':
                    witness=reference_by_cap[r['cap']]
                    pairs.append({'cell':name,**r,**horizon_measures(len(witness['output_token_ids']),r['policy']['output_token_ids'],witness['output_token_ids'])})
                    for role in ('raw','policy'):
                        formats.append({'cell':name,'model':r['model'],'repeat':r['repeat'],'cap':r['cap'],'turn':r['turn'],'role':role,
                                        'compiled_policy':role=='policy' and r['compiled'],**schema_diagnostic(r[role]['output_text'],r[role]['finish_reason'])})
            cells.append(name)
    groups=defaultdict(list)
    for r in pairs: groups[(r['model'],r['cap'])].append(r)
    table=[]; compact=[]
    for key,rs in sorted(groups.items()):
        regs=[r for r in registrations if (r['model'],r['cap'])==key]
        table.append({'model':key[0],'cap':key[1],'raw_references':len(regs),
                      'length_references':sum(r['reference_finish']=='length' for r in regs),
                      'admitted_references':sum(r['certificate_issued'] for r in regs),
                      'reference_actual_tokens_max':max(r['reference_tokens'] for r in regs),
                      'future_pairs':len(rs),'compiled_pairs':sum(r['compiled'] for r in rs),
                      'compiled_outputs_gt256':sum(r['compiled'] and len(r['policy']['output_token_ids'])>256 for r in rs),
                      'compiled_outputs_gt512':sum(r['compiled'] and len(r['policy']['output_token_ids'])>512 for r in rs),
                      'compiled_output_tokens_max':max((len(r['policy']['output_token_ids']) for r in rs if r['compiled']),default=0),
                      'compiled_outputs_exceed_reference_length':sum(r['compiled'] and r['positions_beyond_reference_length']>0 for r in rs),
                      'compiled_positions_beyond_reference_length':sum(r['positions_beyond_reference_length'] for r in rs if r['compiled']),
                      'compiled_divergences_from_witness':sum(r['compiled'] and r['first_divergence_from_witness']!=-1 for r in rs),
                      'token_divergences':sum(r['first_diverging_token']!=-1 for r in rs),
                      'raw_complete_correct_arrays':sum(r['raw_score']['complete_correct_array'] for r in rs),
                      'policy_complete_correct_arrays':sum(r['policy_score']['complete_correct_array'] for r in rs),
                      'compiled_correctness_regressions':sum(r['compiled'] and r['raw_score']['complete_correct_array'] and not r['policy_score']['complete_correct_array'] for r in rs)})
        for r in rs:
            compact.append({k:r[k] for k in ('cell','model','repeat','cap','turn','compiled','first_diverging_token')} | {
                'raw_tokens':len(r['raw']['output_token_ids']),'policy_tokens':len(r['policy']['output_token_ids']),
                **{k:r[k] for k in ('reference_returned_tokens','positions_beyond_reference_length','first_divergence_from_witness','future_positions_from_first_divergence')},
                'raw_finish':r['raw']['finish_reason'],'policy_finish':r['policy']['finish_reason'],
                'raw_correct':r['raw_score']['complete_correct_array'],'policy_correct':r['policy_score']['complete_correct_array']})
    a.output.mkdir(parents=True,exist_ok=True)
    if table: write(a.output/'long_output_summary_v1.csv',table); write(a.output/'long_output_pairs_v1.csv',compact)
    if formats:
        write(a.output/'posthoc_schema_diagnostics_v1.csv',formats)
        counts=Counter((r['model'],r['cap'],r['role'],r['compiled_policy'],r['category']) for r in formats)
        write(a.output/'posthoc_schema_summary_v1.csv',[dict(zip(('model','cap','role','compiled_policy','category'),key))|{'generations':count} for key,count in sorted(counts.items())])
    audit={'schema_version':'tsc-r1r.long-completion.v1','complete_cells':len(cells),'expected_cells':9,
           'actual_generations':actual,'expected_generations':135,'metric_joins':joins,'paired_futures':len(pairs),
           'failures':sorted(set(failures)),'execution_complete':len(cells)==9 and actual==joins==135 and not failures,
           'posthoc_schema_diagnostic_rows':len(formats),'posthoc_diagnostics_do_not_change_primary_scores':True,
           'scope':'controlled long-output mechanics; never pooled with benchmark quality or performance'}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit))
    return 0 if audit['execution_complete'] else 2


if __name__=='__main__': raise SystemExit(main())
