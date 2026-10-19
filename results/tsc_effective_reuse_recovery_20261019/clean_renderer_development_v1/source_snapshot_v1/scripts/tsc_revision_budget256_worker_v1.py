"""Three bounded equal-budget conditions, reusing measured model/runtime assets."""
from __future__ import annotations
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

STUDY='results/tsc_mechanism_budget256_20261018'
BASE='results/tsc_revision_mechanism_controls_20261018'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def adapt():
    tree=ast.parse(Path(original.__file__).read_text(encoding='utf-8'))
    base=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_cell')
    changed=deepcopy(base)
    def assignment(fn,name):
        rr=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in n.targets)]
        assert len(rr)==1;return rr[0]
    replacements={
        'port':"9400+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        'source':"root/'results/tsc_revision_mechanism_controls_20261018/source_snapshot'",
        'policy_hash':"sha(study/'freeze_v1.json')",
        'client':"[PYTHON,'-B',str(root/'scripts/tsc_revision_budget256_client_v1.py'),'--project-root',str(root),'--freeze',str(study/'freeze_v1.json'),'--root',str(source),'--plan',str(study/'protocol_v1.json'),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]"}
    for key,value in replacements.items():
        node=assignment(changed,key);node.value=ast.copy_location(ast.parse(value,mode='eval').body,node.value)
    # Only two Manifest-specific completion assertions change to zero. The
    # behavior-case count remains 20; every other execution statement is kept.
    modified_assertions=0
    for node in ast.walk(changed):
        if not isinstance(node,ast.Assert):continue
        text=ast.unparse(node.test)
        if 'manifest_request_complete' in text or 'registration_control' in text:
            assert isinstance(node.test,ast.Compare) and len(node.test.comparators)==1
            node.test.comparators[0]=ast.Constant(value=0);modified_assertions+=1
    assert modified_assertions==2
    before=deepcopy(base);after=deepcopy(changed)
    for fn in (before,after):
        for key in replacements:assignment(fn,key).value=ast.Constant(value='DECLARED_BUDGET_CONDITION_ADAPTER')
        for node in ast.walk(fn):
            if isinstance(node,ast.Assert) and any(k in ast.unparse(node.test) for k in ['manifest_request_complete','registration_control']):
                node.test.comparators[0]=ast.Constant(value='NO_MANIFEST_IN_SUPPLEMENT')
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    proof=dict(changed_assignments=list(replacements),changed_manifest_count_assertions=2,
        remaining_function_AST_identical=True,
        adapted_function_AST_sha256=hashlib.sha256(ast.dump(changed,include_attributes=False).encode()).hexdigest())
    namespace=original.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[changed],type_ignores=[])),str(original.__file__)+'[budget256]', 'exec'),namespace)
    return namespace['run_cell'],proof


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=['check','execute'],required=True)
    p.add_argument('--freeze-sha256',required=True);p.add_argument('--check-receipt-sha256')
    a=p.parse_args();root=a.root.resolve();study=root/STUDY;base=root/BASE
    assert sys.platform=='linux' and root.is_relative_to(original.DISK)
    assert sha(study/'freeze_v1.json')==a.freeze_sha256
    freeze=read(study/'freeze_v1.json')
    for x in freeze['source_files']:assert sha(root/x['path'])==x['sha256'],x['path']
    assert sha(study/'protocol_v1.json')==freeze['protocol_sha256']
    assert sha(base/'preflight_v3/receipt_v1.json')==freeze['parent_preflight_receipt_sha256']
    assert sha(base/'freeze_v3.json')==freeze['parent_freeze_sha256']
    for x in read(base/'freeze_v3.json')['files']:
        assert sha(base/'source_snapshot'/x['path'])==x['sha256'],x['path']
    for x in read(base/'backend_project_dependency_manifest_v1.json')['files']:
        assert sha(root/x['snapshot_path'])==x['sha256'],x['snapshot_path']
    original.validate_preflight(base)  # stat/hash validation, never copy/profile again
    protocol=read(study/'protocol_v1.json');parent=read(base/'protocol_v1.json')
    for new,old in zip(protocol['behavior_cases'],parent['behavior_cases'],strict=True):
        assert new['output_budget']==256 and old['output_budget']==64
        assert {k:v for k,v in new.items() if k!='output_budget'}=={k:v for k,v in old.items() if k!='output_budget'}
    runtime_alias=study/'preflight_v3'
    if not runtime_alias.exists():runtime_alias.symlink_to(base/'preflight_v3',target_is_directory=True)
    assert runtime_alias.is_symlink() and runtime_alias.resolve()==(base/'preflight_v3').resolve()
    run_cell,proof=adapt();assert proof==freeze['worker_AST_proof']
    for port in [9400,9401,9402]:
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    receipt=study/'CPU_execution_check_v1.json'
    if not receipt.exists():original.write(receipt,dict(freeze_sha256=a.freeze_sha256,proof=proof,
        parent_preflight_reused=True,unchanged_120_prompt_shapes_fit_16K_with_256_budget=True,
        private_runtime_alias=str(runtime_alias),new_GPU_requests=0,all_unique_ports_bindable=True))
    if a.mode=='check':print(json.dumps(dict(status='CHECKED',receipt_sha256=sha(receipt))));return
    assert a.check_receipt_sha256==sha(receipt),'Publish actual Linux CPU receipt first'
    prior=read(base/'execution_state_v1.json')
    assert prior['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(prior['completed_cells'])==9
    assert (base/'raw_evidence_archive_manifest_v1.json').is_file(),'Archive the parent before new GPU work'
    assert not original.foreign_pids(original.resource_snapshot())
    import fcntl
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (study/'execution_state_v1.json').exists(),'No automatic rerun or overwrite'
        current=dict(status='RUNNING',worker_pid=os.getpid(),completed_cells=[],output_budget=256)
        original.state(study/'execution_state_v1.json',current);owned=set()
        try:
            # Same bounded two-lane orchestration as the parent. No capacity
            # or throughput claim is made from these trace-instrumented calls.
            jobs=[('Qwen3-8B',0),('Mistral-7B-Instruct-v0.3',1),('Llama-3.1-8B-Instruct',0)]
            for start in (0,2):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending=[]
                    for model,lane in jobs[start:start+2]:
                        pending.append(pool.submit(run_cell,root,study,model,1,lane,1,owned));time.sleep(2)
                    for f in pending:
                        current['completed_cells'].append(f.result());original.state(study/'execution_state_v1.json',current)
            current.update(status='MATRIX_COMPLETE_PENDING_ANALYSIS',worker_pid=None,formal_business_requests=240)
            original.state(study/'execution_state_v1.json',current)
        except BaseException as error:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error))
            original.state(study/'execution_state_v1.json',current);raise


if __name__=='__main__':main()
