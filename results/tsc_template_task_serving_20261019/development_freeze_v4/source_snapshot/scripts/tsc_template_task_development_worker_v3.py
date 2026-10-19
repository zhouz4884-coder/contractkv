"""Qwen-first immutable development orchestration; optional models gated later."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Event,Thread
import time
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_mechanism_worker_v3 as base
from scripts.tsc_revision_final_raw_worker_v1 import resource_monitor

STUDY=Path('results/tsc_template_task_serving_20261019')
PARENT=Path('results/tsc_revision_mechanism_controls_20261018')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def import_probe(study):
    import subprocess
    frozen=study/'development_freeze_v3/source_snapshot'
    runtime=study/'preflight_v3/runtime'
    cache=study/'CPU_tmp/runtime_import_cache_v3';cache.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith(('CONTRACTKV_','VLLM_'))}
    env.update(PYTHONPATH=os.pathsep.join([str(frozen/'scripts/tsc_residency_trace_v1'),str(runtime),str(frozen)]),
        CUDA_VISIBLE_DEVICES='0',HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),
        XDG_CACHE_HOME=str(cache/'xdg'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),
        VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),TMPDIR=str(cache),
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',
        CONTRACTKV_RESIDENCY_TRACE=str(study/'CPU_tmp/runtime_import_trace_v3.jsonl'))
    commands=[['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B','-m','vllm.entrypoints.openai.api_server','--help'],
        ['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B','-c',
         "import sitecustomize; import scripts.tsc_revision_r2_margin_policy as m; import scripts.tsc_revision_r2_execution_trace as t; import vllm.v1.core.sched.scheduler; import vllm.v1.worker.gpu_model_runner; assert 'development_freeze_v3/source_snapshot' in m.__file__; assert 'source_snapshot/scripts/tsc_residency_trace_v1' in sitecustomize.__file__; print('ISOLATED_RUNTIME_IMPORT_AND_TRACE_PASS')"]]
    result=[]
    for i,command in enumerate(commands):
        target=study/f'CPU_tmp/runtime_import_probe_{i}_v3.log'
        with target.open('xb') as f:done=subprocess.run(command,cwd=frozen,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
        assert done.returncode==0,'Runtime import probe failed; no model inference permitted'
        result.append(dict(returncode=0,log=target.name,sha256=sha(target)))
    return dict(checks=result,no_model_load_or_generation=True,dynamic_runtime_script_imports_and_trace_entry_exercised=True)

def adapted_cell():
    old=next(n for n in ast.parse(Path(base.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run_cell')
    new=deepcopy(old)
    changes=dict(source="study/'development_freeze_v3/source_snapshot'",policy_hash="sha(study/'development_freeze_v3/freeze.json')",
        port="9920+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        client="[PYTHON,'-B',str(source/'scripts/tsc_template_task_development_client_v2.py'),'--study',str(study),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--model-identity',model,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]")
    for name,expression in changes.items():
        rr=[n for n in ast.walk(new) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)];assert len(rr)==1
        rr[0].value=ast.copy_location(ast.parse(expression,mode='eval').body,rr[0].value)
    count=0
    for n in ast.walk(new):
        if isinstance(n,ast.Assert):
            text=ast.unparse(n.test)
            if 'diagnostic_cell_complete' in text:n.test.comparators[0]=ast.Constant(value='template_task_development_complete');count+=1
            elif any(s in text for s in ['behavior_case_complete','manifest_request_complete','registration_control']):n.test.comparators[0]=ast.Constant(value=0);count+=1
    assert count==4
    left,right=deepcopy(old),deepcopy(new)
    for fn in (left,right):
        for n in ast.walk(fn):
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in changes for t in n.targets):n.value=ast.Constant(value='DECLARED_DISPATCH')
            if isinstance(n,ast.Assert) and any(s in ast.unparse(n.test) for s in ['diagnostic_cell_complete','template_task_development_complete','behavior_case_complete','manifest_request_complete','registration_control']):n.test.comparators[0]=ast.Constant(value='DECLARED_COMPLETION')
    assert ast.dump(left,include_attributes=False)==ast.dump(right,include_attributes=False)
    env=base.__dict__.copy();exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),str(base.__file__)+'[task-bearing-development]','exec'),env)
    return env['run_cell'],dict(parent_sha256=sha(Path(base.__file__)),changed_assignments=list(changes),changed_completion_assertions=count,other_AST_unchanged=True)

def main(args):
    root=args.root.resolve();study=root/STUDY;assert read(study/'development_exit_qwen_v2.json')['returncode']==1
    assert not (study/'cells/Qwen3-8B_r1/attempt1/responses.jsonl').exists(),'Never overwrite a scientific execution'
    assert sys.platform=='linux' and root.is_relative_to(base.DISK)
    if base.foreign_pids(base.resource_snapshot()):print('WAIT_FOR_FOREIGN_GPU');return 75
    frozen=study/'development_freeze_v3';assert sha(frozen/'freeze.json')==args.freeze_sha256
    freeze=read(frozen/'freeze.json')
    for row in freeze['files']:
        assert sha(root/row['path'])==sha(frozen/'source_snapshot'/row['path'])==row['sha256'],row['path']
    run,proof=adapted_cell();assert proof==freeze['worker_adapter_proof']
    base.validate_preflight(root/PARENT)
    alias=study/'preflight_v3'
    if not alias.exists():alias.symlink_to(root/PARENT/'preflight_v3',target_is_directory=True)
    assert alias.resolve()==(root/PARENT/'preflight_v3').resolve()
    receipt=study/'development_preflight_receipt_v3.json'
    if args.mode=='preflight':
        assert not receipt.exists() and not (study/'development_execution_state_v3.json').exists()
        assert read(study/'input_selection_complete_v2.json')['model_outputs_used']==0
        probe=import_probe(study)
        base.write(receipt,dict(status='PASS',actual_runtime_import_probe=probe,freeze_sha256=args.freeze_sha256,worker_adapter_proof=proof,
            reused_immutable_runtime_receipt_sha256=sha(root/PARENT/'preflight_v3/receipt_v1.json'),model_asset_stats_verified=True,
            all_tokenizer_shapes_verified=True,resource=base.resource_snapshot(),new_GPU_requests=0))
        print(json.dumps(dict(receipt_sha256=sha(receipt))));return 0
    assert args.receipt_sha256==sha(receipt)
    import fcntl
    with (study/'development_worker_v3.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=study/'development_execution_state_v3.json'
        if args.mode=='qwen':
            assert not path.exists();state=dict(status='RUNNING_QWEN',worker_pid=os.getpid(),completed_cells=[])
            jobs=[('Qwen3-8B',0)]
        else:
            state=read(path);assert state['status']=='AWAITING_QWEN_INDEPENDENT_AUDIT'
            audit=read(study/'development_Qwen_decision_v2.json');assert audit['invariants_pass'] and audit['eligible_families']
            assert state['completed_cells']==['cells/Qwen3-8B_r1/attempt2']
            state.update(status='RUNNING_OPTIONAL_MODELS',worker_pid=os.getpid());jobs=[('Mistral-7B-Instruct-v0.3',0),('Llama-3.1-8B-Instruct',1)]
        base.state(path,state);owned,stop,violation=set(),Event(),Event()
        monitor=Thread(target=resource_monitor,args=(study/('development_GPU_resources_'+args.mode+'_v3.jsonl'),owned,stop,violation),daemon=True);monitor.start()
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending=[]
                for model,lane in jobs:pending.append(pool.submit(run,root,study,model,1,lane,2 if model=='Qwen3-8B' else 1,owned));time.sleep(2)
                for future in pending:
                    relative=future.result();assert not violation.is_set();cell=study/relative
                    base.write(cell/'nested_completion_inventory_v1.json',dict(files=[dict(path=p.relative_to(cell).as_posix(),sha256=sha(p),bytes=p.stat().st_size)
                        for p in sorted(cell.rglob('*')) if p.is_file() and p.suffix in {'.json','.jsonl','.log'} and not any(x in {'cache','tmp'} for x in p.relative_to(cell).parts)]))
                    state['completed_cells'].append(relative);base.state(path,state)
            state.update(status='AWAITING_QWEN_INDEPENDENT_AUDIT' if args.mode=='qwen' else 'DEVELOPMENT_COMPLETE_PENDING_AUDIT',worker_pid=None);base.state(path,state)
        except BaseException as e:
            state.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(e).__name__,error_message=str(e));base.state(path,state);raise
        finally:stop.set();monitor.join(timeout=10)
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--mode',choices=['preflight','qwen','others'],required=True)
    p.add_argument('--freeze-sha256',required=True);p.add_argument('--receipt-sha256');raise SystemExit(main(p.parse_args()))
