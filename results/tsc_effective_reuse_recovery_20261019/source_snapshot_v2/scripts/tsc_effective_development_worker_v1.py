"""Reuse isolated V5 infrastructure for three bounded development cells."""
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

STUDY = Path('results/tsc_effective_reuse_recovery_20261019')
PARENT = Path('results/tsc_revision_mechanism_controls_20261018')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))


def adapted_cell():
    old = next(n for n in ast.parse(Path(base.__file__).read_text(encoding='utf-8')).body
               if isinstance(n, ast.FunctionDef) and n.name == 'run_cell')
    new = deepcopy(old)
    replacements = dict(source="study/'source_snapshot_v1'", policy_hash="sha(study/'freeze_development_v1.json')",
        port="9890+['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'].index(model)",
        client="[PYTHON,'-B',str(source/'scripts/tsc_effective_development_client_v1.py'),'--study-root',str(study),'--source-root',str(source),'--identity',str(study/'preflight_v3'/('identity_'+model+'.json')),'--base-url',f'http://127.0.0.1:{port}/v1','--model',served,'--cell-id',name,'--policy-hash',policy_hash,'--output',str(cell/'responses.jsonl')]")
    for key, expr in replacements.items():
        found = [n for n in ast.walk(new) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == key for t in n.targets)]
        assert len(found) == 1
        found[0].value = ast.copy_location(ast.parse(expr, mode='eval').body, found[0].value)
    changed = 0
    for n in ast.walk(new):
        if isinstance(n, ast.Assert):
            text = ast.unparse(n.test)
            if 'diagnostic_cell_complete' in text:
                n.test.comparators[0] = ast.Constant(value='effective_development_cell_complete')
                changed += 1
            elif any(s in text for s in ['behavior_case_complete', 'manifest_request_complete', 'registration_control']):
                n.test.comparators[0] = ast.Constant(value=0)
                changed += 1
    assert changed == 4
    left, right = deepcopy(old), deepcopy(new)
    for fn in [left, right]:
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in replacements for t in n.targets):
                n.value = ast.Constant(value='DECLARED_DEVELOPMENT_DISPATCH')
            if isinstance(n, ast.Assert) and any(s in ast.unparse(n.test) for s in [
                'diagnostic_cell_complete', 'effective_development_cell_complete', 'behavior_case_complete', 'manifest_request_complete', 'registration_control']):
                n.test.comparators[0] = ast.Constant(value='DECLARED_DEVELOPMENT_COMPLETION')
    assert ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)
    space = base.__dict__.copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new], type_ignores=[])),
                 str(base.__file__) + '[effective-reuse-development]', 'exec'), space)
    return space['run_cell'], dict(parent_sha256=sha(Path(base.__file__)), changed_assignments=list(replacements),
                                   changed_completion_assertions=4, all_other_cell_AST_identical=True)


def main(args):
    root = args.root.resolve()
    study, parent = root / STUDY, root / PARENT
    assert sys.platform == 'linux' and root.is_relative_to(base.DISK)
    if base.foreign_pids(base.resource_snapshot()):
        print(json.dumps(dict(status='WAIT_FOR_UNRELATED_GPU', new_GPU_requests=0)))
        return 75
    freeze = read(study / 'freeze_development_v1.json')
    assert sha(study / 'freeze_development_v1.json') == args.freeze_sha256
    for row in freeze['files']:
        assert sha(root / row['path']) == row['sha256'], row['path']
    run_cell, proof = adapted_cell()
    assert proof == freeze['worker_adapter_proof']
    base.validate_preflight(parent)
    assert sha(parent / 'preflight_v3/receipt_v1.json') == freeze['parent_runtime_receipt_sha256']
    alias = study / 'preflight_v3'
    if not alias.exists():
        alias.symlink_to(parent / 'preflight_v3', target_is_directory=True)
    assert alias.resolve() == (parent / 'preflight_v3').resolve()
    receipt = study / 'development_preflight_receipt_v1.json'
    if args.mode == 'preflight':
        assert not receipt.exists() and not (study / 'development_execution_state_v1.json').exists()
        base.write(receipt, dict(status='PASS', freeze_sha256=args.freeze_sha256, worker_proof=proof,
            model_stats_and_immutable_runtime_verified=True, no_runtime_or_model_copy=True,
            resource=base.resource_snapshot(), new_GPU_requests=0))
        print(json.dumps(dict(status='PREFLIGHT_PASS', receipt_sha256=sha(receipt))))
        return 0
    assert args.receipt_sha256 == sha(receipt), 'Publish the actual receipt before any new model output'
    import fcntl
    with (study / 'development_worker.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = study / 'development_execution_state_v1.json'
        assert not state_path.exists(), 'Observe existing state; do not restart'
        state = dict(status='RUNNING', worker_pid=os.getpid(), completed_cells=[], planned_cells=3)
        base.state(state_path, state)
        owned, stop, violation = set(), Event(), Event()
        monitor = Thread(target=resource_monitor, args=(study / 'development_GPU_resources_v1.jsonl', owned, stop, violation), daemon=True)
        monitor.start()
        try:
            jobs = [('Qwen3-8B', 0), ('Mistral-7B-Instruct-v0.3', 1), ('Llama-3.1-8B-Instruct', 0)]
            for start in range(0, 3, 2):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending = []
                    for model, lane in jobs[start:start + 2]:
                        pending.append(pool.submit(run_cell, root, study, model, 1, lane, 1, owned))
                        time.sleep(2)
                    for future in pending:
                        relative = future.result()
                        assert not violation.is_set(), 'Foreign GPU activity; preserve all results'
                        cell = study / relative
                        base.write(cell / 'nested_completion_inventory_v1.json', dict(files=[
                            dict(path=p.relative_to(cell).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
                            for p in sorted(cell.rglob('*')) if p.is_file() and p.suffix in {'.json', '.jsonl', '.log'}
                            and not any(x in {'cache', 'tmp'} for x in p.relative_to(cell).parts)]))
                        state['completed_cells'].append(relative)
                        base.state(state_path, state)
            state.update(status='COMPLETE_PENDING_DEVELOPMENT_DECISION', worker_pid=None)
            base.state(state_path, state)
        except BaseException as error:
            state.update(status='FAILURE_PRESERVED', worker_pid=None, error_type=type(error).__name__, error_message=str(error))
            base.state(state_path, state)
            raise
        finally:
            stop.set()
            monitor.join(timeout=10)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--mode', choices=['preflight', 'execute'], required=True)
    p.add_argument('--freeze-sha256', required=True)
    p.add_argument('--receipt-sha256')
    raise SystemExit(main(p.parse_args()))
