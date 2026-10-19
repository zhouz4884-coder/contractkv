"""Bounded metadata renderer control; reuse immutable serving runtime."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Event, Thread
import time
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_mechanism_worker_v3 as base
from scripts.tsc_revision_final_raw_worker_v1 import resource_monitor

STUDY = Path('results/tsc_effective_reuse_recovery_20261019/clean_renderer_development_v1')
PARENT = Path('results/tsc_revision_mechanism_controls_20261018')

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def adapted_cell():
    old = next(n for n in ast.parse(Path(base.__file__).read_text(encoding='utf-8')).body
               if isinstance(n, ast.FunctionDef) and n.name == 'run_cell')
    new = deepcopy(old)
    replacements = dict(source="study/'source_snapshot_v1'", policy_hash="sha(study/'freeze_v1.json')",
        port="9900+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        client="[PYTHON,'-B',str(source/'scripts/tsc_effective_renderer_client_v1.py'),'--study-root',str(study),'--source-root',str(source),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]")
    for key, expression in replacements.items():
        nodes = [n for n in ast.walk(new) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == key for t in n.targets)]
        assert len(nodes) == 1
        nodes[0].value = ast.copy_location(ast.parse(expression, mode='eval').body, nodes[0].value)
    changed = 0
    for n in ast.walk(new):
        if isinstance(n, ast.Assert):
            text = ast.unparse(n.test)
            if 'diagnostic_cell_complete' in text:
                n.test.comparators[0] = ast.Constant(value='renderer_development_cell_complete'); changed += 1
            elif any(s in text for s in ['behavior_case_complete', 'manifest_request_complete', 'registration_control']):
                n.test.comparators[0] = ast.Constant(value=0); changed += 1
    assert changed == 4
    left, right = deepcopy(old), deepcopy(new)
    for fn in (left, right):
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in replacements for t in n.targets):
                n.value = ast.Constant(value='DECLARED_RENDERER_DISPATCH')
            if isinstance(n, ast.Assert) and any(s in ast.unparse(n.test) for s in ['diagnostic_cell_complete', 'renderer_development_cell_complete', 'behavior_case_complete', 'manifest_request_complete', 'registration_control']):
                n.test.comparators[0] = ast.Constant(value='DECLARED_COMPLETION')
    assert ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)
    namespace = base.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[])),
                 str(base.__file__) + '[renderer-control]', 'exec'), namespace)
    return namespace['run_cell'], dict(parent_sha256=sha(Path(base.__file__)), changed_assignments=list(replacements),
                                     changed_completion_assertions=changed, other_cell_AST_identical=True)

def shapes(root, study):
    from transformers import AutoTokenizer
    from types import SimpleNamespace
    from scripts.tsc_effective_renderer_client_v1 import renderer_context
    from scripts.tsc_revision_r1r_live import prepare
    from scripts.phase22_llama_layout_ladder import layout_for_level
    from scripts.phase17_live_common import digest
    generation = read(study/'source_snapshot_v1/configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json')
    samples = [json.loads(s) for s in (study/'repo_development_inputs_v1.jsonl').read_text().splitlines()]
    output = []
    for model in read(study/'protocol_v1.json')['models']:
        tokenizer = AutoTokenizer.from_pretrained(str(base.DISK/'models'/model), local_files_only=True)
        args = SimpleNamespace(protocol=generation, experiment='free-generation', output_budget=0,
                               model_identity=model, policy_hash='CPU-renderer-preflight')
        for kind in ('current', 'clean'):
            with renderer_context(kind) as renderer:
                for source in samples:
                    sample = deepcopy(source)
                    sample['shared_template_id'] = sample['revision_session_id']
                    sample['revision_session_id'] += '-tenant00'
                    case, raw, _, budget, _ = prepare(args, sample, 0)
                    assert budget == 384
                    for level in ('L0', 'L1', 'L2', 'L3'):
                        order = layout_for_level(case, level, generation['layout']['ladder'])['topological_order']
                        messages = raw if level == 'L0' else [raw[0], dict(role='user', content=renderer(order, case['segments']))]
                        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
                        assert ids and len(ids) + budget + 1 <= 16384
                        output.append(dict(model=model, renderer=kind, source_group=source['revision_source_group'],
                            level=level, prompt_tokens=len(ids), output_budget=budget, prompt_ids_sha256=digest(ids)))
    assert len(output) == 48
    base.write(study/'CPU_shapes_v1.json', dict(shapes=output, all_fit=True, new_GPU_requests=0))

def main(args):
    root=args.root.resolve(); study=root/STUDY; parent=root/PARENT
    assert sys.platform == 'linux' and root.is_relative_to(base.DISK)
    previous=root/'results/tsc_effective_reuse_recovery_20261019/development_worker_exit_v2.json'
    assert read(previous)['returncode'] == 0
    assert not base.foreign_pids(base.resource_snapshot()), 'GPU belongs to another task; do not launch'
    freeze=read(study/'freeze_v1.json'); assert sha(study/'freeze_v1.json') == args.freeze_sha256
    for row in freeze['files']: assert sha(root/row['path']) == row['sha256'], row['path']
    cell,proof=adapted_cell(); assert proof == freeze['worker_adapter_proof']
    base.validate_preflight(parent)
    alias=study/'preflight_v3'
    if not alias.exists(): alias.symlink_to(parent/'preflight_v3', target_is_directory=True)
    assert alias.resolve() == (parent/'preflight_v3').resolve()
    receipt=study/'preflight_receipt_v1.json'
    if args.mode == 'preflight':
        assert not receipt.exists() and not (study/'execution_state_v1.json').exists()
        shapes(root,study)
        base.write(receipt, dict(status='PASS', freeze_sha256=args.freeze_sha256, worker_proof=proof,
            actual_shapes_sha256=sha(study/'CPU_shapes_v1.json'), parent_runtime_sha256=sha(parent/'preflight_v3/receipt_v1.json'),
            resource=base.resource_snapshot(), no_GPU_inference=True, source_sha256=sha(Path(__file__))))
        print(json.dumps(dict(receipt_sha256=sha(receipt)))); return 0
    assert args.receipt_sha256 == sha(receipt)
    assert read(receipt)['actual_shapes_sha256'] == sha(study/'CPU_shapes_v1.json')
    import fcntl
    with (study/'worker_v1.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        statepath=study/'execution_state_v1.json'; assert not statepath.exists()
        state=dict(status='RUNNING',worker_pid=os.getpid(),completed_cells=[],planned_cells=3)
        base.state(statepath,state)
        owned,stop,violation=set(),Event(),Event()
        monitor=Thread(target=resource_monitor,args=(study/'GPU_resources_v1.jsonl',owned,stop,violation),daemon=True); monitor.start()
        try:
            jobs=[('Qwen3-8B',0),('Mistral-7B-Instruct-v0.3',1),('Llama-3.1-8B-Instruct',0)]
            for start in (0,2):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending=[]
                    for model,lane in jobs[start:start+2]:
                        pending.append(pool.submit(cell,root,study,model,1,lane,1,owned)); time.sleep(2)
                    for future in pending:
                        relative=future.result(); assert not violation.is_set()
                        target=study/relative
                        base.write(target/'nested_completion_inventory_v1.json',dict(files=[dict(path=p.relative_to(target).as_posix(),sha256=sha(p),bytes=p.stat().st_size)
                            for p in sorted(target.rglob('*')) if p.is_file() and p.suffix in {'.json','.jsonl','.log'}
                            and not any(s in {'cache','tmp'} for s in p.relative_to(target).parts)]))
                        state['completed_cells'].append(relative); base.state(statepath,state)
            state.update(status='COMPLETE_PENDING_RENDERER_DECISION',worker_pid=None); base.state(statepath,state)
        except BaseException as error:
            state.update(status='FAILURE_PRESERVED',worker_pid=None,error_type=type(error).__name__,error_message=str(error));base.state(statepath,state);raise
        finally:
            stop.set();monitor.join(timeout=10)
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--mode',choices=['preflight','execute'],required=True)
    parser.add_argument('--freeze-sha256',required=True)
    parser.add_argument('--receipt-sha256')
    raise SystemExit(main(parser.parse_args()))
