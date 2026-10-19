"""Real next-line diagnostic using the frozen four-path behavior collector."""
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def adapted_run(source):
    tree=ast.parse(source.read_text(encoding='utf-8'))
    old=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run')
    cut=next(i for i,n in enumerate(old.body) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call)
        and isinstance(n.value.func,ast.Name) and n.value.func.id=='binding_functions')
    changed=deepcopy(old);changed.body=deepcopy(old.body[:cut])
    edits=0
    for n in ast.walk(changed):
        if isinstance(n,ast.keyword) and n.arg=='source_unit':
            n.value=ast.parse("case['source_group']",mode='eval').body;edits+=1
    assert edits==1
    changed.body+=ast.parse("""
assert counts['business']==len(plan['behavior_cases'])*4==24
assert counts.get('verification',0)<=6
record(dict(event='diagnostic_cell_complete',counts=counts,diagnostic_client_wall_s=time.perf_counter()-started,
    all_cases_preserved=True,service_performance_claim=False,real_RepoBench_sources=3,
    one_python_statement_guard_preserved=True,production_family_eligibility_unchanged=True))
print(json.dumps(dict(cell=args.cell_id,counts=counts)),flush=True)
""").body
    proof=dict(unchanged_setup_generate_qualify_and_behavior_loop_except_source_unit=True,
        source_unit_replaced_by_actual_repository_identity=True,Manifest_not_repeated=True,expected_business=24,expected_cases=6)
    before=deepcopy(old.body[:cut]);after=deepcopy(changed.body[:cut])
    for statements in [before,after]:
        for n in ast.walk(ast.Module(body=statements,type_ignores=[])):
            if isinstance(n,ast.keyword) and n.arg=='source_unit':n.value=ast.Constant(value='DECLARED_REAL_SOURCE_METADATA')
    assert ast.dump(ast.Module(body=before,type_ignores=[]),include_attributes=False)==ast.dump(ast.Module(body=after,type_ignores=[]),include_attributes=False)
    return changed,proof


def main(args):
    freeze=json.loads(args.freeze.read_text(encoding='utf-8'));root=args.project_root.resolve()
    for x in freeze['source_files']:assert sha(root/x['path'])==x['sha256'],x['path']
    base=root/'results/tsc_revision_mechanism_controls_20261018';snapshot=base/'source_snapshot'
    sys.path.insert(0,str(snapshot))
    collector=snapshot/'scripts/tsc_revision_mechanism_live_v3.py';assert sha(collector)==freeze['parent_collector_sha256']
    spec=importlib.util.spec_from_file_location('frozen_real_repo_collector',collector)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    from scripts.tsc_revision_r2_admission import SingleShotRegistrar
    from scripts.contractkv_verifier import VerificationIncomplete
    from scripts.phase20a_official_quality import standard_score
    guard=root/'results/tsc_real_repobench_mechanism_20261018/source_extra/tsc_revision_r3_output_contract.py'
    assert sha(guard)==freeze['unchanged_output_contract_sha256']
    spec=importlib.util.spec_from_file_location('unchanged_real_repo_output_contract',guard)
    syntax=importlib.util.module_from_spec(spec);spec.loader.exec_module(syntax)
    spec=importlib.util.spec_from_file_location('unchanged_incomplete_reference_fix',root/'scripts/tsc_revision_incomplete_reference_fix_v5.py')
    fix=importlib.util.module_from_spec(spec);spec.loader.exec_module(fix)
    old_register=SingleShotRegistrar.register
    SingleShotRegistrar.register=fix.repaired_register(old_register,VerificationIncomplete)
    class ExactRepoRegistrar(syntax.OutputContractRegistrar):
        def register(self,args,namespace,scope,business,gate,record=lambda row:None):
            return super().register(args,namespace,scope,business,{**gate,'output_contract':'one_python_statement'},record)
    def score(result,case):
        if not result.get('success'):return 0.
        return standard_score(case['dataset'],case['task'],result.get('output_text',''),case['answer'])[0]
    def actual_plan(args,case):
        started=time.perf_counter();ids=original.tokenize(args.base_url,args.model,case['candidate_messages'],True,args.timeout)
        prefix=original.tokenize(args.base_url,args.model,case['candidate_prefix_messages'],False,args.timeout)
        end=original.lcp_length(prefix,ids);assert end//16>0 and end<len(ids)
        return dict(level=case['diagnostic_layout_level'],messages=case['candidate_messages'],prompt_token_ids=ids,
            prompt_ids_sha256=original.digest(ids),stable_prefix_end_token=end,stable_full_blocks=end//16,
            stable_content_hash=original.digest(ids[:end]),layout_hash=original.digest(case['candidate_order']),
            dependency_graph_hash=original.digest([(x['segment_id'],x.get('dependencies',[])) for x in case['segments']]),
            query_scope=original.digest(dict(raw_messages=case['raw_messages'],candidate_prompt_ids=ids,output_budget=case['output_budget'])),
            output_budget=case['output_budget'],cpu_http_preparation_ms=(time.perf_counter()-started)*1000,
            qualification_protocol='actual Raw witness, exact observation, existing one_python_statement guard; private diagnostic')
    function,proof=adapted_run(collector);assert proof==freeze['client_AST_proof']
    namespace=original.__dict__.copy();namespace.update(score=score,actual_plan=actual_plan,SingleShotRegistrar=ExactRepoRegistrar)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(collector)+'[real-RepoBench-private-diagnostic]', 'exec'),namespace)
    try:
        namespace['run'](args)
        plan=json.loads(args.plan.read_text(encoding='utf-8'));cases={x['case_id']:x for x in plan['behavior_cases']}
        model={'qwen3-8b':'Qwen3-8B','mistral-7b':'Mistral-7B-Instruct-v0.3','llama-3.1-8b':'Llama-3.1-8B-Instruct'}[args.model]
        path=root/'results/tsc_real_repobench_mechanism_20261018/inputs_v1/CPU_prompt_shapes_v1.jsonl'
        assert sha(path)==plan['CPU_prompt_shapes_sha256']
        expected={}
        for line in path.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['model']==model and row['tenant']==row['turn']==0:expected[row['source_group'],row['condition']]=row
        checked=0;failed=0
        for line in args.output.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['event']!='business':continue
            if not row['response']['success']:failed+=1;continue
            case=cases[row['case_id']]
            condition='candidate' if row['compiled_input'] and case['diagnostic_layout_level']=='L3' else 'raw'
            shape=expected[case['source_group'],condition]
            assert row['response']['prompt_ids_sha256']==shape['prompt_ids_sha256'],'Actual real-task input differs from frozen faithful CPU shape'
            checked+=1
        with (args.output.parent/'actual_prompt_shape_check_v1.json').open('x',encoding='utf-8') as f:
            json.dump(dict(checked_successful_actual_requests=checked,failed_transport_requests=failed,
                source_models_and_layouts_match_CPU_preparation=True,new_GPU_requests_by_check=0),f,indent=2)
    finally:SingleShotRegistrar.register=old_register


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['project-root','freeze','root','plan','identity','output']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['base-url','model','cell-id','policy-hash']:p.add_argument('--'+name,required=True)
    p.add_argument('--timeout',type=float,default=600);main(p.parse_args())
