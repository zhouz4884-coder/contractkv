"""Check additive backend imports, then exec the existing frozen v3 worker."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

STUDY=Path('results/tsc_revision_mechanism_controls_20261018')
FREEZE_SHA='7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff'
PYTHON='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
DISK=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def project_imports(path):
    out=set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node,ast.Import):out.update(x.name for x in node.names if x.name.startswith('scripts.'))
        if isinstance(node,ast.ImportFrom) and node.module:
            if node.module.startswith('scripts.'):out.add(node.module)
            elif node.level==1 and path.parent.name=='scripts':out.add('scripts.'+node.module)
        if isinstance(node,ast.Call) and node.args and isinstance(node.args[0],ast.Constant):
            value=node.args[0].value
            if isinstance(value,str) and value.startswith('scripts.') and (
                isinstance(node.func,ast.Name) and node.func.id=='__import__' or
                isinstance(node.func,ast.Attribute) and node.func.attr=='import_module'):
                out.add(value)
    return out


def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--dependency-freeze-sha256',required=True);p.add_argument('--check-only',action='store_true')
    args,rest=p.parse_known_args();root=args.root.resolve();study=root/STUDY;snapshot=study/'source_snapshot'
    assert sys.platform=='linux' and root.is_relative_to(DISK)
    freeze=study/'freeze_v3.json';assert sha(freeze)==FREEZE_SHA,'Original freeze_v3 changed'
    supplement=study/'backend_project_dependency_manifest_v1.json'
    assert sha(supplement)==args.dependency_freeze_sha256,'Wrong dependency supplement'
    extra=read(supplement);assert extra['original_freeze_v3_sha256']==FREEZE_SHA
    assert sha(Path(__file__))==extra['checked_entry_sha256']
    expected={str((snapshot/x['path']).resolve()):x['sha256'] for x in read(freeze)['files']}
    for x in extra['files']:
        path=(root/x['snapshot_path']).resolve();assert path.is_relative_to(snapshot)
        expected[str(path)]=x['sha256'];assert sha(path)==x['sha256']
    for path,digest in expected.items():assert sha(Path(path))==digest,path
    base=read(snapshot/'configs/tsc_revision_r1r_backend_commitment_v2.json')
    changed=read(snapshot/'configs/tsc_revision_r2_backend_commitment_v1.json')
    backend_expected={x['file']:x['after_sha256'] for x in base['source_files']}
    backend_expected.update({x['file']:x['after_sha256'] for x in changed['source_files']})
    backend=root/'third_party/vllm-contractkv-tsc-r2-margin';pending=set();backend_files=[]
    for rel,digest in backend_expected.items():
        path=backend/rel;assert sha(path)==digest,rel
        pending.update(project_imports(path));backend_files.append(dict(path=rel,sha256=digest))
    visited=set()
    while pending:
        name=pending.pop()
        if name in visited:continue
        path=(snapshot/Path(*name.split('.')).with_suffix('.py')).resolve()
        assert str(path) in expected,'Backend import is not frozen: '+name
        assert path.is_file() and sha(path)==expected[str(path)]
        visited.add(name);pending.update(project_imports(path)-visited)
    # No inference/runtime import: these project helpers are pure control code.
    sys.path.insert(0,str(snapshot))
    for name in sorted(visited):
        module=importlib.import_module(name);path=Path(module.__file__).resolve()
        assert path.is_relative_to(snapshot) and sha(path)==expected[str(path)],name
    mode='check' if args.check_only else (rest[rest.index('--mode')+1] if '--mode' in rest else 'unknown')
    cache=study/'driver_cache'/mode;tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
    for key in ('TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR'):os.environ.pop(key,None)
    os.environ.update(TMPDIR=str(tmp),XDG_CACHE_HOME=str(cache/'xdg'),HF_HOME=str(cache/'hf'),
        HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),
        TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),
        CUDA_CACHE_PATH=str(cache/'cuda'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',CUDA_VISIBLE_DEVICES='')
    receipt=dict(utc=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),mode=mode,
        original_freeze_sha256=FREEZE_SHA,dependency_freeze_sha256=sha(supplement),
        backend_sources=backend_files,imported_project_modules=sorted(visited),
        all_project_imports_frozen_and_loaded_from_snapshot=True,this_check_model_forwards=0,
        worker='scripts/tsc_revision_mechanism_worker_v3.py',no_worker_reimplementation=True)
    folder=study/'entry_checks_v1';folder.mkdir(exist_ok=True)
    with (folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+str(os.getpid())+'.json')).open('x') as f:
        json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt),flush=True)
    if args.check_only:return 0
    worker=root/'scripts/tsc_revision_mechanism_worker_v3.py'
    expected_worker=next(x['sha256'] for x in read(freeze)['files'] if x['path']=='scripts/tsc_revision_mechanism_worker_v3.py')
    assert sha(worker)==expected_worker
    os.execv(PYTHON,[PYTHON,'-B',str(worker),'--root',str(root),*rest])


if __name__=='__main__':raise SystemExit(main())
