"""Single-use bounded worker, reusing the unchanged isolated server launcher."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event,Thread
import time
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_raw_worker_v1 as base
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight

STUDY=Path('results/tsc_behavior_scope_repair_20261020')
CORE=Path('results/tsc_revision_mechanism_controls_20261018')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,indent=2);f.write('\n')
def state(p,x):
    q=p.with_suffix('.tmp');q.write_text(json.dumps(x,indent=2)+'\n');q.replace(p)

def adapted_start():
    old=next(n for n in ast.parse(Path(base.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='start_server')
    new=deepcopy(old)
    changes=dict(cell="study/'runs'/job['id']/'attempt1'",source="study/job['snapshot']",protocol='None',
        client="[PY,'-B',str(source/'scripts/tsc_behavior_scope_client_v1.py'),'--study',str(study),'--job',str(study/job['job_file']),'--identity',str(root/CORE/'preflight_v3'/('identity_'+model+'.json')),'--output',str(cell/'responses.jsonl'),'--summary',str(cell/'summary_v1.json'),'--metrics-events',str(cell/'metrics.jsonl'),'--base-url',f'http://127.0.0.1:{job[\"port\"]}/v1','--model',served,'--policy-hash',policy_hash]")
    for key,expression in changes.items():
        nn=[n for n in ast.walk(new) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets)]
        assert len(nn)==1;nn[0].value=ast.copy_location(ast.parse(expression,mode='eval').body,nn[0].value)
    a,b=deepcopy(old),deepcopy(new)
    for fn in [a,b]:
        for n in ast.walk(fn):
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in changes for t in n.targets):n.value=ast.Constant(value='DECLARED_REPAIR_DISPATCH')
    assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
    space=base.__dict__.copy();exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),str(base.__file__)+'[exact-behavior-repair]','exec'),space)
    return space['start_server'],dict(parent_sha256=sha(Path(base.__file__)),changed_assignments=list(changes),all_other_server_AST_identical=True)

def run_client(item):
    stop=Event();thread=Thread(target=base.monitor,args=(item['job']['port'],item['cell']/'telemetry_v1.jsonl',stop),daemon=True);thread.start()
    try:
        with (item['cell']/'client.log').open('xb') as f:done=subprocess.run(item['client'],cwd=item['source'],env=item['environment'],stdout=f,stderr=subprocess.STDOUT,timeout=3600)
        assert done.returncode==0,'Scientific cell failed: preserve all outputs; no automatic retry'
        result=read(item['cell']/'summary_v1.json')
        assert result['execution_complete'] and result['offered']==item['job']['expected_business']==result['successful']
        assert result['raw_file_sha256']==sha(item['cell']/'responses.jsonl')
        assert read(item['cell']/'measured_backend_drain_v1.json')['backend_request_counters_drained']
        return result
    finally:stop.set();thread.join(timeout=10)

def wave(root,study,jobs,policy,owned,start):
    items=[];stop=Event();violation=Event();monitor=None
    try:
        for job in jobs:items.append(start(root,study,job,policy,owned));time.sleep(2)
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            for f in [pool.submit(base.ready,i) for i in items]:f.result()
        label=hashlib.sha256('|'.join(j['id'] for j in jobs).encode()).hexdigest()[:16]
        write(study/'waves'/(label+'_ready_v1.json'),dict(jobs=[j['id'] for j in jobs],all_servers_ready_before_any_client=True))
        monitor=Thread(target=base.resource_monitor,args=(study/'waves'/(label+'_GPU_resources_v1.jsonl'),owned,stop,violation),daemon=True);monitor.start()
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            outcomes=[f.result() for f in [pool.submit(run_client,i) for i in items]]
        stop.set();monitor.join(timeout=10)
        assert not monitor.is_alive() and not violation.is_set() and not base.foreign_pids(base.resource_snapshot(),owned)
        for item,result in zip(items,outcomes):
            write(item['cell']/'completion_v1.json',dict(status='complete',job=item['job'],summary_sha256=sha(item['cell']/'summary_v1.json'),
                files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in item['cell'].iterdir() if p.is_file() and p.name!='server.log']))
        return [i['cell'].relative_to(study).as_posix() for i in items]
    except BaseException as e:
        for item in items:
            p=item['cell']/'failure_v1.json'
            if not p.exists():write(p,dict(error_type=type(e).__name__,error_message=str(e),whole_wave_invalid=True,outputs_preserved=True))
        raise
    finally:
        stop.set()
        if monitor:monitor.join(timeout=10)
        for item in items:base.stop_own_group(item['process']);owned.discard(item['process'].pid)

def main(a):
    root=a.root.resolve();study=root/STUDY;assert sys.platform=='linux' and root.is_relative_to(base.DISK)
    freeze=study/(a.phase+'_freeze_v1/freeze.json');assert sha(freeze)==a.freeze_sha256
    data=read(freeze)
    for r in data['files']:
        assert sha(root/r['path'])==sha(freeze.parent/'source_snapshot'/r['path'])==r['sha256'],r['path']
    start,proof=adapted_start();assert proof==data['server_adapter_proof']
    protocol=read(study/(a.phase+'_jobs_v1.json'));jobs=protocol['jobs']
    receipt=study/(a.phase+'_preflight_v1.json');status=study/(a.phase+'_execution_state_v1.json')
    if a.mode=='launch':
        assert not status.exists() and not (study/(a.phase+'_launch_v1.json')).exists()
        assert a.receipt_sha256==sha(receipt)
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'--root',str(root),'--phase',a.phase,'--mode','execute',
                 '--freeze-sha256',a.freeze_sha256,'--receipt-sha256',a.receipt_sha256]
        with (study/(a.phase+'_worker.log')).open('xb') as log:process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(study/(a.phase+'_launch_v1.json'),dict(worker_pid=process.pid,command=command,published_commit=a.published_commit,epoch_s=time.time()))
        print(json.dumps({'worker_pid':process.pid}));return 0
    if base.foreign_pids(base.resource_snapshot()):print('WAIT_FOR_EXCLUSIVE_GPU');return 75
    validate_preflight(root/CORE)
    if a.mode=='preflight':
        assert not receipt.exists() and not status.exists()
        registry=read(root/CORE/'preflight_v3/model_asset_registry_v1.json');assets=[]
        for model in registry['models']:
            if model['model'] not in protocol['models']:continue
            for r in model['files']:
                path=base.DISK/'models'/model['model']/r['file'];assert sha(path)==r['sha256'],str(path)
            assets.append(dict(model=model['model'],full_SHA_files=len(model['files'])))
        frozen=freeze.parent/'source_snapshot';runtime=root/CORE/'preflight_v3/runtime'
        env={**os.environ,'PYTHONPATH':os.pathsep.join([str(runtime),str(frozen)]),'PYTHONDONTWRITEBYTECODE':'1',
             'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','CUDA_VISIBLE_DEVICES':''}
        with (study/(a.phase+'_CPU_import_probe.log')).open('xb') as log:
            done=subprocess.run([sys.executable,'-B',str(frozen/'scripts/tsc_behavior_scope_client_v1.py'),'--help'],cwd=frozen,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        assert done.returncode==0,'No model inference until isolated import passes'
        write(receipt,dict(status='PASS',freeze_sha256=a.freeze_sha256,assets=assets,server_adapter_proof=proof,
                           parent_runtime_receipt_sha256=sha(root/CORE/'preflight_v3/receipt_v1.json'),
                           resources=base.resource_snapshot(),isolated_client_import_PASS=True,new_model_generations=0))
        print(json.dumps({'receipt_sha256':sha(receipt)}));return 0
    assert a.receipt_sha256==sha(receipt)
    import fcntl
    with (study/(a.phase+'_worker.lock')).open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert not status.exists(),'Monitor existing worker; never duplicate'
        value=dict(status='RUNNING',worker_pid=os.getpid(),planned_cells=len(jobs),completed_cells=[],current_wave=[]);state(status,value)
        owned=set();started=time.time();ret=0
        try:
            groups={}
            for job in jobs:groups.setdefault(job['wave'],[]).append(job)
            for current in groups.values():
                value['current_wave']=[j['id'] for j in current];state(status,value)
                value['completed_cells'].extend(wave(root,study,current,a.freeze_sha256,owned,start));state(status,value)
            value.update(status='COMPLETE_PENDING_INDEPENDENT_ANALYSIS',worker_pid=None,current_wave=[]);state(status,value)
        except BaseException as e:
            ret=1;value.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(e).__name__,error_message=str(e));state(status,value);raise
        finally:write(study/(a.phase+'_exit_v1.json'),dict(returncode=ret,started_epoch_s=started,ended_epoch_s=time.time(),automatic_retries=False))
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--phase',choices=['development','validation'],required=True)
    p.add_argument('--mode',choices=['preflight','launch','execute'],required=True);p.add_argument('--freeze-sha256',required=True)
    p.add_argument('--receipt-sha256');p.add_argument('--published-commit');raise SystemExit(main(p.parse_args()))
