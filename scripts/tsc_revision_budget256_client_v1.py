"""Run all frozen behavior cases at 256 tokens; no repeated Manifest trial.

The original collector's setup, generation, qualification and full behavior
loop are retained as the same AST. Only the subsequent Manifest section is
omitted and the terminal count assertion is adjusted to behavior-only work.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def behavior_function(source):
    tree=ast.parse(source.read_text(encoding='utf-8'))
    original=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run')
    cut=next(i for i,n in enumerate(original.body) if isinstance(n,ast.Assign)
             and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name)
             and n.value.func.id=='binding_functions')
    prefix=deepcopy(original.body[:cut])
    assert isinstance(prefix[-1],ast.For), 'Expected the complete unchanged behavior loop'
    tail=ast.parse("""
assert counts['business']==len(plan['behavior_cases'])*4==80
assert counts.get('verification',0)<=20
record(dict(event='diagnostic_cell_complete',counts=counts,
    diagnostic_client_wall_s=time.perf_counter()-started,
    all_cases_preserved=True,service_performance_claim=False,
    output_budget_condition=256,manifest_not_repeated=True))
print(json.dumps(dict(cell=args.cell_id,counts=counts)),flush=True)
""").body
    changed=deepcopy(original);changed.body=prefix+tail
    assert ast.dump(ast.Module(body=prefix,type_ignores=[]),include_attributes=False)==ast.dump(
        ast.Module(body=original.body[:cut],type_ignores=[]),include_attributes=False)
    proof=dict(unchanged_setup_and_complete_behavior_loop_AST=True,
        removed_section='Manifest only (already measured in parent study)',
        prefix_AST_sha256=hashlib.sha256(ast.dump(ast.Module(body=prefix,type_ignores=[]),include_attributes=False).encode()).hexdigest())
    return changed,proof


def run(args):
    freeze=json.loads(args.freeze.read_text(encoding='utf-8'))
    root=args.project_root.resolve();base=root/freeze['parent_study']
    snapshot=base/'source_snapshot'
    for x in freeze['source_files']:
        assert sha(root/x['path'])==x['sha256'],x['path']
    collector=snapshot/'scripts/tsc_revision_mechanism_live_v3.py'
    assert sha(collector)==freeze['parent_collector_sha256']
    assert sha(base/'incomplete_reference_continuation_v5.json')==freeze['parent_repair_manifest_sha256']
    sys.path.insert(0,str(snapshot))
    spec=importlib.util.spec_from_file_location('frozen_mechanism_collector_budget256',collector)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from scripts.contractkv_verifier import VerificationIncomplete
    from scripts.tsc_revision_r2_admission import SingleShotRegistrar
    fixpath=root/'scripts/tsc_revision_incomplete_reference_fix_v5.py'
    spec=importlib.util.spec_from_file_location('frozen_incomplete_fix_budget256',fixpath)
    fix=importlib.util.module_from_spec(spec);spec.loader.exec_module(fix)
    original=SingleShotRegistrar.register
    SingleShotRegistrar.register=fix.repaired_register(original,VerificationIncomplete)
    changed,proof=behavior_function(collector)
    assert proof==freeze['client_AST_proof']
    namespace=module.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[changed],type_ignores=[])),str(collector)+'[behavior-only-budget256]', 'exec'),namespace)
    try:
        namespace['run'](args)
    finally:
        SingleShotRegistrar.register=original


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--project-root',type=Path,required=True)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--identity',type=Path,required=True)
    p.add_argument('--base-url',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--cell-id',required=True)
    p.add_argument('--policy-hash',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=300)
    run(p.parse_args())
