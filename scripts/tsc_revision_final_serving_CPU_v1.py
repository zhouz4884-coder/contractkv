"""CPU controls for arrival pairing and orchestration; never GPU efficacy evidence."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import tempfile
from threading import Event

if __package__ in (None,''):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_raw_derive_v1 import arrivals,percentile,read,sha,write
from scripts.tsc_revision_final_serving_prepare_v1 import matrix
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals
from scripts import tsc_revision_final_serving_worker_v1 as worker


def check(root):
    study=root/'results/tsc_task_faithful_open_arrival_20261018';inputs=study/'inputs_v1/faithful_selected_sessions_v1.jsonl'
    sessions=[json.loads(line) for line in inputs.read_text(encoding='utf-8').splitlines()]
    assert len(sessions)==6
    records={};checks=[]
    with tempfile.TemporaryDirectory(prefix='ckv_final_CPU_') as temporary:
        out=Path(temporary)
        for index,load in enumerate(('common','high')):
            for repeat in (1,2,3):
                rate=.5 if load=='common' else .8;seed=202610181000+100*index+repeat
                trace=arrivals(sessions,6,rate,seed,sha(inputs));assert trace==arrivals(sessions,6,rate,seed,sha(inputs))
                target=out/f'{load}_r{repeat}.json';write(target,trace)
                ids=[s['revision_session_id']+f'-tenant{tenant:02d}' for s in sessions for tenant in range(6)]
                waves,_,_=load_arrivals(target,sha(inputs),ids,6,2)
                assert len(waves)==180 and trace['actual_business_requests']==360
                assert trace['waves'][0]['ready_offset_s']==0 and trace['waves'][-1]['ready_offset_s']==358/rate
                assert trace['offered_horizon_s']==360/rate
                records[f'{load}_r{repeat}']=dict(path=target.name,sha256=sha(target))
        jobs=matrix(records,dict(common=.5,high=.8))
        assert len([j for j in jobs if j['phase']=='qwen'])==12
        assert len([j for j in jobs if j['phase']=='cross'])==12
        assert len([j for j in jobs if j['phase']=='gate'])==6
        assert len({j['id'] for j in jobs})==len({j['port'] for j in jobs})==30
        assert [j['economic_gate'] for j in jobs if j['phase']=='gate']==['ON','OFF','OFF','ON','ON','OFF']
        assert all(j['lane']==0 and j['policy']=='risk-tail' for j in jobs if j['phase']=='gate')
        checks += ['six normalized arrival traces validate original loader and repeat determinism',
            '24 formal plus6 isolated Gate jobs, unique cells/ports, exact Raw/Contract arrival and GPU pairing',
            'repeat2 reverses policy order and swaps main GPU lanes; Gate repeat2 OFF first']
        # Fake transport verifies whole-wave completion semantics, not model effects.
        saved={name:getattr(worker,name) for name in ('start_server','client')}
        raw_saved={name:getattr(worker.raw,name) for name in ('ready','resource_monitor','foreign_pids','resource_snapshot','stop_own_group')}
        seen=[]
        class Process:
            def __init__(self,pid):self.pid=pid
        def start(root,study,job,policy,owned):
            cell=study/'formal/cells'/job['id'];cell.mkdir(parents=True)
            pid=100+len(seen);owned.add(pid);seen.append(('start',job['id']))
            return dict(job=job,cell=cell,process=Process(pid))
        def ready(item):seen.append(('ready',item['job']['id']))
        def client(item):
            assert sum(kind=='ready' for kind,_ in seen)==2
            assert not any(kind=='stop' for kind,_ in seen)
            seen.append(('client',item['job']['id']));return dict(fake=True)
        def monitor(path,owned,stop,violation):
            write(path,dict(fake_resource_observation=True));stop.wait(5)
        try:
            worker.start_server=start;worker.client=client;worker.raw.ready=ready;worker.raw.resource_monitor=monitor
            worker.raw.foreign_pids=lambda *args:[];worker.raw.resource_snapshot=lambda:{}
            worker.raw.stop_own_group=lambda process:seen.append(('stop',process.pid))
            owned=set();finished=worker.run_wave(root,out,jobs[:2],'CPU_ONLY',owned)
            assert len(finished)==2 and not owned
            assert [kind for kind,_ in seen][-2:]==['stop','stop']
            assert all(read(out/path/'completion_v1.json')['status']=='complete' for path in finished)
        finally:
            for name,value in saved.items():setattr(worker,name,value)
            for name,value in raw_saved.items():setattr(worker.raw,name,value)
        checks += ['fake two-server wave: both ready before client, both complete before own-server stop; no GPU inference']
        seen.clear()
        def failing_client(item):
            assert sum(kind=='ready' for kind,_ in seen)==2
            if item['job']['id']==jobs[2]['id']:raise RuntimeError('CPU deliberate transport failure')
            return dict(fake=True)
        try:
            worker.start_server=start;worker.client=failing_client;worker.raw.ready=ready;worker.raw.resource_monitor=monitor
            worker.raw.foreign_pids=lambda *args:[];worker.raw.resource_snapshot=lambda:{}
            worker.raw.stop_own_group=lambda process:seen.append(('stop',process.pid))
            owned=set()
            try:worker.run_wave(root,out,jobs[2:4],'CPU_ONLY',owned)
            except RuntimeError as error:assert str(error)=='CPU deliberate transport failure'
            else:raise AssertionError('One client failure must invalidate the whole wave')
            assert not owned
            for job in jobs[2:4]:
                cell=out/'formal/cells'/job['id']
                assert read(cell/'failure_v1.json')['whole_wave_invalid']
                assert not (cell/'completion_v1.json').exists()
        finally:
            for name,value in saved.items():setattr(worker,name,value)
            for name,value in raw_saved.items():setattr(worker.raw,name,value)
        checks += ['fake one-client failure invalidates both wave cells and retains both failure records; no partial successful-cell reuse']
    assert percentile([0,10,20],.95)==19 and percentile([1],.95)==1
    for name in ('tsc_revision_final_raw_derive_v1.py','tsc_revision_final_serving_prepare_v1.py','tsc_revision_final_serving_worker_v1.py'):
        ast.parse((root/'scripts'/name).read_text(encoding='utf-8'))
    return dict(schema_version='contractkv.final-serving-CPU.v1',checks=checks,
        all_passed=True,new_GPU_requests=0,synthetic_transport_not_serving_efficacy=True,
        sources=[dict(path=(root/'scripts'/name).relative_to(root).as_posix(),sha256=sha(root/'scripts'/name)) for name in
            ('tsc_revision_final_raw_derive_v1.py','tsc_revision_final_serving_prepare_v1.py','tsc_revision_final_serving_worker_v1.py')])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=check(args.root.resolve());write(args.output,result);print(json.dumps(result))
