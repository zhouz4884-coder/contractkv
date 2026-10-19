"""Preserve three completed cells; fail-closed repair for incomplete references.

Only HTTP ports and explicit client-wrapper execution change. The frozen
server, cases, margins, budget, scopes and runtime stay intact.
"""
from __future__ import annotations
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_mechanism_worker_v3 as original


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def adapt_execution(jobs):
    tree=ast.parse(Path(original.__file__).read_text(encoding='utf-8'))
    base=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_cell')
    changed=deepcopy(base)
    def assignment(fn,name):
        matches=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id==name for x in n.targets)]
        assert len(matches)==1;return matches[0]
    old=assignment(base,'port')
    assert ast.dump(old.value,include_attributes=False)==ast.dump(ast.parse('8990+lane',mode='eval').body,include_attributes=False)
    assignment(changed,'port').value=ast.copy_location(ast.parse('_port_override(model,repeat,lane)',mode='eval').body,old.value)
    old_client=deepcopy(assignment(base,'client').value)
    assignment(changed,'client').value=ast.copy_location(ast.Call(func=ast.Name(id='_client_wrapper',ctx=ast.Load()),
        args=[ast.Name(id=x,ctx=ast.Load()) for x in ['root','study','source']]+[old_client],keywords=[]),assignment(base,'client').value)
    before_control=deepcopy(base);after_control=deepcopy(changed)
    for name in ['port','client']:
        assignment(before_control,name).value=ast.Constant(value='EXPLICIT_EXECUTION_ADAPTER')
        assignment(after_control,name).value=ast.Constant(value='EXPLICIT_EXECUTION_ADAPTER')
    assert ast.dump(before_control,include_attributes=False)==ast.dump(after_control,include_attributes=False)
    lookup={(x['model'],x['repeat']):x for x in jobs}
    def port_for(model,repeat,lane):
        job=lookup[model,repeat];assert lane==job['lane'];return job['port']
    def client_for(root,study,source,command):
        assert command[:3]==[original.PYTHON,'-B',str(source/'scripts/tsc_revision_mechanism_live_v3.py')]
        return [original.PYTHON,'-B',str(root/'scripts/tsc_revision_mechanism_client_wrapper_v5.py'),
            '--snapshot-root',str(source),'--archived-client',command[2],
            '--repair-module',str(root/'scripts/tsc_revision_incomplete_reference_fix_v5.py'),
            '--repair-manifest',str(study/'incomplete_reference_continuation_v5.json'),*command[3:]]
    namespace=original.__dict__.copy();namespace.update(_port_override=port_for,_client_wrapper=client_for)
    module=ast.fix_missing_locations(ast.Module(body=[changed],type_ignores=[]))
    exec(compile(module,str(original.__file__)+'[port-and-client-fail-closed-adapter-v5]','exec'),namespace)
    proof=dict(only_changed_expressions=['unique HTTP port','explicit incomplete-reference client wrapper'],
        all_other_function_AST_identical=True,original_function_AST_sha256=hashlib.sha256(ast.dump(base,include_attributes=False).encode()).hexdigest(),
        adapted_function_AST_sha256=hashlib.sha256(ast.dump(changed,include_attributes=False).encode()).hexdigest())
    return namespace['run_cell'],proof


