"""Test two-server measurement barriers with explicit fake workers, not inference."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import sys
from unittest.mock import patch

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_raw_worker_v1 as worker


def main(root):
    events=[];ready_ids=set();finished=set()
    jobs=[dict(id='CPU_FAKE_A',lane=0,wave=0),dict(id='CPU_FAKE_B',lane=1,wave=0)]
    with tempfile.TemporaryDirectory(prefix='raw_barrier_CPU_',dir=root/'.artifacts') as folder:
        study=Path(folder)
        def start(root,study,job,policy,owned):
            cell=study/'calibration/cells'/job['id'];cell.mkdir(parents=True)
            process=SimpleNamespace(pid=900000+job['lane']);owned.add(process.pid);events.append(['start',job['id']])
            return dict(job=job,cell=cell,process=process)
        def ready(item):ready_ids.add(item['job']['id']);events.append(['ready',item['job']['id']])
        def client(item):
            assert len(ready_ids)==2
            events.append(['client',item['job']['id']]);finished.add(item['job']['id'])
            return dict(CPU_FAKE=True,not_a_service_result=True)
        def stop(process):
            assert len(finished)==2, 'Never stop or reload one server during its peer measurement'
            events.append(['stop',process.pid])
        fake_time=SimpleNamespace(sleep=lambda _:None,time=time.time,monotonic=time.monotonic,perf_counter=time.perf_counter)
        with patch.object(worker,'start_server',start),patch.object(worker,'ready',ready),patch.object(worker,'client',client),\
             patch.object(worker,'stop_own_group',stop),patch.object(worker,'resource_snapshot',lambda:dict(CPU_FAKE=True,processes=[])),\
             patch.object(worker,'foreign_pids',lambda *args:[]),patch.object(worker,'time',fake_time):
            completed=worker.run_wave(root,study,jobs,'CPU_FAKE_POLICY',set())
        assert len(completed)==2
        ready_positions=[i for i,x in enumerate(events) if x[0]=='ready']
        client_positions=[i for i,x in enumerate(events) if x[0]=='client']
        stop_positions=[i for i,x in enumerate(events) if x[0]=='stop']
        assert max(ready_positions)<min(client_positions) and max(client_positions)<min(stop_positions)
    result=dict(status='PASS',new_GPU_requests=0,fake_workers=2,both_ready_before_any_client=True,
        both_clients_finished_before_any_server_stopped=True,trace=events,service_performance_claim=False)
    path=root/'results/tsc_final_existing_evidence_CPU_20261018/raw_calibration_orchestration_CPU_v1.json'
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
