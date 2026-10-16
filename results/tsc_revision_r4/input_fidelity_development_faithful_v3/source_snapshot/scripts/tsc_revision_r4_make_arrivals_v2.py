"""Standardize nominal load per model; pair all policies on identical arrivals."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_make_arrivals import make_trace,read,sha
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals

ALIASES={'Qwen3-8B':'qwen','Mistral-7B-Instruct-v0.3':'mistral','Llama-3.1-8B-Instruct':'llama'}


def model_trace(samples,sessions_sha,tenants,durations,repeat,model,load=.8):
    trace=make_trace(samples,sessions_sha,tenants,2,durations,repeat,load)
    trace.update(model_identity=model,common_across_models_and_policies=False,
                 common_across_policies_within_model=True,nominal_load_standardized_to_each_model_development_raw=True)
    trace['boundary']='Exogenous two-request waves; identical relative arrival offsets across all policies within a model/repeat. Each model has nominal .8 load from its own observed development raw mean wave service. Absolute rates differ across models. Shared dispatch barrier, queueing, all idle and drain remain on clock; not production traffic.'
    return trace


def main():
    p=argparse.ArgumentParser();p.add_argument('--development-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cold',type=Path,required=True);p.add_argument('--fanout',type=Path,required=True);p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve model-specific arrival version')
    freeze=json.loads((a.development_root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol'];sources=[];measures={}
    for cell in sorted((a.development_root/'cells').glob('*raw-order*')):
        summary=json.loads((cell/'summary.json').read_text(encoding='utf-8'))
        if not summary['execution_complete'] or sha(cell/'raw.jsonl')!=summary['raw_file_sha256']:raise ValueError('Complete development raw inputs required')
        samples=read(a.development_root/'source_snapshot'/config['input_files'][summary['study']]);tenants=summary['tenants_per_template']
        ids=[s['revision_session_id']+(f'-tenant{t:02d}' if tenants>1 else '') for s in samples for t in range(tenants)]
        order={sid:i for i,sid in enumerate(ids)};waves=defaultdict(list);model=None
        for row in read(cell/'raw.jsonl'):
            if row['row_type'] in ('warm','future'):waves[order[row['session_id']]//2,row['turn_id']].append(row);model=row['model']
        local=defaultdict(list)
        for rows in waves.values():
            if len(rows)!=2:raise ValueError('Complete two-request development wave required')
            families={r['family'] for r in rows}
            if len(families)!=1:continue
            local[next(iter(families))].append(max(r['end_time'] for r in rows)-min(r['first_time']-r['ttft_ms']/1000 for r in rows))
        for family,values in local.items():measures[summary['study'],model,family]={'mean_wave_service_s':statistics.fmean(values),'waves':len(values)}
        sources.append({'path':(cell/'raw.jsonl').as_posix(),'sha256':sha(cell/'raw.jsonl')})
    if len(sources)!=6:raise ValueError('All six development raw cells required')
    a.output.mkdir(parents=True);files={};duration_records=[]
    for study,path,tenants in [('single-session',a.cold,1),('template-fanout',a.fanout,10)]:
        samples=read(path);files[study]={}
        for model,alias in ALIASES.items():
            durations={family:measures[study,model,family]['mean_wave_service_s'] for family in sorted({s['revision_family'] for s in samples})}
            duration_records.extend({'study':study,'model':model,'family':family,**measures[study,model,family]} for family in durations)
            files[study][model]={}
            for repeat in range(1,a.repeats+1):
                trace=model_trace(samples,sha(path),tenants,durations,repeat,model)
                dest=a.output/f'{study}_{alias}_r{repeat}.json'
                with dest.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(trace,indent=2)+'\n')
                ids=[s['revision_session_id']+(f'-tenant{t:02d}' if tenants>1 else '') for s in samples for t in range(tenants)]
                load_arrivals(dest,sha(path),ids,tenants,2)
                files[study][model][str(repeat)]={'path':dest.as_posix(),'sha256':sha(dest),'waves':len(trace['waves']),'last_offset_s':trace['waves'][-1]['ready_offset_s']}
    manifest={'schema_version':'tsc-r4.model-specific-arrival-calibration.v2','development_freeze_sha256':sha(a.development_root/'freeze.json'),
              'only_observed_development_raw_timings':True,'new_validation_model_outcomes_used':False,'offered_load':.8,
              'common_across_policies_within_model':True,'model_specific_nominal_load':True,
              'amendment':'Before any formal new50 forwards, replace common slowest-model absolute trace with each model own observed mean-wave service at the same prespecified nominal .8 load. All policies within model/repeat remain exactly paired. The old common-rate generator and any derived v1 tables remain preserved.',
              'boundary':'New-source service demand can differ from development: actual achieved utilization need not equal .8. This is one frozen synthetic offered-load point, not a production trace or universal p99 guarantee.',
              'sources':sources,'duration_records':duration_records,'files':files,'generator_sha256':sha(Path(__file__))}
    manifest['base_trace_generator_sha256']=sha(Path(__file__).with_name('tsc_revision_r4_make_arrivals.py'))
    (a.output/'arrival_commitment_v2.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps({'generated_traces':sum(len(v) for x in files.values() for v in x.values()),'files':files}))


if __name__=='__main__':main()
