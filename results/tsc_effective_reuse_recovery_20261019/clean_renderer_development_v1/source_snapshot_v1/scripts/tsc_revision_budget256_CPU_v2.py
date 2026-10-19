"""Zero-GPU execution-shape check, using explicit fake transport/registrar.

This verifies budget propagation and unchanged case inclusion, not behavioral
efficacy, admissibility, GPU costs or prefix publication.
"""
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import time
import tempfile
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_budget256_client_v2 import behavior_function
from scripts.tsc_revision_budget256_worker_v2 import adapt


def main(root):
    study=root/'results/tsc_mechanism_budget256_20261018'
    source=root/'results/tsc_revision_mechanism_controls_20261018/source_snapshot/scripts/tsc_revision_mechanism_live_v3.py'
    plan=json.loads((study/'protocol_v1.json').read_text(encoding='utf-8'))
    function,client_proof=behavior_function(source)
    _,worker_proof=adapt()
    calls=[];qualifications=[]
    def generate(args,messages,budget,rid,*,witness=False,salt=None):
        assert budget==256
        calls.append(dict(messages=messages,budget=budget,rid=rid,witness=witness,salt=salt))
        return dict(success=True,request_id=rid,output_text='FAKE_TRANSPORT',
            output_token_ids=[1,2],prompt_token_ids=[3,4],finish_reason='stop')
    def actual_plan(args,case):
        assert case['output_budget']==256
        return dict(messages=case['candidate_messages'],query_scope=case['case_id'],output_budget=256)
    class FakeRegistrar:
        def __init__(self,raw,candidate):
            assert (raw,candidate)==(.0625,.125)
        def register(self,args,namespace,scope,raw,gate,record):
            qualifications.append(dict(namespace=namespace,scope=scope,plan=deepcopy(gate['plan'])))
            issued=len(qualifications)%2==0
            return dict(certificate_issued=issued,attempts=[dict(explicit_CPU_fake=True)])
    originals=ast.parse(source.read_text(encoding='utf-8'))
    helpers=[n for n in originals.body if isinstance(n,ast.FunctionDef) and n.name in ('normalized','score','difference')]
    space=dict(json=json,re=re,time=time,business_generate=generate,actual_plan=actual_plan,SingleShotRegistrar=FakeRegistrar)
    exec(compile(ast.fix_missing_locations(ast.Module(body=helpers+[function],type_ignores=[])),str(source)+'[CPU fake I/O]', 'exec'),space)
    with tempfile.TemporaryDirectory(prefix='budget256_CPU_',dir=study) as directory:
        output=Path(directory)/'responses.jsonl'
        space['run'](SimpleNamespace(plan=study/'protocol_v1.json',output=output,cell_id='CPU_FAKE',policy_hash='CPU_FAKE',model='CPU_FAKE'))
        rows=[json.loads(x) for x in output.read_text(encoding='utf-8').splitlines()]
    counts=Counter(x['event'] for x in rows)
    assert len(calls)==80 and len(qualifications)==20
    assert counts['business']==80 and counts['behavior_case_complete']==20
    assert counts['manifest_request_complete']==counts['registration_control']==0
    assert sum(x['witness'] for x in calls)==20
    assert counts['diagnostic_cell_complete']==1
    for case in plan['behavior_cases']:
        actual=[x for x in calls if x['rid'].startswith('CPU_FAKE-behavior-'+case['case_id']+'-')]
        assert len(actual)==4 and actual[0]['messages']==case['raw_messages'] and actual[1]['messages']==case['raw_messages']
        assert actual[2]['messages']==case['candidate_messages']
        assert actual[3]['messages'] in (case['raw_messages'],case['candidate_messages'])
    result=dict(status='PASS',new_GPU_requests=0,transport='explicit CPU fake',qualification='explicit CPU fake',
        propagated_equal_budget=256,fake_business_calls=80,fake_qualification_calls=20,
        all_original_case_IDs_preserved=True,no_Manifest_repetition=True,client_AST_proof=client_proof,worker_AST_proof=worker_proof,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scientific_result_claim=False)
    with (study/'CPU_wiring_regression_v2.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