def validate(root,study,repair):
    assert sha(Path(__file__))==repair['continuation_source_sha256']
    assert sha(Path(original.__file__))==repair['unchanged_worker_v3_sha256']
    assert sha(root/'scripts/tsc_revision_incomplete_reference_fix_v5.py')==repair['repair_module_sha256']
    assert sha(root/'scripts/tsc_revision_mechanism_client_wrapper_v5.py')==repair['client_wrapper_sha256']
    assert sha(study/'freeze_v3.json')==repair['original_freeze_v3_sha256']
    assert sha(study/'preflight_v3/receipt_v1.json')==repair['existing_preflight_receipt_sha256']
    original.validate_preflight(study)
    for x in read(study/'freeze_v3.json')['files']:assert sha(study/'source_snapshot'/x['path'])==x['sha256']
    for x in repair['preserved_complete_files']:assert sha(study/x['path'])==x['sha256']
    for x in repair['preserved_failed_files']:assert sha(study/x['path'])==x['sha256']
    for rel in repair['preserved_completed_cells']:
        cell=study/rel;assert read(cell/'completion_v1.json')['status']=='complete'
        for x in read(cell/'completion_v1.json')['files']:assert sha(cell/x['path'])==x['sha256']
    assert len(repair['preserved_completed_cells'])==3 and len(repair['remaining_cells'])==6
    assert len({x['port'] for x in repair['remaining_cells']})==6


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--mode',choices=['check','execute'],required=True)
    p.add_argument('--execution-repair-sha256',required=True);p.add_argument('--check-receipt-sha256');a=p.parse_args()
    root=a.root.resolve();study=root/original.ROOT_REL;assert sys.platform=='linux' and root.is_relative_to(original.DISK)
    repair_path=study/'incomplete_reference_continuation_v5.json';assert sha(repair_path)==a.execution_repair_sha256
    repair=read(repair_path);validate(root,study,repair)
    # Invoke the existing source/import checker, not another model/tokenizer
    # preflight or worker. This is a zero-forward integrity check.
    command=[original.PYTHON,'-B',str(root/'scripts/tsc_revision_mechanism_checked_entry_v1.py'),'--root',str(root),
        '--dependency-freeze-sha256',repair['dependency_supplement_sha256'],'--check-only']
    subprocess.run(command,cwd=root,check=True)
    run_cell,proof=adapt_execution(repair['remaining_cells'])
    for job in repair['remaining_cells']:
        with socket.socket() as s:s.bind(('127.0.0.1',job['port']))
    folder=study/'incomplete_reference_continuation_v5_checks';receipt=folder/'receipt_v1.json'
    if not receipt.exists():
        folder.mkdir();original.write(receipt,dict(repair_sha256=a.execution_repair_sha256,source_sha256=sha(Path(__file__)),
            proof=proof,unique_ports=[x['port'] for x in repair['remaining_cells']],all_ports_bindable=True,
            completed_cells_preserved=3,failed_partial_records_preserved=63,remaining_new_cells=6,new_GPU_requests=0,
            no_model_runtime_copy_or_tokenizer_preflight_repeated=True))
    assert read(receipt)['repair_sha256']==a.execution_repair_sha256
    if a.mode=='check':print(json.dumps(dict(status='INCOMPLETE_REFERENCE_CONTINUATION_CHECKED',receipt_sha256=sha(receipt))));return 0
    assert a.check_receipt_sha256==sha(receipt),'Publish this exact infrastructure receipt before continuing'
    assert not original.foreign_pids(original.resource_snapshot()),'Wait for exclusive GPUs; never stop others'
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=dict(status='RUNNING',worker_pid=os.getpid(),attempt=3,completed_cells=list(repair['preserved_completed_cells']),
            repair_sha256=a.execution_repair_sha256,original_preflight_receipt_sha256=repair['existing_preflight_receipt_sha256'])
        original.state(study/'execution_state_v1.json',current);owned=set();jobs=repair['remaining_cells']
        try:
            for wave_number in sorted({x['wave'] for x in jobs}):
                wave=[x for x in jobs if x['wave']==wave_number];errors=[]
                assert len(wave)<=2 and len({x['lane'] for x in wave})==len(wave)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending=[]
                    for job in wave:
                        cell=study/'cells'/f"{job['model']}_r{job['repeat']}"/'attempt3'
                        assert not cell.exists(),'Never run a cell twice'
                        pending.append(pool.submit(run_cell,root,study,job['model'],job['repeat'],job['lane'],3,owned));time.sleep(2)
                    for f in pending:
                        try:
                            rel=f.result();current['completed_cells'].append(rel)
                            original.state(study/'execution_state_v1.json',current)
                        except BaseException as e:errors.append(e)
                if errors:raise errors[0]
            assert len(current['completed_cells'])==9
            for x in repair['preserved_complete_files']:assert sha(study/x['path'])==x['sha256']
            for x in repair['preserved_failed_files']:assert sha(study/x['path'])==x['sha256']
            current.update(status='MATRIX_COMPLETE_PENDING_ANALYSIS',worker_pid=None,
                failed_attempt_extra_business_records=63,formal_business_requests=855,
                observed_business_including_failed_attempt=918)
            original.state(study/'execution_state_v1.json',current)
        except BaseException as e:
            current.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(e).__name__,error_message=str(e))
            original.state(study/'execution_state_v1.json',current);raise
    return 0


if __name__=='__main__':raise SystemExit(main())
