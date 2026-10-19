"""Final CPU audit of actual launch, drain and resource evidence."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

STUDY=Path('results/tsc_template_task_serving_20261019')
EXPECTED={'0':'GPU-ef01d441-985f-50b3-6e64-5d4c3e2def3a','1':'GPU-a696ce9a-7137-cf6f-b4d3-deb992a72f28'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main(workspace,evidence,output):
    proof=read(workspace/STUDY/'formal_local_independent_recompute_v1.json')
    assert proof['status']=='PASS' and not output.exists()
    study=evidence/STUDY;protocol=read(study/'formal_protocol_v1.json')
    state=read(study/'formal_execution_state_v1.json');end=read(study/'formal_exit_v1.json')
    assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS' and len(state['completed_cells'])==27
    assert end['returncode']==0 and not end['automatic_retries']
    waves=defaultdict(list);devices=defaultdict(set);cells=[]
    for job in protocol['jobs']:
        path=study/'runs'/job['id']/'attempt1'
        launch=read(path/'launch_v1.json');summary=read(path/'summary_v1.json');drain=read(path/'measured_backend_drain_v1.json')
        assert launch['job']==summary['job']==job
        assert summary['execution_complete'] and summary['offered']==summary['successful']==384
        assert drain['backend_request_counters_drained'] and drain['included_in_measured_service_clock']
        visible=launch['environment']['CUDA_VISIBLE_DEVICES'];assert visible==str(job['lane'])
        devices[job['model'],job['repeat']].add(visible)
        command=launch['server']
        for flag,value in [('--max-model-len','16384'),('--max-num-seqs','2'),('--tensor-parallel-size','1'),('--dtype','float16'),('--host','127.0.0.1')]:
            assert command[command.index(flag)+1]==value
        assert '--enable-prefix-caching' in command
        process=read(path/'server_process_v1.json');assert process['pid']==process['process_group']
        assert not (path/'failure_v1.json').exists()
        cells.append(dict(cell=job['id'],model=job['model'],repeat=job['repeat'],load=job['load'],policy=job['policy'],
            CUDA_VISIBLE_DEVICES=visible,server_process_group=process['process_group'],success=384,
            full_backend_drain_in_service_clock=True))
        waves[job['wave']].append(job)
    assert all(len(v)==1 for v in devices.values())
    snapshots=0;wave_rows=[]
    for number,jobs in sorted(waves.items()):
        label=hashlib.sha256('|'.join(j['id'] for j in jobs).encode()).hexdigest()[:16]
        ready=read(study/'waves'/(label+'_ready_v1.json'))
        assert ready['jobs']==[j['id'] for j in jobs] and ready['all_servers_ready_before_any_measured_client']
        count=0
        with (study/'waves'/(label+'_GPU_resources_v1.jsonl')).open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():continue
                row=json.loads(line);assert not row['foreign_GPU_PIDs']
                mapping={r[0]:r[1] for r in row['snapshot']['devices']};assert mapping==EXPECTED
                assert all('3090' in r[2] for r in row['snapshot']['devices'])
                count+=1
        assert count>0;snapshots+=count
        wave_rows.append(dict(wave=number,jobs=[j['id'] for j in jobs],all_servers_ready_before_clients=True,
            actual_resource_snapshots=count,no_foreign_GPU_processes_in_snapshots=True,actual_index_UUID_mapping_stable=True))
    release=read(workspace/STUDY/'formal_GPU_completion_audit_v1.json')['resource_after_exit']
    assert release['formal_exit']['returncode']==0 and not release['GPU_compute'].strip()
    result=dict(status='PASS_ACTUAL_FROZEN_EXECUTION_AND_GPU_RELEASE_AUDIT',new_GPU_requests=0,
        archive_sha256=proof['archive_sha256'],actual_cells=27,actual_business=10368,successful_business=10368,
        GPU_matrix_elapsed_seconds=end['ended_epoch_s']-end['started_epoch_s'],
        expected_GPU_index_UUID_mapping=EXPECTED,resource_snapshots_checked=snapshots,
        same_CUDA_device_ordinal_within_each_model_repeat=True,configuration_identical_across_policy_arms=True,
        full_backend_drain_in_every_cell_clock=True,owned_GPU_compute_released=True,
        boundary='Same-device evidence combines frozen CUDA_VISIBLE_DEVICES launches with the stable actual index/UUID resource records on the same host. No cross-engine KV reuse or public-IAM claim.',
        cells=cells,waves=wave_rows,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ['status','actual_cells','actual_business','resource_snapshots_checked','owned_GPU_compute_released','GPU_matrix_elapsed_seconds']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['workspace','evidence-root','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();main(args.workspace.resolve(),args.evidence_root.resolve(),args.output.resolve())
