"""Actual length/stop/quality and metric audit for controlled long outputs."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write
from scripts.tsc_revision_live import load_metrics


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cells=[]; pairs=[]; registrations=[]; failures=[]; actual=0; joins=0
    for model in ('qwen','mistral','llama'):
        for repeat in (1,2,3):
            name=f'long-horizon_{model}_r{repeat}'; directory=a.root/name; raw=directory/'raw.jsonl'
            if not raw.with_suffix('.summary.json').is_file(): failures.append(name+':missing'); continue
            summary=json.loads(raw.with_suffix('.summary.json').read_text()); rows=read(raw)
            if hashlib.sha256(raw.read_bytes()).hexdigest()!=summary['raw_sha256']: failures.append(name+':hash')
            business=[r for r in rows if r['row_type']=='reference']+[r[k] for r in rows if r['row_type']=='paired_future' for k in ('raw','policy')]
            events=load_metrics(directory/'metrics.jsonl'); actual+=len(business)
            if len(business)!=15 or len({r['request_id'] for r in business})!=15: failures.append(name+':generation_count_or_ids')
            for r in business:
                if not r['success'] or not r['token_ids_available'] or len(r['output_token_ids'])!=r['completion_tokens']: failures.append(name+':missing_actual_generation')
                if r['request_id'] in events: joins+=1
                else: failures.append(name+':missing_metric_join')
            for r in rows:
                if r['row_type']=='verification':
                    registrations.append({'cell':name,**r})
                    if r['reference_finish']=='length' and r['certificate_issued']: failures.append(name+':length_admission')
                    if not r['certificate_issued'] and r['committed_tokens']: failures.append(name+':rejected_publication')
                if r['row_type']=='paired_future': pairs.append({'cell':name,**r})
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
                      'token_divergences':sum(r['first_diverging_token']!=-1 for r in rs),
                      'raw_complete_correct_arrays':sum(r['raw_score']['complete_correct_array'] for r in rs),
                      'policy_complete_correct_arrays':sum(r['policy_score']['complete_correct_array'] for r in rs),
                      'compiled_correctness_regressions':sum(r['compiled'] and r['raw_score']['complete_correct_array'] and not r['policy_score']['complete_correct_array'] for r in rs)})
        for r in rs:
            compact.append({k:r[k] for k in ('cell','model','repeat','cap','turn','compiled','first_diverging_token')} | {
                'raw_tokens':len(r['raw']['output_token_ids']),'policy_tokens':len(r['policy']['output_token_ids']),
                'raw_finish':r['raw']['finish_reason'],'policy_finish':r['policy']['finish_reason'],
                'raw_correct':r['raw_score']['complete_correct_array'],'policy_correct':r['policy_score']['complete_correct_array']})
    a.output.mkdir(parents=True,exist_ok=True)
    if table: write(a.output/'long_output_summary_v1.csv',table); write(a.output/'long_output_pairs_v1.csv',compact)
    audit={'schema_version':'tsc-r1r.long-completion.v1','complete_cells':len(cells),'expected_cells':9,
           'actual_generations':actual,'expected_generations':135,'metric_joins':joins,'paired_futures':len(pairs),
           'failures':sorted(set(failures)),'execution_complete':len(cells)==9 and actual==joins==135 and not failures,
           'scope':'controlled long-output mechanics; never pooled with benchmark quality or performance'}
    (a.output/'completion_audit_v1.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit))
    return 0 if audit['execution_complete'] else 2


if __name__=='__main__': raise SystemExit(main())
