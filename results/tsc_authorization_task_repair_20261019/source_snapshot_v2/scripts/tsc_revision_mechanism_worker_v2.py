"""Isolated two-stage orchestration for bounded mechanism diagnostics."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT_REL=Path('results/tsc_revision_mechanism_controls_20261018')
DISK=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')
PYTHON='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_tableIII_fullcost_worker_v3 import resource_snapshot, foreign_pids, stop_own_group, runtime_inventory


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
def state(p,value):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(p)


def preflight(root,study,plan):
    out=study/'preflight_v2';out.mkdir()
    registry=root/'results/tsc_tableIII_fullcost_replay_20261018/launch_attempt3_preflight/model_registry_v1.json'
    expected='f498ce77473d08efd6672b8cc729f9d0b0d2d738ecd69911cdfae4def91e72eb'
    assert sha(registry)==expected
    models=[x for x in read(registry)['models'] if x['model'] in plan['models']]
    assert len(models)==3
    for model in models:
        for x in model['files']:
            q=DISK/'models'/model['model']/x['file'];st=q.stat()
            assert (st.st_size,st.st_mtime_ns)==(x['bytes'],x['mtime_ns']),q
    write(out/'model_asset_registry_v1.json',dict(models=models,full_hash_origin=str(registry),origin_sha256=expected,
          current_stat_match=True,claim='Full SHA measured before Table III; unchanged assets verified again before this separate diagnostic.'))
    source=root/'third_party/vllm-contractkv-tsc-r2-margin';target=out/'runtime'
    commitment=read(study/'source_snapshot/configs/tsc_revision_r2_backend_commitment_v1.json')
    for x in commitment['source_files']:assert sha(source/x['file'])==x['after_sha256'],x['file']
    for x in commitment['native_extensions']:assert sha(source/x['relative_path'])==x['sha256'],x['relative_path']
    before=runtime_inventory(source/'vllm')
    shutil.copytree(source,target,symlinks=True,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
    after=runtime_inventory(target/'vllm');assert before==after
    assert runtime_inventory(source/'vllm')==before
    write(out/'runtime_inventory_v1.json',dict(source=str(source),copy=str(target),files=after,shared_source_unchanged=True))
    from transformers import AutoTokenizer
    identities=[];shapes=[]
    for model in models:
        path=DISK/'models'/model['model'];tok=AutoTokenizer.from_pretrained(str(path),local_files_only=True)
        assets=model['files'];config=json.loads((path/'tokenizer_config.json').read_text())
        tokenizer_assets=[x for x in assets if x['file'].startswith(('tokenizer','special_tokens','vocab','merges'))]
        identity=dict(model_identity=model['model'],model_revision='registered-assets-sha256:'+hashlib.sha256(json.dumps(assets,sort_keys=True).encode()).hexdigest(),
            tokenizer=hashlib.sha256(json.dumps(tokenizer_assets,sort_keys=True).encode()).hexdigest(),
            chat_template_hash=hashlib.sha256(json.dumps(config.get('chat_template'),sort_keys=True).encode()).hexdigest(),
            runtime_revision=sha(out/'runtime_inventory_v1.json'))
        filename='identity_'+model['model']+'.json';write(out/filename,identity);identities.append(filename)
        for case in plan['behavior_cases']+plan['manifest_cases']:
            for condition in ('raw','candidate'):
                ids=tok.apply_chat_template(case[condition+'_messages'],tokenize=True,add_generation_prompt=True)
                assert ids and len(ids)+case['output_budget']+1<=16384
                shapes.append(dict(model=model['model'],case_id=case['case_id'],condition=condition,
                    prompt_tokens=len(ids),output_budget=case['output_budget'],
                    prompt_ids_sha256=hashlib.sha256(json.dumps(ids,sort_keys=True,ensure_ascii=False).encode()).hexdigest()))
    write(out/'input_shapes_v1.json',dict(shapes=shapes,all_fit_16K=True,no_input_truncation=True))
    files=[p for p in out.glob('*.json')]
    write(out/'receipt_v1.json',dict(plan_sha256=sha(study/'protocol_v1.json'),worker_sha256=sha(Path(__file__)),
        no_GPU_inference=True,metadata=[dict(path=p.name,sha256=sha(p)) for p in files]))
    return out/'receipt_v1.json'


def validate_preflight(study):
    out=study/'preflight_v2';receipt=out/'receipt_v1.json';r=read(receipt)
    assert r['plan_sha256']==sha(study/'protocol_v1.json') and r['worker_sha256']==sha(Path(__file__))
    for x in r['metadata']:assert sha(out/x['path'])==x['sha256']
    inv=read(out/'runtime_inventory_v1.json');assert runtime_inventory(Path(inv['copy'])/'vllm')==inv['files']
    for model in read(out/'model_asset_registry_v1.json')['models']:
        for x in model['files']:
            st=(DISK/'models'/model['model']/x['file']).stat();assert (st.st_size,st.st_mtime_ns)==(x['bytes'],x['mtime_ns'])
    return receipt


def run_cell(root,study,model,repeat,lane,attempt,owned):
    name=f'{model}_r{repeat}';cell=study/'cells'/name/f'attempt{attempt}';cell.mkdir(parents=True)
    assert not foreign_pids(resource_snapshot(),owned),'Foreign GPU task; no diagnostic launch'
    port=8990+lane
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    tmp=cell/'tmp';tmp.mkdir();alias=Path('/tmp')/('ckvME-'+hashlib.sha256(str(tmp).encode()).hexdigest()[:12])
    assert tmp.resolve().is_relative_to(DISK)
    if alias.is_symlink():assert alias.resolve()==tmp.resolve()
    else:assert not alias.exists();alias.symlink_to(tmp,target_is_directory=True)
    cache=cell/'cache';policy_hash=sha(study/'freeze_v2.json');source=study/'source_snapshot'
    env={k:v for k,v in os.environ.items() if not k.startswith(('CONTRACTKV_','VLLM_')) and k not in ('TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR')}
    env.update(CUDA_VISIBLE_DEVICES=str(lane),PYTHONPATH=os.pathsep.join([str(source/'scripts/tsc_residency_trace_v1'),str(study/'preflight_v2/runtime'),str(source)]),
        TMPDIR=str(alias),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),
        XDG_CACHE_HOME=str(cache/'xdg'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),
        VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',VLLM_USE_V1='1',
        CONTRACTKV_POLICY_HASH=policy_hash,CONTRACTKV_MIN_CANDIDATE_MARGIN='-1000000000',CONTRACTKV_MAX_DEGRADATION='1000000000',
        CONTRACTKV_MIN_RAW_TOKEN_MARGIN='.0625',CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN='.125',
        CONTRACTKV_SHADOW_CHUNK_TOKENS='128',CONTRACTKV_SHADOW_ROUND_TOKENS='128',
        CONTRACTKV_PREFIX_METRICS='1',CONTRACTKV_PREFIX_INITIAL_ONLY='1',CONTRACTKV_PREFIX_METRICS_LOG=str(cell/'metrics.jsonl'),
        CONTRACTKV_RESIDENCY_TRACE=str(cell/'backend_trace.jsonl'),CONTRACTKV_R2_VERIFY_TRACE=str(cell/'verify_trace.jsonl'))
    served={'Qwen3-8B':'qwen3-8b','Mistral-7B-Instruct-v0.3':'mistral-7b','Llama-3.1-8B-Instruct':'llama-3.1-8b'}[model]
    server_cmd=[PYTHON,'-B','-m','vllm.entrypoints.openai.api_server','--model',str(DISK/'models'/model),
        '--served-model-name',served,'--host','127.0.0.1','--port',str(port),'--dtype','float16',
        '--tensor-parallel-size','1','--max-model-len','16384','--max-num-seqs','2','--gpu-memory-utilization','.88','--enable-prefix-caching']
    client=[PYTHON,'-B',str(source/'scripts/tsc_revision_mechanism_live_v2.py'),'--root',str(source),'--plan',str(study/'protocol_v1.json'),
        '--identity',str(study/'preflight_v2'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1',
        '--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]
    write(cell/'launch_v1.json',dict(server=server_cmd,client=client,environment={k:v for k,v in env.items() if k.startswith(('CONTRACTKV_','VLLM_','CUDA_')) or k in ('PYTHONPATH','TMPDIR')},repeat=repeat,lane=lane))
    server=None
    try:
        with (cell/'server.log').open('xb') as log:
            server=subprocess.Popen(server_cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);owned.add(server.pid)
            write(cell/'server_process_v1.json',dict(pid=server.pid,process_group=server.pid))
            deadline=time.monotonic()+600
            while True:
                if server.poll() is not None:raise RuntimeError('Diagnostic server startup exited')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models',timeout=3) as response:
                        assert any(x['id']==served for x in json.load(response)['data'])
                    break
                except Exception:
                    if time.monotonic()>deadline:raise TimeoutError('Diagnostic server startup timeout')
                    time.sleep(1)
            with (cell/'client.log').open('xb') as out:
                done=subprocess.run(client,cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
            assert done.returncode==0,'Diagnostic client failed; preserve complete cell and all outputs'
            rows=[json.loads(x) for x in (cell/'responses.jsonl').open() if x.strip()]
            assert rows[-1]['event']=='diagnostic_cell_complete'
            assert len([r for r in rows if r['event']=='behavior_case_complete'])==20
            assert len([r for r in rows if r['event']=='manifest_request_complete'])==8
            assert len([r for r in rows if r['event']=='registration_control'])==3
            assert not foreign_pids(resource_snapshot(),owned)
            write(cell/'completion_v1.json',dict(status='complete',counts=rows[-1]['counts'],
                diagnostic_no_performance_claim=True,files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size)
                    for p in cell.glob('*.jsonl')]))
    except BaseException as exc:
        write(cell/'failure_v1.json',dict(type=type(exc).__name__,message=str(exc),retain_all_attempts=True));raise
    finally:
        stop_own_group(server)
        if server:owned.discard(server.pid)
    return str(cell.relative_to(study))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--mode',choices=['preflight','execute'],required=True)
    p.add_argument('--receipt-sha256');p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
    root=a.root.resolve();study=root/ROOT_REL;assert sys.platform=='linux' and root.is_relative_to(DISK)
    table=read(root/'results/tsc_tableIII_fullcost_replay_20261018/execution_state_v1.json')
    assert table['status']=='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS' and table['formal_GPU_cells_completed']==24,'Do not overlap original full-cost replay'
    freeze=read(study/'freeze_v2.json')
    for x in freeze['files']:
        assert sha(study/'source_snapshot'/x['path'])==x['sha256']
    # Business/server imports use the frozen snapshot. Do not overwrite live
    # root dependencies belonging to other studies to deploy this diagnostic.
    expected={x['path']:x['sha256'] for x in freeze['files']}
    assert sha(Path(__file__))==expected['scripts/tsc_revision_mechanism_worker_v2.py']
    assert sha(Path(runtime_inventory.__code__.co_filename))==expected['scripts/tsc_tableIII_fullcost_worker_v3.py']
    assert not foreign_pids(resource_snapshot()),'Wait for exclusively available GPUs'
    import fcntl
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=dict(status='PREFLIGHT',worker_pid=os.getpid(),attempt=a.attempt,completed_cells=[])
        state(study/'execution_state_v1.json',current)
        try:
            plan=read(study/'protocol_v1.json');receipt=study/'preflight_v2/receipt_v1.json'
            if not receipt.exists():receipt=preflight(root,study,plan)
            validate_preflight(study)
            current.update(status='AWAITING_RECEIPT_PUBLICATION',receipt_sha256=sha(receipt));state(study/'execution_state_v1.json',current)
            if a.mode=='preflight':return 0
            assert a.receipt_sha256==sha(receipt),'Publish the exact preflight receipt before GPU forwarding'
            owned=set();jobs=[(model,r) for r in (1,2,3) for model in plan['models']]
            for i in range(0,len(jobs),2):
                wave=jobs[i:i+2]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[]
                    for lane,(model,r) in enumerate(wave):
                        futures.append(pool.submit(run_cell,root,study,model,r,lane,a.attempt,owned));time.sleep(2)
                    for f in futures:current['completed_cells'].append(f.result())
                current['status']='RUNNING';state(study/'execution_state_v1.json',current)
            current.update(status='MATRIX_COMPLETE_PENDING_ANALYSIS',worker_pid=None);state(study/'execution_state_v1.json',current)
        except BaseException as exc:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(exc).__name__,error_message=str(exc));state(study/'execution_state_v1.json',current);raise
    return 0


if __name__=='__main__':raise SystemExit(main())
