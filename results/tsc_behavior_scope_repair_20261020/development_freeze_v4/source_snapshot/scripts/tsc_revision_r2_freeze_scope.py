"""Freeze explicit runtime/data files and their static local Python import closure."""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_scope(root,base,protocol_path,seeds,extra):
    root=root.resolve();base=base.resolve();target=base/'freeze.json'
    if target.exists():raise RuntimeError('Preserve existing prospective freeze')
    files=set(seeds);queue=list(seeds)
    while queue:
        name=queue.pop();path=root/name
        if path.suffix!='.py':continue
        tree=ast.parse(path.read_text(encoding='utf-8'));modules=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):modules.extend(alias.name for alias in node.names)
            if isinstance(node,ast.ImportFrom) and node.level==0 and node.module:
                modules.append(node.module)
                if node.module=='scripts':modules.extend('scripts.'+alias.name for alias in node.names)
        for module in modules:
            if not module.startswith('scripts.'):continue
            candidate=Path(*module.split('.')).with_suffix('.py').as_posix()
            if (root/candidate).is_file() and candidate not in files:files.add(candidate);queue.append(candidate)
    files.add(Path(__file__).resolve().relative_to(root).as_posix())
    base.mkdir(parents=True,exist_ok=True);items=[]
    for name in sorted(files):
        path=root/name;saved=base/'source_snapshot'/name
        saved.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,saved)
        items.append({'path':name,'sha256':sha(path)})
    record={'schema_version':'tsc-r2.prospective-scope-freeze.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'protocol':json.loads(protocol_path.read_text(encoding='utf-8')),'files':items,
            'static_local_import_closure_not_line_execution_trace':True,**extra}
    with target.open('x',encoding='utf-8') as out:out.write(json.dumps(record,indent=2)+'\n')
    (base/'source_checksums.sha256').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in items),encoding='utf-8')
    return {'freeze_sha256':sha(target),'files':len(items)}
