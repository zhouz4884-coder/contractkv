"""Freeze common offered load using observed development raw service only."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]


def make_trace(samples,sessions_sha,tenants,concurrency,durations,repeat,load=.8,seed=10672134):
    if not 0<load<=1:raise ValueError('Declared offered load must be in (0,1]')
    expanded=[{**s,'revision_session_id':s['revision_session_id']+(f'-tenant{t:02d}' if tenants>1 else '')} for s in samples for t in range(tenants)]
    waves=[];offset=0.;rng=random.Random(seed+repeat)
    for start in range(0,len(expanded),concurrency):
        cohort=expanded[start:start+concurrency];families=sorted({s['revision_family'] for s in cohort})
        nominal=max(durations[f] for f in families)
        if nominal<=0:raise ValueError('Nonpositive observed duration')
        for turn in range(10):
            waves.append({'wave_index':len(waves),'cohort_start':start,'turn':turn,'session_ids':[s['revision_session_id'] for s in cohort],
                          'families':families,'ready_offset_s':offset,'nominal_service_s':nominal})
            offset+=nominal/load*rng.uniform(.9,1.1)
    return {'schema_version':'tsc-r4.fixed-wave-arrivals.v1','sessions_sha256':sessions_sha,'tenants_per_template':tenants,
            'concurrency':concurrency,'repeat':repeat,'actual_business_requests':len(expanded)*10,'seed':seed+repeat,
            'nominal_offered_load':load,'common_across_models_and_policies':True,
            'boundary':'Exogenous two-request wave arrivals; shared wave dispatch barrier is retained. Delayed waves queue. This is not an independent-request asynchronous scheduler or a production trace.',
            'waves':waves}


def main():
    p=argparse.ArgumentParser();p.add_argument('--development-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cold',type=Path,required=True);p.add_argument('--fanout',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--offered-load',type=float,default=.8);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve arrival version')
    freeze=json.loads((a.development_root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol'];sources=[];measures=defaultdict(list)
    for cell in sorted((a.development_root/'cells').glob('*raw-order*')):
        summary=json.loads((cell/'summary.json').read_text(encoding='utf-8'))
        if not summary['execution_complete'] or sha(cell/'raw.jsonl')!=summary['raw_file_sha256']:raise ValueError('Incomplete development raw')
        samples=read(a.development_root/'source_snapshot'/config['input_files'][summary['study']])
        expanded=[s['revision_session_id']+(f'-tenant{t:02d}' if summary['tenants_per_template']>1 else '') for s in samples for t in range(summary['tenants_per_template'])]
        order={s:i for i,s in enumerate(expanded)};waves=defaultdict(list)
        for row in read(cell/'raw.jsonl'):
            if row['row_type'] in ('warm','future'):waves[order[row['session_id']]//2,row['turn_id']].append(row)
        local=defaultdict(list)
        for rows in waves.values():
            if len(rows)!=2:raise ValueError('Expected complete two-request raw waves')
            families={r['family'] for r in rows}
            if len(families)!=1:continue
            duration=max(r['end_time'] for r in rows)-min(r['first_time']-r['ttft_ms']/1000 for r in rows)
            local[next(iter(families))].append(duration)
        for family,values in local.items():measures[summary['study'],family].append({'model':rows[0]['model'],'mean_wave_service_s':statistics.fmean(values),'waves':len(values)})
        sources.append({'path':(cell/'raw.jsonl').as_posix(),'sha256':sha(cell/'raw.jsonl')})
    if len(sources)!=6:raise ValueError('All six development raw cells are required')
    a.output.mkdir(parents=True);files={};duration_records=[]
    for study,path,tenants in [('single-session',a.cold,1),('template-fanout',a.fanout,10)]:
        samples=read(path);durations={}
        for family in sorted({s['revision_family'] for s in samples}):
            records=measures[study,family]
            if len(records)!=3:raise ValueError('Three model development timing groups required')
            durations[family]=max(r['mean_wave_service_s'] for r in records)
            duration_records.append({'study':study,'family':family,'common_mean_wave_service_s':durations[family],'observed_model_groups':records})
        files[study]={}
        for repeat in range(1,a.repeats+1):
            trace=make_trace(samples,sha(path),tenants,2,durations,repeat,a.offered_load)
            dest=a.output/f'{study}_r{repeat}.json'
            with dest.open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(trace,indent=2)+'\n')
            ids=[s['revision_session_id']+(f'-tenant{t:02d}' if tenants>1 else '') for s in samples for t in range(tenants)]
            load_arrivals(dest,sha(path),ids,tenants,2)
            files[study][str(repeat)]={'path':dest.as_posix(),'sha256':sha(dest),'waves':len(trace['waves']),'last_offset_s':trace['waves'][-1]['ready_offset_s']}
    manifest={'schema_version':'tsc-r4.arrival-calibration.v1','development_freeze_sha256':sha(a.development_root/'freeze.json'),
              'only_observed_development_raw_timings':True,'new_validation_model_outcomes_used':False,'selection':'Maximum across three models of observed mean raw wave service per predefined family and study; one prespecified load .8 and deterministic uniform .9..1.1 interarrival jitter.',
              'offered_load':a.offered_load,'sources':sources,'duration_records':duration_records,'files':files,'generator_sha256':sha(Path(__file__))}
    (a.output/'arrival_commitment_v1.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':files}))


if __name__=='__main__':main()
