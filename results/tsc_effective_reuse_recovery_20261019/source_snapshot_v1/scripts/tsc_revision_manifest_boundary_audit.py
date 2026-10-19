"""CPU audit of actual client binding functions and the separate manifest helper.

Source-extracted functions avoid loading a serving runtime. No network admission
gateway, GPU request, or live confidentiality detector is simulated or claimed.
"""
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any
import argparse
import ast
import copy
import hashlib
import hmac
import json
import secrets
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.contractkv_certificate_binding import CertificateBinding,RequestBinding,sign,validation_errors


def main():
    path=ROOT/'scripts/tsc_real_task_open_loop.py';source=path.read_text();tree=ast.parse(source)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['issue_binding','check_binding']]
    assert len(functions)==2
    # digest is the exact source dependency used by the real client, not a new hash rule.
    helper=ROOT/'scripts/phase17_live_common.py'
    digest=next(n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='digest')
    space={'argparse':argparse,'Any':Any,'asdict':asdict,'hashlib':hashlib,'json':json,
        'CertificateBinding':CertificateBinding,'RequestBinding':RequestBinding,
        'sign_binding':sign,'binding_validation_errors':validation_errors}
    exec(compile(ast.Module(body=[digest]+functions,type_ignores=[]),str(path),'exec'),space)
    args=SimpleNamespace(cell_id='cpu-test',model_identity='model',model_revision='revision',tokenizer='tokenizer',
        chat_template_hash='chat',runtime_revision='runtime',qualification_hash='qualification',policy_hash='policy')
    sample={'service_template_id':'template'}
    scope={'authorization_domain':'domain','service_epoch':1,'stable_content_hash':'stable','layout_hash':'layout','private_suffix_excluded':True}
    protocol={'generation_budgets':{'task':96}}
    secret=secrets.token_bytes(32)
    binding,tag=space['issue_binding'](args,sample,scope,protocol,secret)
    certificate={'signed_binding':binding,'binding_signature':tag}
    cases=[]
    def check(name,a=args,s=sample,sc=scope,p=protocol,cert=certificate,expected=True):
        errors=space['check_binding'](a,s,sc,p,cert,secret)
        assert bool(errors)==expected,(name,errors)
        cases.append({'case':name,'binding_errors':errors,'compiled_route_admissible':not errors,
                      'evidence_type':'CPU source-extracted controlled-client binding check'})
    check('valid_binding',expected=False)
    check('tenant_label_not_bound_by_domain_wildcard',s={'service_template_id':'template','tenant_id':'different-label'},expected=False)
    for field in ['model_identity','model_revision','tokenizer','chat_template_hash','runtime_revision','qualification_hash','policy_hash']:
        other=copy.deepcopy(args);setattr(other,field,'changed');check('changed_'+field,a=other)
    for field,value in [('authorization_domain','other'),('service_epoch',2),('stable_content_hash','changed'),('layout_hash','changed'),('private_suffix_excluded',False)]:
        other=copy.deepcopy(scope);other[field]=value;check('changed_'+field,sc=other)
    check('changed_template',s={'service_template_id':'other'})
    check('changed_generation_budget',p={'generation_budgets':{'task':128}})
    check('missing_signed_binding',cert={})
    other=copy.deepcopy(certificate);other['binding_signature']='invalid';check('bad_authentication_tag',cert=other)
    other=copy.deepcopy(certificate);other['signed_binding']['expires_at_epoch']=0
    other['binding_signature']=sign(CertificateBinding(**other['signed_binding']),secret);check('expired_binding',cert=other)
    # Locate the invocation before route selection in the actual async request function.
    replay=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='replay')
    request=next(n for n in replay.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='request_one')
    check_lines=[n.lineno for n in ast.walk(request) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='check_binding']
    send_lines=[n.lineno for n in ast.walk(request) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='send_chat_stream_async']
    assert len(check_lines)==len(send_lines)==1 and check_lines[0]<send_lines[0]
    output=ROOT/'results/tsc_revision_evidence_closure_20261017/manifest_audit';output.mkdir(parents=True,exist_ok=True)
    report={'cases':cases,'case_count':len(cases),'binding_error_cases':sum(bool(r['binding_errors']) for r in cases),
        'actual_enforcement_location':'Trusted controlled-service client before compiled/raw route selection',
        'network_authentication_proxy_implemented_by_this_test':False,'live_registration_helper_integrated':False,
        'individual_tenant_identity_check':'This client binds tenant_id=* within the operator-configured authorization domain; it is not a per-tenant access-control service.',
        'request_function_source_lines':{'binding_check':check_lines[0],'model_send':send_lines[0]},
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'new_model_calls':0,
        'limits':['Binding mismatch selects raw routing; it does not mean that no backend raw request is sent.',
                  'The separate nine-case manifest helper does not infer confidentiality or run as a public registration endpoint.',
                  'A trusted caller/controller must mediate engine access. Arbitrary direct untrusted engine clients are outside this evaluated boundary.']}
    (output/'client_binding_boundary_v1.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'CPU_cases':len(cases),'rejected_compiled_bindings':report['binding_error_cases'],'actual_location':report['actual_enforcement_location'],'new_model_calls':0}))


if __name__=='__main__':main()
