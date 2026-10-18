"""Recompute archived results in a separate output directory, preserving originals."""
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists()
    source=a.study/'postprocessing_source_v1/tsc_revision_real_repo_analysis_v1.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    old=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');new=deepcopy(old)
    def assignment(fn):
        matches=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='output' for x in n.targets)]
        assert len(matches)==1;return matches[0]
    n=assignment(new);n.value=ast.copy_location(ast.Name(id='_independent_output_directory',ctx=ast.Load()),n.value)
    before=deepcopy(old);after=deepcopy(new)
    assignment(before).value=ast.Constant(value='OUTPUT_DIRECTORY_ONLY');assignment(after).value=ast.Constant(value='OUTPUT_DIRECTORY_ONLY')
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    spec=importlib.util.spec_from_file_location('archived_budget_analysis_source',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    space=module.__dict__.copy();space['_independent_output_directory']=a.output.resolve()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),str(source)+'[independent-output-directory-only]', 'exec'),space)
    space['main'](a.root.resolve())
    with (a.output/'independent_output_adapter_receipt_v1.json').open('x',encoding='utf-8') as f:
        json.dump(dict(only_output_directory_mapped=True,all_other_function_AST_identical=True,
            archived_analysis_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),new_GPU_requests=0,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),f,indent=2)


if __name__=='__main__':main()
