"""Freeze rates/SLO/marks only from completed Raw-only development calibration."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
def cutoff(value):return max(1500,int(math.ceil(1.5*value/500)*500))

def main(root):
    study=root/'results/tsc_template_task_serving_20261019'
    state=read(study/'calibration_execution_state_v1.json');assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS'
    assert read(study/'calibration_exit_v1.json')['returncode']==0
    calibration=read(study/'calibration_protocol_v1.json');catalog=read(study/'development_catalog_v1.json')
    profiles={}
    for job in calibration['jobs']:
        path=study/'runs'/job['id']/'attempt1';assert path.relative_to(study).as_posix() in state['completed_cells']
        result=read(path/'summary_v1.json')
        assert read(path/'completion_v1.json')['summary_sha256']==sha(path/'summary_v1.json')
        assert result['offered']==result['successful']==80 and result['actual_verification_RPCs']==result['compiled_business']==0
        assert result['business_native_unavailable']==0 and result['raw_file_sha256']==sha(path/'responses.jsonl')
        profiles[job['model']]=dict(Raw_rate=80/result['wall_s'],Raw_epoch_wall_s=result['wall_s'],
            Raw_intrinsic_TTFT_p95_ms=result['backend_TTFT_ms']['p95'],Raw_intrinsic_E2E_p95_ms=result['backend_e2e_ms']['p95'],
            SLO=dict(TTFT_ms=cutoff(result['backend_TTFT_ms']['p95']),E2E_ms=cutoff(result['backend_e2e_ms']['p95'])),
            source_summary_sha256=sha(path/'summary_v1.json'),calibration_cell=path.relative_to(study).as_posix())
    samples=[json.loads(s) for s in (study/'inputs_validation_v2/sessions_v2.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(samples)==6
    marks={};gaps={}
    for repeat in range(1,4):
        frames=[]
        for round_index in range(2):
            order=list(samples);random.Random(2026101940+10*repeat+round_index).shuffle(order)
            for sample in order:
                for turn in range(1+round_index*4,5+round_index*4):
                    for tenant in range(8):frames.append(dict(sequence=len(frames),source_group=sample['revision_source_group'],tenant=tenant,turn=turn))
        assert len(frames)==384
        marks[repeat]=frames;rng=random.Random(2026101930+repeat);gaps[repeat]=[rng.expovariate(1.) for _ in frames]
    qualification=sha(study/'development_catalog_v1.json');queues={0:[],1:[]};joblist=[]
    policies=['Raw-authorized','Session-qualified','Template-qualified']
    for model_index,model in enumerate(profiles):
        for repeat in range(1,4):
            lane=(repeat-1+model_index)%2
            rotation=(repeat-1)%3;order=policies[rotation:]+policies[:rotation]
            loads=[('common80',.8),('high100',1.)] if model=='Qwen3-8B' else [('common80',.8)]
            for load,multiplier in loads:
                rate=profiles[model]['Raw_rate']*multiplier;total=1.;frames=[]
                for frame,gap in zip(marks[repeat],gaps[repeat]):
                    total+=gap/rate;frames.append(dict(**frame,unit_exponential_gap=gap,ready_offset_s=total))
                arrivals=f'formal_arrivals_v1/{model}-{load}-r{repeat}.json'
                write(study/arrivals,dict(schema='frozen-task-template-marked-Poisson.v1',model=model,repeat=repeat,load=load,
                    arrival_rate=rate,marked_locality='two32-request blocks per template',requests=frames))
                for policy in order:
                    name=f'{model}-{load}-r{repeat}-{policy}'
                    job=dict(id=name,model=model,phase='formal',policy=policy,input_set='validation',eligible_families=catalog['models'][model]['eligible_families'],
                        qualification_hash=qualification,arrivals=arrivals,repeat=repeat,load=load,arrival_rate_rps=rate,
                        SLO=profiles[model]['SLO'],snapshot='formal_freeze_v1/source_snapshot',job_file='formal_jobs_v1/'+name+'.json',lane=lane,attempt=1)
                    queues[lane].append(job)
    # All three policies in a model/repeat run on the SAME physical GPU.
    # The other lane is ready first and held throughout each measured wave.
    wave_index=0
    while queues[0] or queues[1]:
        for lane in (0,1):
            if queues[lane]:
                job=queues[lane].pop(0);job['wave']=wave_index;joblist.append(job)
        wave_index+=1
    for index,job in enumerate(joblist):job['port']=10100+index;write(study/job['job_file'],job)
    assert sum(j['model']=='Qwen3-8B' for j in joblist)==18
    assert len(joblist)<=36
    assert all(len({j['lane'] for j in joblist if j['wave']==w})==sum(j['wave']==w for j in joblist) for w in {j['wave'] for j in joblist})
    write(study/'formal_protocol_v1.json',dict(schema='task-template-formal-service.v1',jobs=joblist,Raw_only_profiles=profiles,
        same_GPU_within_model_repeat=True,common_load_is_model_normalized_not_cross_model_absolute_rate=True,
        all_source_templates_included=6,requests_per_cell=384,Qwen_two_loads_three_repeats=True,optional_models_one_load_three_repeats=True,
        paired_arrivals_equal_across_policies=True,independent_formal_model_outputs_before_freeze=0,
        measurement_contract_sha256=sha(study/'serving_measurement_contract_v1.json'),
        no_outcome_based_sources_loads_SLO_or_job_selection=True,source_sha256=sha(Path(__file__))))
    print(json.dumps(dict(jobs=len(joblist),Raw_only_profiles=profiles)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
