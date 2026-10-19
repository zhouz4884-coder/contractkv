"""Check real-case construction against frozen tokenizer hashes; no GPU forwards."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_real_repo_client_v1 import adapted_run
from scripts.tsc_revision_real_repo_worker_v1 import adapt
from scripts.phase17_live_common import digest
from scripts.contractkv_pstp import lcp_length
from transformers import AutoTokenizer


def main(root):
    study=root/'results/tsc_real_repobench_mechanism_20261018'
    protocol=json.loads((study/'protocol_v1.json').read_text(encoding='utf-8'))
    shapes={}
    for line in (study/'inputs_v1/CPU_prompt_shapes_v1.jsonl').read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if r['tenant']==r['turn']==0:shapes[r['model'],r['source_group'],r['condition']]=r
    measured=[]
    for model in protocol['models']:
        tok=AutoTokenizer.from_pretrained('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/'+model,local_files_only=True)
        for case in protocol['behavior_cases']:
            ids={}
            for condition,messages in [('raw',case['raw_messages']),('candidate',case['candidate_messages'])]:
                ids[condition]=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
                reference='raw' if condition=='raw' or case['diagnostic_layout_level']=='L0' else 'candidate'
                assert digest(ids[condition])==shapes[model,case['source_group'],reference]['prompt_ids_sha256']
                assert len(ids[condition])+case['output_budget']<=16384
            prefix=tok.apply_chat_template(case['candidate_prefix_messages'],tokenize=True,add_generation_prompt=False,return_dict=False)
            end=lcp_length(prefix,ids['candidate']);assert 16<=end<len(ids['candidate'])
            measured.append(dict(model=model,case_id=case['case_id'],level=case['diagnostic_layout_level'],
                raw_tokens=len(ids['raw']),candidate_tokens=len(ids['candidate']),stable_prefix_end_token=end,
                block_aligned_prefix_tokens=end//16*16))
    # Execute the actual adapter class with an explicit lower-layer fake to
    # verify the original output guard is requested without rewriting its gate.
    tree=ast.parse((root/'scripts/tsc_revision_real_repo_client_v1.py').read_text(encoding='utf-8'))
    klass=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='ExactRepoRegistrar')
    class LowerFake:
        def register(self,args,namespace,scope,business,gate,record):return gate
    space=dict(syntax=SimpleNamespace(OutputContractRegistrar=LowerFake))
    exec(compile(ast.Module(body=[klass],type_ignores=[]),'actual_Repo_adapter_class_CPU_fake','exec'),space)
    gate=dict(allow_verification=False,reason='inherited_decision',plan=dict(level='L3'))
    observed=space['ExactRepoRegistrar']().register(None,'namespace','exactscope',{},gate)
    assert observed=={**gate,'output_contract':'one_python_statement'} and gate.get('output_contract') is None
    collector=root/'results/tsc_revision_mechanism_controls_20261018/source_snapshot/scripts/tsc_revision_mechanism_live_v3.py'
    _,client_proof=adapted_run(collector);_,worker_proof=adapt()
    result=dict(status='PASS',new_GPU_requests=0,actual_shape_hash_checks=36,model_candidate_cases=len(measured),
        measured_shapes=measured,client_AST_proof=client_proof,worker_AST_proof=worker_proof,
        output_guard_requested=True,input_gate_not_mutated_or_bypassed=True,
        official_primary_score_not_used_in_gate=True,protocol_sha256=hashlib.sha256((study/'protocol_v1.json').read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scientific_efficacy_claim=False)
    with (study/'CPU_case_and_guard_check_v1.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='measured_shapes'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
