"""Fresh-server Raw-only load calibration; no Contract task output is produced."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from threading import Event,Thread
import time
import urllib.request

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_tableIII_fullcost_worker_v3 import resource_snapshot,foreign_pids,stop_own_group
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight

STUDY='results/tsc_task_faithful_open_arrival_20261018'
CORE='results/tsc_revision_mechanism_controls_20261018'
DISK=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')
PY='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
SERVED={'Qwen3-8B':'qwen3-8b','Mistral-7B-Instruct-v0.3':'mistral-7b','Llama-3.1-8B-Instruct':'llama-3.1-8b'}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
def state(p,value):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');temp.replace(p)


def fetch_metrics(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics',timeout=5) as response:return response.read().decode()


def monitor(port,path,stop):
    names=['num_requests_running','num_requests_waiting','kv_cache_usage_perc','gpu_cache_usage_perc','num_preemptions_total']
    with path.open('x',encoding='utf-8') as f:
        while not stop.is_set():
            row=dict(monotonic_s=time.perf_counter(),epoch_s=time.time())
            try:
                text=fetch_metrics(port);values={}
                for name in names:
                    matches=[float(x) for x in re.findall(r'^vllm:'+name+r'(?:\{[^\n]*\})?\s+([\d.eE+-]+)$',text,re.M)]
                    values[name]=sum(matches) if matches else None
                row.update(available=True,values=values)
            except Exception as error:row.update(available=False,error_type=type(error).__name__,error_message=str(error))
            f.write(json.dumps(row)+'\n');f.flush();stop.wait(.5)


def resource_monitor(path,owned,stop,violation):
    with path.open('x',encoding='utf-8') as f:
        while not stop.is_set():
            try:
                snapshot=resource_snapshot();unexpected=foreign_pids(snapshot,owned)
                row=dict(monotonic_s=time.perf_counter(),snapshot=snapshot,foreign_GPU_PIDs=unexpected)
                if unexpected:violation.set()
            except Exception as error:
                row=dict(monotonic_s=time.perf_counter(),error_type=type(error).__name__,error_message=str(error));violation.set()
            f.write(json.dumps(row)+'\n');f.flush();stop.wait(2.)


def start_server(root,study,job,policy_hash,owned):
    cell=study/'calibration/cells'/job['id'];assert not cell.exists();cell.mkdir(parents=True)
    assert not foreign_pids(resource_snapshot(),owned),'Wait; do not compete with another GPU task'
    with socket.socket() as s:s.bind(('127.0.0.1',job['port']))
    source=study/'source_snapshot_v1';runtime=root/CORE/'preflight_v3/runtime';cache=cell/'cache';tmp=cell/'tmp';tmp.mkdir()
    alias=Path('/tmp')/('ckvFA-'+hashlib.sha256(str(tmp).encode()).hexdigest()[:12])
    assert not alias.exists() and not alias.is_symlink();alias.symlink_to(tmp,target_is_directory=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('CONTRACTKV_','VLLM_')) and k not in ['TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR']}
    env.update(CUDA_VISIBLE_DEVICES=str(job['lane']),PYTHONPATH=os.pathsep.join([str(runtime),str(source)]),
        TMPDIR=str(alias),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),
        XDG_CACHE_HOME=str(cache/'xdg'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),
        VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',VLLM_USE_V1='1',CONTRACTKV_POLICY_HASH=policy_hash,
        CONTRACTKV_MIN_CANDIDATE_MARGIN='-1000000000',CONTRACTKV_MAX_DEGRADATION='1000000000',
        CONTRACTKV_MIN_RAW_TOKEN_MARGIN='.0625',CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN='.125',
        CONTRACTKV_SHADOW_CHUNK_TOKENS='128',CONTRACTKV_SHADOW_ROUND_TOKENS='128',
        CONTRACTKV_PREFIX_METRICS='1',CONTRACTKV_PREFIX_INITIAL_ONLY='1',CONTRACTKV_PREFIX_METRICS_LOG=str(cell/'metrics.jsonl'))
    assert not any('RESIDENCY_TRACE' in key or 'VERIFY_TRACE' in key for key in env)
    model=job['model'];served=SERVED[model]
    server=[PY,'-B','-m','vllm.entrypoints.openai.api_server','--model',str(DISK/'models'/model),
        '--served-model-name',served,'--host','127.0.0.1','--port',str(job['port']),'--dtype','float16',
        '--tensor-parallel-size','1','--max-model-len','16384','--max-num-seqs','2','--gpu-memory-utilization','.88','--enable-prefix-caching']
    protocol=read(study/'raw_calibration_protocol_v1.json')
    client=[PY,'-B',str(source/'scripts/tsc_revision_final_fixed_client_v2.py'),'--client-audit',str(cell/'client_audit_v2.json'),
        '--cpu-prompt-shapes',str(study/'inputs_v1/CPU_prompt_shapes_v1.jsonl'),'--economic-gate','ON',
        '--protocol',str(root/protocol['generation_protocol']),'--catalog',str(root/protocol['selected_catalog']),
        '--previous-catalog',str(root/'configs/tsc_revision_r3_catalog_v1.json'),'--profile','balanced',
        '--sessions',str(study/'inputs_v1/faithful_selected_sessions_v1.jsonl'),'--model',served,'--model-identity',model,
        '--study','template-fanout','--policy','raw-order','--base-url',f'http://127.0.0.1:{job["port"]}/v1',
        '--cell-id',job['id'],'--policy-hash',policy_hash,'--repeat','1','--tenants-per-template','2',
        '--arrival-trace',str(study/job['arrival']),'--output',str(cell/'raw.jsonl'),'--summary',str(cell/'summary.json'),
        '--metrics-events',str(cell/'metrics.jsonl')]
    write(cell/'launch_v1.json',dict(job=job,server=server,client=client,
        environment={k:v for k,v in env.items() if k.startswith(('CONTRACTKV_','VLLM_','CUDA_')) or k in ['PYTHONPATH','TMPDIR']},
        no_heavy_residency_hook=True,model_runtime_preflight_reused=True))
    handle=(cell/'server.log').open('xb')
    process=None
    try:
        process=subprocess.Popen(server,cwd=source,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
        owned.add(process.pid);write(cell/'server_process_v1.json',dict(pid=process.pid,process_group=process.pid))
        return dict(job=job,cell=cell,process=process,client=client,environment=env,source=source)
    except BaseException:
        stop_own_group(process)
        if process:owned.discard(process.pid)
        raise
    finally:handle.close()


def ready(item):
    deadline=time.monotonic()+600;job=item['job']
    while time.monotonic()<deadline:
        if item['process'].poll() is not None:raise RuntimeError('Server startup exited: '+job['id'])
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{job["port"]}/v1/models',timeout=3) as response:
                assert any(x['id']==SERVED[job['model']] for x in json.load(response)['data'])
            return
        except Exception:time.sleep(1)
    raise TimeoutError('Server startup deadline: '+job['id'])


def client(item):
    stop=Event();thread=Thread(target=monitor,args=(item['job']['port'],item['cell']/'telemetry_v1.jsonl',stop),daemon=True)
    thread.start();started=time.time()
    try:
        with (item['cell']/'client.log').open('xb') as f:
            done=subprocess.run(item['client'],cwd=item['source'],env=item['environment'],stdout=f,stderr=subprocess.STDOUT,
                timeout=item['job'].get('client_timeout_s',3600))
        if done.returncode:raise RuntimeError('Raw client failed; preserve its complete evidence: '+item['job']['id'])
        summary=read(item['cell']/'summary.json');audit=read(item['cell']/'client_audit_v2.json')
        assert summary['execution_complete'] and summary['arrival_requests']==120 and summary['futures']==108
        assert summary['verification_calls']==summary['compiled_future_requests']==0
        assert audit['result']=='completed' and audit['actual_business_prompt_ID_hashes_checked']==120
        assert read(item['cell']/'measured_backend_drain_v1.json')['backend_request_counters_drained']
        return dict(started_epoch_s=started,ended_epoch_s=time.time(),summary=summary)
    finally:stop.set();thread.join(timeout=10)


def run_wave(root,study,jobs,policy_hash,owned):
    items=[];outcomes=[];errors=[];resource_stop=Event();resource_violation=Event();resource_thread=None
    try:
        for job in jobs:items.append(start_server(root,study,job,policy_hash,owned));time.sleep(2)
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            futures=[pool.submit(ready,item) for item in items]
            for f in futures:f.result()
        # No new model-loading process overlaps either measured client.
        write(study/'calibration/waves'/('wave_'+str(jobs[0]['wave'])+'_ready_v1.json'),
            dict(jobs=[x['id'] for x in jobs],both_servers_ready_before_any_client=True,ready_epoch_s=time.time()))
        resource_thread=Thread(target=resource_monitor,args=(study/'calibration/waves'/('wave_'+str(jobs[0]['wave'])+'_GPU_resources_v1.jsonl'),
            owned,resource_stop,resource_violation),daemon=True);resource_thread.start()
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            futures=[pool.submit(client,item) for item in items]
            for f in futures:
                try:outcomes.append(f.result())
                except BaseException as e:errors.append(e)
        if errors:raise errors[0]
        resource_stop.set();resource_thread.join(timeout=10)
        assert not resource_thread.is_alive() and not resource_violation.is_set(),'GPU exclusivity was not continuously supported; preserve whole wave'
        assert not foreign_pids(resource_snapshot(),owned)
        for item,outcome in zip(items,outcomes):
            write(item['cell']/'completion_v1.json',dict(status='complete',job=item['job'],outcome=outcome,
                held_peer_server_until_all_wave_clients_finished=True,
                files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in item['cell'].glob('*.jsonl')]))
        return [str(x['cell'].relative_to(study)) for x in items]
    except BaseException as error:
        for item in items:
            if not (item['cell']/'failure_v1.json').exists():write(item['cell']/'failure_v1.json',
                dict(type=type(error).__name__,message=str(error),whole_wave_invalid=True,retain_all_requests=True))
        raise
    finally:
        resource_stop.set()
        if resource_thread:resource_thread.join(timeout=10)
        for item in items:
            stop_own_group(item['process']);owned.discard(item['process'].pid)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--phase',choices=['baseline','profiles'],required=True);p.add_argument('--freeze-sha256',required=True)
    p.add_argument('--derived-profile-plan-sha256');a=p.parse_args();root=a.root.resolve();study=root/STUDY
    assert sys.platform=='linux' and root.is_relative_to(DISK)
    freeze_path=study/'raw_calibration_freeze_v1.json';assert sha(freeze_path)==a.freeze_sha256;freeze=read(freeze_path)
    for row in freeze['files']:assert sha(root/row['path'])==row['sha256'],row['path']
    for row in freeze['snapshot_files']:assert sha(study/'source_snapshot_v1'/row['path'])==row['sha256']
    assert sha(root/CORE/'preflight_v3/receipt_v1.json')==freeze['parent_runtime_receipt_sha256']
    validate_preflight(root/CORE)
    prior=root/'results/tsc_real_repobench_mechanism_20261018'
    assert read(prior/'formal_execution_v1_exit.json')['returncode']==0
    assert read(prior/'execution_state_v1.json')['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS'
    assert not foreign_pids(resource_snapshot()),'Wait for exclusive GPUs'
    if a.phase=='baseline':jobs=read(study/'raw_calibration_protocol_v1.json')['baseline_jobs']
    else:
        derived=study/'calibration/derived_profile_plan_v1.json';assert sha(derived)==a.derived_profile_plan_sha256
        assert read(study/'calibration/baseline_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
        jobs=read(derived)['profile_jobs']
    import fcntl
    with (study/'calibration_worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=study/'calibration'/f'{a.phase}_execution_state_v1.json';assert not path.exists()
        current=dict(status='RUNNING',worker_pid=os.getpid(),phase=a.phase,completed_cells=[])
        state(path,current);owned=set()
        try:
            for wave in sorted({j['wave'] for j in jobs}):
                current['completed_cells']+=run_wave(root,study,[x for x in jobs if x['wave']==wave],a.freeze_sha256,owned)
                state(path,current)
            current.update(status='COMPLETE_PENDING_ANALYSIS',worker_pid=None);state(path,current)
        except BaseException as error:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error))
            state(path,current);raise


if __name__=='__main__':main()
