"""Three fresh-model real RepoBench diagnostics, preserving production policy."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_mechanism_worker_v3 as original
from scripts.tsc_revision_budget256_worker_v2 import portable_AST_sha256

STUDY='results/tsc_real_repobench_mechanism_20261018'
BASE='results/tsc_revision_mechanism_controls_20261018'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def adapt():
    tree=ast.parse(Path(original.__file__).read_text(encoding='utf-8'))
    old=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_cell')
    changed=deepcopy(old)
    def assign(fn,name):
        matches=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in n.targets)]
        assert len(matches)==1;return matches[0]
    replacements=dict(port="9500+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        source="root/'results/tsc_revision_mechanism_controls_20261018/source_snapshot'",policy_hash="sha(study/'freeze_v1.json')",
        client="[PYTHON,'-B',str(root/'scripts/tsc_revision_real_repo_client_v1.py'),'--project-root',str(root),'--freeze',str(study/'freeze_v1.json'),'--root',str(source),'--plan',str(study/'protocol_v1.json'),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]")
    for key,expression in replacements.items():
        n=assign(changed,key);n.value=ast.copy_location(ast.parse(expression,mode='eval').body,n.value)
    markers={'behavior_case_complete':6,'manifest_request_complete':0,'registration_control':0};edits=0
    for n in ast.walk(changed):
        if isinstance(n,ast.Assert):
            for key,value in markers.items():
                if key in ast.unparse(n.test):n.test.comparators[0]=ast.Constant(value=value);edits+=1
    assert edits==3
    before=deepcopy(old);after=deepcopy(changed)
    for fn in [before,after]:
        for key in replacements:assign(fn,key).value=ast.Constant(value='DECLARED_REAL_REPO_EXECUTION')
        for n in ast.walk(fn):
            if isinstance(n,ast.Assert) and any(k in ast.unparse(n.test) for k in markers):
                n.test.comparators[0]=ast.Constant(value='DECLARED_REAL_REPO_COUNTS')
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    proof=dict(changed_assignments=list(replacements),changed_completion_count_assertions=3,
        all_other_function_AST_identical=True,adapted_function_AST_sha256=portable_AST_sha256(changed))
    space=original.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[changed],type_ignores=[])),str(original.__file__)+'[real-repository-diagnostic]', 'exec'),space)
    return space['run_cell'],proof


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=['check','execute'],required=True)
    p.add_argument('--freeze-sha256',required=True);p.add_argument('--check-receipt-sha256')
    a=p.parse_args();root=a.root.resolve();study=root/STUDY;base=root/BASE
    assert sys.platform=='linux' and root.is_relative_to(original.DISK)
    assert sha(study/'freeze_v1.json')==a.freeze_sha256;freeze=read(study/'freeze_v1.json')
    for x in freeze['source_files']:assert sha(root/x['path'])==x['sha256'],x['path']
    assert sha(study/'protocol_v1.json')==freeze['protocol_sha256']
    assert sha(base/'preflight_v3/receipt_v1.json')==freeze['parent_preflight_receipt_sha256']
    assert sha(base/'freeze_v3.json')==freeze['parent_freeze_sha256']
    original.validate_preflight(base)
    for x in read(base/'freeze_v3.json')['files']:assert sha(base/'source_snapshot'/x['path'])==x['sha256']
    for x in read(base/'backend_project_dependency_manifest_v1.json')['files']:
        assert sha(root/x['snapshot_path'])==x['sha256']
    protocol=read(study/'protocol_v1.json');assert len(protocol['behavior_cases'])==6
    assert len({x['source_group'] for x in protocol['behavior_cases']})==3
    assert {x['diagnostic_layout_level'] for x in protocol['behavior_cases']}=={'L0','L3'}
    assert all(x['output_budget']==384 and x['output_contract']=='one_python_statement' for x in protocol['behavior_cases'])
    assert sha(study/'inputs_v1/CPU_prompt_shapes_v1.jsonl')==protocol['CPU_prompt_shapes_sha256']
    alias=study/'preflight_v3'
    if not alias.exists():alias.symlink_to(base/'preflight_v3',target_is_directory=True)
    assert alias.is_symlink() and alias.resolve()==(base/'preflight_v3').resolve()
    run_cell,proof=adapt();assert proof==freeze['worker_AST_proof']
    for port in [9500,9501,9502]:
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    receipt=study/'CPU_execution_check_v1.json'
    if not receipt.exists():original.write(receipt,dict(freeze_sha256=a.freeze_sha256,proof=proof,
        existing_model_runtime_preflight_reused=True,new_source_shapes_checked_without_model_forward=True,
        private_L0_L3_diagnostic_not_production_eligibility=True,new_GPU_requests=0))
    if a.mode=='check':print(json.dumps(dict(status='CHECKED',receipt_sha256=sha(receipt))));return
    assert a.check_receipt_sha256==sha(receipt),'Publish the actual Linux receipt first'
    budget=root/'results/tsc_mechanism_budget256_20261018'
    assert read(budget/'formal_budget_v2_exit_v1.json')['returncode']==0
    assert read(budget/'execution_state_v1.json')['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS'
    assert (base/'raw_evidence_archive_manifest_v1.json').exists()
    assert not original.foreign_pids(original.resource_snapshot())
    import fcntl
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (study/'execution_state_v1.json').exists(),'Monitor an existing execution instead'
        current=dict(status='RUNNING',worker_pid=os.getpid(),completed_cells=[],production_family_policy_unchanged=True)
        original.state(study/'execution_state_v1.json',current);owned=set()
        try:
            jobs=[('Qwen3-8B',0),('Mistral-7B-Instruct-v0.3',1),('Llama-3.1-8B-Instruct',0)]
            for start in [0,2]:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending=[]
                    for model,lane in jobs[start:start+2]:
                        pending.append(pool.submit(run_cell,root,study,model,1,lane,1,owned));time.sleep(2)
                    for f in pending:
                        current['completed_cells'].append(f.result());original.state(study/'execution_state_v1.json',current)
            current.update(status='MATRIX_COMPLETE_PENDING_ANALYSIS',worker_pid=None,business_requests=72)
            original.state(study/'execution_state_v1.json',current)
        except BaseException as error:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error))
            original.state(study/'execution_state_v1.json',current);raise


if __name__=='__main__':main()
