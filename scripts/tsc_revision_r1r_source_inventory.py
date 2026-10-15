"""Record non-test entrypoints, imported helpers and frozen runtime identities."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root.resolve()
    entries=sorted((root/'scripts').glob('*tsc_revision_r1r*.py'))+sorted((root/'scripts').glob('run_tsc_revision_r1r*.sh'))
    pending=list(entries); roles={path:'entrypoint_or_analysis' for path in entries}; used=set()
    freeze=json.loads((root/'results/tsc_revision_r1r/validation/freeze_v1.json').read_text())
    for item in freeze['files']:
        if item['path'].startswith('third_party/'):
            path=root/item['path']; pending.append(path); roles[path]='actual_serving_engine_source'
            if sha(path)!=item['sha256']: raise RuntimeError('Runtime hash changed')
    while pending:
        path=pending.pop()
        if path in used: continue
        used.add(path)
        if path.suffix!='.py': continue
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            modules=[]
            if isinstance(node,ast.ImportFrom) and node.module:
                if node.module=='scripts': modules=['scripts.'+n.name for n in node.names]
                elif node.module.startswith('scripts.'): modules=[node.module]
            elif isinstance(node,ast.Import): modules=[n.name for n in node.names if n.name.startswith('scripts.')]
            for module in modules:
                target=root/(module.replace('.','/')+'.py')
                if target.is_file() and target not in roles:
                    roles[target]='static_import_helper'; pending.append(target)
    for filename in ('run_vllm_server.sh','stop_vllm_server.sh'):
        path=root/'scripts'/filename; used.add(path); roles[path]='actual_server_lifecycle_entrypoint'
    rows=[{'path':str(path.relative_to(root)),'role':roles[path],'sha256':sha(path)} for path in sorted(used)]
    output=root/'results/tsc_revision_r1r'
    with (output/'result_code_inventory_v1.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','role','sha256')); writer.writeheader(); writer.writerows(rows)
    native=[]
    prior=json.loads((root/'results/tsc_revision_r1/runtime_source_inventory_v1.json').read_text())
    for item in prior['linked_native_extensions']:
        path=root/'third_party/vllm-contractkv-tsc-r1r-slice'/item['relative_path']
        actual=sha(path)
        if actual!=item['sha256']: raise RuntimeError('Native ABI source changed')
        native.append({'relative_path':item['relative_path'],'bytes':path.stat().st_size,'sha256':actual})
    record={'schema_version':'tsc-r1r.result-source-inventory.v1','non_test_code_files':len(rows),
            'entrypoint_and_import_closure_not_line_execution_trace':True,
            'validation_exact_live_sources':'validation/freeze_v1.json and source_snapshot',
            'long_exact_live_sources':'long_horizon/freeze_v1.json and source_snapshot',
            'historical_development_exact_client_versions_complete':False,
            'development_provenance':'Retained outputs, launcher snapshots and backend patches; current root client is the frozen validation version. Development is diagnostic, not the sealed validation evidence.',
            'native_extensions_verified_against_R1':native,'private_SSH_and_credentials_excluded':True}
    (output/'source_inventory_v1.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))


if __name__=='__main__': main()
