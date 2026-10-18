"""Fresh-server, paired fixed-arrival measurement; no method or admission change."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event,Thread
import time

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_raw_worker_v1 as raw

STUDY=raw.STUDY;PY=raw.PY;DISK=raw.DISK
read=raw.read;write=raw.write;sha=raw.sha;state=raw.state


def start_server(root,study,job,policy_hash,owned):
    cell=study/'formal/cells'/job['id'];assert not cell.exists();cell.mkdir(parents=True)
    assert not raw.foreign_pids(raw.resource_snapshot(),owned),'Wait for exclusive GPUs'
    with socket.socket() as sock:sock.bind(('127.0.0.1',job['port']))
    source=study/'source_snapshot_v1';runtime=root/raw.CORE/'preflight_v3/runtime'
    cache=cell/'cache';tmp=cell/'tmp';tmp.mkdir()
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
    model=job['model'];served=raw.SERVED[model]
    server=[PY,'-B','-m','vllm.entrypoints.openai.api_server','--model',str(DISK/'models'/model),
        '--served-model-name',served,'--host','127.0.0.1','--port',str(job['port']),'--dtype','float16',
        '--tensor-parallel-size','1','--max-model-len','16384','--max-num-seqs','2','--gpu-memory-utilization','.88','--enable-prefix-caching']
    protocol=read(study/'raw_calibration_protocol_v1.json')
    client=[PY,'-B',str(source/'scripts/tsc_revision_final_fixed_client_v2.py'),'--client-audit',str(cell/'client_audit_v2.json'),
        '--cpu-prompt-shapes',str(study/'inputs_v1/CPU_prompt_shapes_v1.jsonl'),'--economic-gate',job['economic_gate'],
        '--protocol',str(root/protocol['generation_protocol']),'--catalog',str(root/protocol['selected_catalog']),
        '--previous-catalog',str(root/'configs/tsc_revision_r3_catalog_v1.json'),'--profile','balanced',
        '--sessions',str(study/'inputs_v1/faithful_selected_sessions_v1.jsonl'),'--model',served,'--model-identity',model,
        '--study','template-fanout','--policy',job['policy'],'--base-url',f'http://127.0.0.1:{job["port"]}/v1',
        '--cell-id',job['id'],'--policy-hash',policy_hash,'--repeat',str(job['repeat']),'--tenants-per-template','6',
        '--arrival-trace',str(study/job['arrival']),'--output',str(cell/'raw.jsonl'),'--summary',str(cell/'summary.json'),
        '--metrics-events',str(cell/'metrics.jsonl')]
    write(cell/'launch_v1.json',dict(job=job,server=server,client=client,
        environment={k:v for k,v in env.items() if k.startswith(('CONTRACTKV_','VLLM_','CUDA_')) or k in ['PYTHONPATH','TMPDIR']},
        no_heavy_residency_hook=True,model_runtime_preflight_reused=True,source_snapshot_unchanged=True))
    process=None
    try:
        with (cell/'server.log').open('xb') as handle:
            process=subprocess.Popen(server,cwd=source,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
        owned.add(process.pid);write(cell/'server_process_v1.json',dict(pid=process.pid,process_group=process.pid))
        return dict(job=job,cell=cell,process=process,client=client,environment=env,source=source)
    except BaseException:
        raw.stop_own_group(process)
        if process:owned.discard(process.pid)
        raise


def client(item):
    stop=Event();thread=Thread(target=raw.monitor,args=(item['job']['port'],item['cell']/'telemetry_v1.jsonl',stop),daemon=True)
    thread.start();started=time.time()
    try:
        with (item['cell']/'client.log').open('xb') as handle:
            done=subprocess.run(item['client'],cwd=item['source'],env=item['environment'],stdout=handle,stderr=subprocess.STDOUT,
                timeout=item['job']['client_timeout_s'])
        if done.returncode:raise RuntimeError('Serving client failed; retain whole wave: '+item['job']['id'])
        summary=read(item['cell']/'summary.json');audit=read(item['cell']/'client_audit_v2.json')
        assert summary['execution_complete'] and summary['arrival_requests']==360 and summary['futures']==324
        assert summary['policy']==item['job']['policy'] and summary['repeat']==item['job']['repeat']
        if item['job']['policy']=='raw-order':assert summary['verification_calls']==summary['compiled_future_requests']==0
        assert summary['arrival_trace_sha256']==item['job']['arrival_sha256']
        assert audit['result']=='completed' and audit['actual_business_prompt_ID_hashes_checked']==360
        assert audit['economic_gate']==item['job']['economic_gate']
        assert read(item['cell']/'measured_backend_drain_v1.json')['backend_request_counters_drained']
        return dict(started_epoch_s=started,ended_epoch_s=time.time(),summary=summary)
    finally:stop.set();thread.join(timeout=10)


def run_wave(root,study,jobs,policy_hash,owned):
    items=[];outcomes=[];errors=[];resource_stop=Event();violation=Event();thread=None
    wave=str(jobs[0]['wave']);waves=study/'formal/waves'
    try:
        for job in jobs:items.append(start_server(root,study,job,policy_hash,owned));time.sleep(2)
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            for future in [pool.submit(raw.ready,item) for item in items]:future.result()
        write(waves/f'wave_{wave}_ready_v1.json',dict(jobs=[x['id'] for x in jobs],
            all_servers_ready_before_any_client=True,no_weight_loading_during_peer_measurement=True,ready_epoch_s=time.time()))
        thread=Thread(target=raw.resource_monitor,args=(waves/f'wave_{wave}_GPU_resources_v1.jsonl',owned,resource_stop,violation),daemon=True)
        thread.start()
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            futures=[pool.submit(client,item) for item in items]
            for future in futures:
                try:outcomes.append(future.result())
                except BaseException as error:errors.append(error)
        if errors:raise errors[0]
        resource_stop.set();thread.join(timeout=10)
        assert not thread.is_alive() and not violation.is_set(),'Unverified GPU exclusivity; preserve whole wave'
        assert not raw.foreign_pids(raw.resource_snapshot(),owned)
        for item,outcome in zip(items,outcomes):
            write(item['cell']/'completion_v1.json',dict(status='complete',job=item['job'],outcome=outcome,
                held_peer_server_until_all_wave_clients_finished=True,
                files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in item['cell'].glob('*.jsonl')]))
        return [str(item['cell'].relative_to(study)) for item in items]
    except BaseException as error:
        for item in items:
            if not (item['cell']/'failure_v1.json').exists():write(item['cell']/'failure_v1.json',
                dict(type=type(error).__name__,message=str(error),whole_wave_invalid=True,retain_all_requests=True))
        raise
    finally:
        resource_stop.set()
        if thread:thread.join(timeout=10)
        for item in items:raw.stop_own_group(item['process']);owned.discard(item['process'].pid)


def paired_compiled_feasibility(study,protocol,phase):
    checks=[]
    for model,load,repeat in sorted({(j['model'],j['load'],j['repeat']) for j in protocol['jobs'] if j['phase']==phase}):
        pair=[j for j in protocol['jobs'] if (j['phase'],j['model'],j['load'],j['repeat'])==(phase,model,load,repeat)]
        assert len(pair)==2
        data={}
        for job in pair:
            cell=study/'formal/cells'/job['id'];assert read(cell/'completion_v1.json')['status']=='complete'
            rows=[json.loads(x) for x in (cell/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            data[job['policy']]={(r['source_group'],r['tenant_id'],r['turn_id']):r for r in rows if r['row_type'] in ('warm','future')}
        baseline=data['raw-order'];contract=data['risk-tail'];assert baseline.keys()==contract.keys() and len(baseline)==360
        compiled=[(baseline[key],row) for key,row in contract.items() if row['effective_level']!='L0']
        changed=[(a,b) for a,b in compiled if (a['output_token_ids'],a['finish_reason'])!=(b['output_token_ids'],b['finish_reason'])]
        checks.append(dict(model=model,load=load,repeat=repeat,compiled_pairs=len(compiled),compiled_ID_or_finish_changes=len(changed)))
    assert not any(x['compiled_ID_or_finish_changes'] for x in checks),'Compiled behavioral difference: stop and attribute before cross-model extension'
    return checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--phase',choices=['qwen','cross','gate'],required=True);parser.add_argument('--freeze-sha256',required=True)
    args=parser.parse_args();root=args.root.resolve();study=root/STUDY
    assert sys.platform=='linux' and root.is_relative_to(DISK)
    frozen=study/'formal_freeze_v1.json';assert sha(frozen)==args.freeze_sha256;freeze=read(frozen)
    for row in freeze['files']:assert sha(root/row['path'])==row['sha256'],row['path']
    parent=read(study/'raw_calibration_freeze_v1.json')
    for row in parent['snapshot_files']:assert sha(study/'source_snapshot_v1'/row['path'])==row['sha256']
    assert sha(root/raw.CORE/'preflight_v3/receipt_v1.json')==parent['parent_runtime_receipt_sha256']
    raw.validate_preflight(root/raw.CORE)
    assert read(study/'calibration/profiles_exit_v1.json')['returncode']==0
    assert read(study/'calibration/profiles_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
    assert not raw.foreign_pids(raw.resource_snapshot()),'Do not compete with unrelated GPU jobs'
    protocol=read(study/'formal_protocol_v1.json');jobs=[j for j in protocol['jobs'] if j['phase']==args.phase]
    assert len(jobs)=={'qwen':12,'cross':12,'gate':6}[args.phase]
    import fcntl
    with (study/'formal_worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=study/'formal'/f'{args.phase}_execution_state_v1.json';assert not path.exists()
        if args.phase in ('cross','gate'):
            assert read(study/'formal/qwen_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
            proof=study/'formal/qwen_execution_feasibility_v1.json'
            expected=dict(checks=paired_compiled_feasibility(study,protocol,'qwen'),no_parameter_or_source_changes=True)
            if proof.exists():assert read(proof)==expected
            else:write(proof,expected)
        if args.phase=='gate':
            assert read(study/'formal/cross_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
            proof=study/'formal/cross_execution_feasibility_v1.json'
            expected=dict(checks=paired_compiled_feasibility(study,protocol,'cross'),no_parameter_or_source_changes=True)
            if proof.exists():assert read(proof)==expected
            else:write(proof,expected)
        current=dict(status='RUNNING',worker_pid=os.getpid(),phase=args.phase,completed_cells=[])
        state(path,current);owned=set()
        try:
            for wave in sorted({j['wave'] for j in jobs}):
                current['completed_cells']+=run_wave(root,study,[j for j in jobs if j['wave']==wave],args.freeze_sha256,owned)
                state(path,current)
            current.update(status='COMPLETE_PENDING_ANALYSIS',worker_pid=None);state(path,current)
        except BaseException as error:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error))
            state(path,current);raise


if __name__=='__main__':main()
