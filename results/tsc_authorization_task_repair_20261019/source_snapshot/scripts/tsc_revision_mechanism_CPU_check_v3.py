"""Exercise actual source routing/scope code, without any model/network calls."""
import argparse
import ast
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scripts.tsc_revision_mechanism_live_v3 as live


def check(root,output):
    if output.exists():raise FileExistsError(output)
    plan=json.loads((root/'results/tsc_revision_mechanism_controls_20261018/protocol_v1.json').read_text(encoding='utf-8'))
    case=copy.deepcopy(plan['behavior_cases'][0])
    args=SimpleNamespace(base_url='CPU-NO-NETWORK',model='CPU',timeout=1,cell_id='cpu',policy_hash='cpu-policy')
    original=live.tokenize
    try:
        live.tokenize=lambda url,model,msg,gen,timeout:list(json.dumps(msg,ensure_ascii=False).encode())
        a=live.actual_plan(args,case);changed=copy.deepcopy(case)
        changed['expected_raw_text']='DIFFERENT_OFFLINE_SCORE_TARGET';changed['declared_risk']='OTHER_TEST_LABEL'
        b=live.actual_plan(args,changed);assert a['query_scope']==b['query_scope']
        changed=copy.deepcopy(case);changed['raw_messages'][1]['content']+=' new observation'
        c=live.actual_plan(args,changed);assert a['query_scope']!=c['query_scope']
    finally:live.tokenize=original
    source=root/'scripts/tsc_revision_mechanism_live_v3.py';tree=ast.parse(source.read_text(encoding='utf-8'))
    inner=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='generate')
    captured=[];recorded=[]
    def fake_business(*aa,**kw):
        captured.append(kw.get('salt'));return {'request_id':'CPU-ONLY','success':True,'output_text':''}
    space=dict(args=args,counts={},record=recorded.append,score=lambda *a:0,business_generate=fake_business)
    exec(compile(ast.Module(body=[inner],type_ignores=[]),str(source),'exec'),space)
    space['generate'](case,'manifest_raw','x',legacy_raw=True);assert captured[-1] is None
    space['generate'](case,'manifest_compiled','x',legacy_raw=True,compiled=True,salt='authorized');assert captured[-1]=='authorized'
    space['generate'](case,'behavior_raw','x');assert captured[-1].startswith('cpu-policy:private:')
    assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id in ('scope_errors','admit') for t in n.targets)]
    assert len(assignments)==2
    code=compile(ast.Module(body=sorted(assignments,key=lambda n:n.lineno),type_ignores=[]),str(source),'exec')
    for issued,errors,old,new,expected in [(True,[],'a','a',True),(True,[],'a','b',False),
                                          (True,['domain_mismatch'],'a','a',False),(False,[],'a','a',False)]:
        ns=dict(issued=issued,binding_errors=errors,candidate={'query_scope':old},target_plan={'query_scope':new})
        exec(code,ns);assert ns['admit']==expected
    result=dict(CPU_only=True,model_calls=0,
        actual_source_functions_exercised=['actual_plan','nested generate','scope_errors/admit AST assignments'],
        offline_answer_and_risk_label_do_not_change_scope=True,changed_actual_observation_changes_scope=True,
        original_Manifest_raw_transport_salt_None=True,compiled_salt_preserved=True,
        behavior_private_control_salts_preserved=True,
        exact_scope_mismatch_or_HMAC_mismatch_or_no_certificate_selects_raw=True,
        backend_publication_or_behavior_claim=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();check(a.root,a.output)
