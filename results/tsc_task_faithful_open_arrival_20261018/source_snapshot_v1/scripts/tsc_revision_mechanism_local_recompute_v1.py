"""Recompute an archived diagnostic locally with identical tokenizer bytes.

Only the remote absolute model directory is mapped to the existing CPU
tokenizer snapshot. All original analysis statements and checks remain.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True)
    p.add_argument('--tokenizer-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();study=a.study.resolve();output=a.output.resolve();assert not output.exists()
    source=study/'postprocessing_source_v5/tsc_revision_mechanism_analysis_v3.py'
    registry=read(study/'preflight_v3/model_asset_registry_v1.json');checked=[]
    for model in registry['models']:
        for entry in model['files']:
            if entry['file'].startswith(('tokenizer','special_tokens','vocab','merges')):
                path=a.tokenizer_root/model['model']/entry['file'];assert sha(path)==entry['sha256']
                checked.append(dict(model=model['model'],file=entry['file'],sha256=entry['sha256']))
    tree=ast.parse(source.read_text(encoding='utf-8'));original=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='analyze')
    changed=deepcopy(original)
    def assignment(fn):
        matches=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='modelpath' for t in n.targets)]
        assert len(matches)==1;return matches[0]
    node=assignment(changed)
    node.value=ast.copy_location(ast.Call(func=ast.Name(id='_local_modelpath',ctx=ast.Load()),args=[node.value],keywords=[]),node.value)
    before=deepcopy(original);after=deepcopy(changed)
    assignment(before).value=ast.Constant(value='EXPLICIT_LOCAL_TOKENIZER_DIRECTORY')
    assignment(after).value=ast.Constant(value='EXPLICIT_LOCAL_TOKENIZER_DIRECTORY')
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    spec=importlib.util.spec_from_file_location('archived_original_mechanism_analysis',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    models={x['model'] for x in registry['models']}
    def local_modelpath(remote):
        assert remote.name in models
        local=a.tokenizer_root/remote.name;assert local.is_dir();return local
    space=module.__dict__.copy();space['_local_modelpath']=local_modelpath
    exec(compile(ast.fix_missing_locations(ast.Module(body=[changed],type_ignores=[])),str(source)+'[local-tokenizer-directory-only]', 'exec'),space)
    space['analyze'](study,output)
    expected=read(study/'analysis_v3/summary_v1.json');actual=read(output/'summary_v1.json');assert actual==expected,'Local independently decoded summary differs'
    equal=[]
    for reference in sorted((study/'analysis_v3').glob('*.csv')):
        candidate=output/reference.name;assert candidate.read_bytes()==reference.read_bytes(),reference.name;equal.append(reference.name)
    receipt=dict(status='PASS',original_analysis_source_sha256=sha(source),new_GPU_requests=0,
        only_remote_model_directory_mapped=True,all_other_function_AST_identical=True,
        verified_existing_tokenizer_assets=checked,summary_all_fields_equal=True,CSV_bytes_equal=equal,
        raw_model_tokens_not_reconstructed=True,source_sha256=sha(Path(__file__)))
    with (output/'independent_recompute_receipt_v1.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS',all_summary_fields_equal=True,CSV_bytes_equal=equal)))


if __name__=='__main__':main()
