"""Bounded9 fresh-engine transport controls, reusing immutable V5 runtime."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_mechanism_worker_v3 as base

STUDY = Path('results/tsc_authorization_task_repair_20261019')
PARENT = Path('results/tsc_revision_mechanism_controls_20261018')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))


def adapted_cell():
    tree = ast.parse(Path(base.__file__).read_text(encoding='utf-8'))
    old = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_cell')
    new = deepcopy(old)
    replacements = dict(source="study/'source_snapshot_v2'", port="9800+repeat*4+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        policy_hash="sha(study/'freeze_v2.json')",
        client="[PYTHON,'-B',str(source/'scripts/tsc_repair_authorized_client_v2.py'),'--source-root',str(source),'--plan',str(study/'protocol_v2.json'),'--cases',str(study/'inputs_v1/cases_by_model_v1.json'),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]")
    for key, value in replacements.items():
        matches = [n for n in ast.walk(new) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets)]
        assert len(matches)==1
        matches[0].value=ast.copy_location(ast.parse(value,mode='eval').body,matches[0].value)
    replaced = 0
    for n in ast.walk(new):
        if isinstance(n,ast.Assert):
            text=ast.unparse(n.test)
            if 'diagnostic_cell_complete' in text:
                n.test.comparators[0]=ast.Constant(value='repair_cell_complete');replaced+=1
            elif any(t in text for t in ('behavior_case_complete','manifest_request_complete','registration_control')):
                n.test.comparators[0]=ast.Constant(value=0);replaced+=1
    assert replaced==4
    before,after=deepcopy(old),deepcopy(new)
    for fn in (before,after):
        for n in ast.walk(fn):
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in replacements for t in n.targets):
                n.value=ast.Constant(value='DECLARED_REPAIR_EXECUTION')
            if isinstance(n,ast.Assert) and any(t in ast.unparse(n.test) for t in ('diagnostic_cell_complete','repair_cell_complete','behavior_case_complete','manifest_request_complete','registration_control')):
                n.test.comparators[0]=ast.Constant(value='DECLARED_REPAIR_COMPLETION')
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    space=base.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),
                 str(base.__file__)+'[authorized-transport-cell]', 'exec'),space)
    proof=dict(parent_source_sha256=sha(Path(base.__file__)), changed_assignments=list(replacements),
               changed_completion_assertions=4, all_other_cell_orchestration_AST_identical=True)
    return space['run_cell'], proof


def main(args):
    root=args.root.resolve();study=root/STUDY;parent=root/PARENT
    assert sys.platform=='linux' and root.is_relative_to(base.DISK)
    resource=base.resource_snapshot()
    if base.foreign_pids(resource):
        print(json.dumps(dict(status='WAIT_FOR_FOREIGN_GPU',new_GPU_requests=0)))
        return 75
    freeze=read(study/'freeze_v2.json')
    assert sha(study/'freeze_v2.json')==args.freeze_sha256
    for row in freeze['files']:
        assert sha(root/row['path'])==row['sha256'],row['path']
    run_cell,proof=adapted_cell()
    assert proof==freeze['worker_adapter_proof']
    if args.mode=='check':
        print(json.dumps(dict(status='FREE',source_and_freeze_checked=True,new_GPU_requests=0)))
        return 0
    # Reuse the actual unchanged runtime and full model SHA registry, with new
    # stat/runtime checks. Never copy weights or modify that runtime.
    receipt=parent/'preflight_v3/receipt_v1.json'
    base.validate_preflight(parent)
    assert sha(receipt)==freeze['parent_runtime_receipt_sha256']
    alias=study/'preflight_v3'
    if not alias.exists(): alias.symlink_to(parent/'preflight_v3',target_is_directory=True)
    assert alias.is_symlink() and alias.resolve()==(parent/'preflight_v3').resolve()
    preflight=study/'repair_preflight_receipt_v2.json'
    if args.mode=='preflight':
        assert not preflight.exists() and not (study/'execution_state_v2.json').exists()
        base.write(preflight,dict(status='PASS',freeze_sha256=args.freeze_sha256,worker_proof=proof,
            original_models_stat_and_runtime_match=True,parent_runtime_receipt_sha256=sha(receipt),
            CPU_inputs=sha(study/'inputs_v1/cases_by_model_v1.json'),resource=resource,
            new_GPU_requests=0,runtime_mutations=0,full_weight_hash_or_runtime_copy_repeated=False))
        print(json.dumps(dict(status='PREFLIGHT_PASS',receipt_sha256=sha(preflight))))
        return 0
    assert args.preflight_receipt_sha256==sha(preflight),'Publish the actual preflight receipt before GPU execution'
    assert read(preflight)['freeze_sha256']==args.freeze_sha256
    import fcntl
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state_path=study/'execution_state_v2.json'
        assert not state_path.exists(),'Observe an existing worker; never launch a duplicate'
        state=dict(status='RUNNING',worker_pid=os.getpid(),completed_cells=[],planned_cells=9)
        base.state(state_path,state);owned=set()
        jobs=[('Qwen3-8B',1,0),('Mistral-7B-Instruct-v0.3',1,1),
              ('Llama-3.1-8B-Instruct',1,0),('Qwen3-8B',2,1),
              ('Mistral-7B-Instruct-v0.3',2,0),('Llama-3.1-8B-Instruct',2,1),
              ('Qwen3-8B',3,0),('Mistral-7B-Instruct-v0.3',3,1),('Llama-3.1-8B-Instruct',3,0)]
        try:
            for start in range(0,len(jobs),2):
                assert not base.foreign_pids(base.resource_snapshot(),owned)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending=[]
                    for model,repeat,lane in jobs[start:start+2]:
                        pending.append(pool.submit(run_cell,root,study,model,repeat,lane,1,owned));time.sleep(2)
                    for future in pending:
                        state['completed_cells'].append(future.result());base.state(state_path,state)
            assert len(state['completed_cells'])==9
            state.update(status='MATRIX_COMPLETE_PENDING_ANALYSIS',worker_pid=None,
                         actual_business_requests=828,no_additional_GPU_cells_planned=True)
            base.state(state_path,state)
        except BaseException as error:
            state.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error))
            base.state(state_path,state);raise
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=['check','preflight','execute'],required=True)
    p.add_argument('--freeze-sha256',required=True);p.add_argument('--preflight-receipt-sha256')
    raise SystemExit(main(p.parse_args()))
