"""Deterministic Raw-only frames/jobs after independent development acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import random

MODELS=['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
def main(root):
    study=root/'results/tsc_template_task_serving_20261019';catalog=read(study/'development_catalog_v1.json')
    assert catalog['models']['Qwen3-8B']['eligible_families']
    samples=[json.loads(s) for s in (study/'inputs_development_v2/sessions_v2.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(samples)==4
    order=list(samples);random.Random(2026101919).shuffle(order);frames=[]
    for sample in order:
        source=sample['revision_source_group'];points=[(t,k) for t in range(8) for k in range(1,9)]
        points.sort(key=lambda p:hashlib.sha256(f'2026101919:{source}:{p[0]}:{p[1]}'.encode()).hexdigest())
        for tenant,turn in points[:20]:frames.append(dict(sequence=len(frames),source_group=source,tenant=tenant,turn=turn,ready_offset_s=0.))
    assert len(frames)==80
    write(study/'calibration_arrivals_v1.json',dict(schema='Raw-development-fixed-backlog.v1',requests=frames,no_Contract_output_selection=True))
    qualification=hashlib.sha256((study/'development_catalog_v1.json').read_bytes()).hexdigest();jobs=[]
    for model in MODELS:
        if not catalog['models'][model]['eligible_families']:continue
        identity=model+'-Raw-calibration';index=len(jobs)
        job=dict(id=identity,model=model,phase='calibration',policy='Raw-authorized',input_set='development',eligible_families=[],
            qualification_hash=qualification,arrivals='calibration_arrivals_v1.json',repeat=1,load='backlog80',
            snapshot='calibration_freeze_v1/source_snapshot',job_file='calibration_jobs_v1/'+identity+'.json',lane=index%2,port=10010+index,attempt=1)
        write(study/job['job_file'],job);jobs.append(job)
    write(study/'calibration_protocol_v1.json',dict(schema='task-template-Raw-only-calibration.v1',jobs=jobs,
        planned_before_Raw_calibration_output=True,model_selection='Independent development qualified family, Qwen primary.',
        primary_SLO='ceil(1.5*Raw-only intrinsic request TTFT p95/500)*500ms minimum1500ms',secondary_E2E_same_formula=True,
        Qwen_load_multipliers=[.8,1.0],other_model_load_multiplier=.8,batch_rate='80/full measured Raw-only client epoch wall',
        no_Contract_output_in_calibration=True,serving_measurement_contract='serving_measurement_contract_v1.json'))
    print(json.dumps(dict(jobs=len(jobs),models=[j['model'] for j in jobs])))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
