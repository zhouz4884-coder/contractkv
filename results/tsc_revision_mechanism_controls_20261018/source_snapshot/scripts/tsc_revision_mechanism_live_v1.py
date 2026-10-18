"""Real serial business, strict certification, binding and publication controls.

Synthetic diagnostic only. Raw/layout-only namespaces cannot populate the
qualification namespace. No output-dependent retries or selection are allowed.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import secrets
from types import SimpleNamespace
import sys
import time
from typing import Any

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.contractkv_certificate_binding import CertificateBinding, RequestBinding, sign, validation_errors
from scripts.contractkv_pstp import lcp_length
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.tsc_revision_mechanism_cases_v1 import messages
from scripts.tsc_revision_r2_admission import SingleShotRegistrar
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_registration_audit import registration_errors, signature


def normalized(text):
    return re.sub(r'<think>.*?</think>\s*','',text,flags=re.S).strip().strip('"\'').rstrip('.').strip()


def score(result,case):
    return float(bool(result.get('success')) and normalized(result.get('output_text',''))==case['expected_raw_text'])


def difference(a,b):
    if not a.get('success') or not b.get('success'):
        return dict(available=False, reason='one_or_both_business_requests_failed')
    x,y=a['output_token_ids'],b['output_token_ids']
    first=next((i for i,(u,v) in enumerate(zip(x,y)) if u!=v),None)
    if first is None and len(x)!=len(y):first=min(len(x),len(y))
    return dict(available=True, output_ids_equal=x==y, first_difference_index=first,
                finish_equal=a['finish_reason']==b['finish_reason'],
                output_length_a=len(x), output_length_b=len(y),
                prompt_ids_equal=a['prompt_token_ids']==b['prompt_token_ids'])


def binding_functions(root):
    """Execute the actual controlled client's two unchanged functions only."""
    source=root/'scripts/tsc_real_task_open_loop.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('issue_binding','check_binding')]
    assert len(functions)==2
    space=dict(argparse=argparse,Any=Any,asdict=asdict,digest=digest,CertificateBinding=CertificateBinding,
               RequestBinding=RequestBinding,sign_binding=sign,binding_validation_errors=validation_errors)
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),space)
    return space['issue_binding'],space['check_binding']


def actual_plan(args,case):
    started=time.perf_counter()
    candidate=case['candidate_messages']
    ids=tokenize(args.base_url,args.model,candidate,True,args.timeout)
    byid={x['segment_id']:x for x in case['segments']};stable=[]
    for sid in case['candidate_order']:
        x=byid[sid]
        if x['segment_type']=='USER_QUERY' or x['volatility']>=0.5:break
        stable.append(sid)
    prefix=tokenize(args.base_url,args.model,messages(case,stable),False,args.timeout)
    end=lcp_length(prefix,ids)
    assert end//16>0 and end<len(ids)
    return dict(level='L3',messages=candidate,prompt_token_ids=ids,prompt_ids_sha256=digest(ids),
        stable_prefix_end_token=end,stable_full_blocks=end//16,stable_content_hash=digest(ids[:end]),
        layout_hash=digest(case['candidate_order']),
        dependency_graph_hash=digest([(x['segment_id'],x['dependencies']) for x in case['segments']]),
        query_scope=digest(case),output_budget=case['output_budget'],
        cpu_http_preparation_ms=(time.perf_counter()-started)*1000,
        qualification_protocol='actual raw witness, exact observation scope; controlled mechanism diagnostic')


def run(args):
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if args.output.exists():raise FileExistsError('Preserve every attempted cell: '+str(args.output))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.touch(exist_ok=False)
    started=time.perf_counter();counts={}
    def record(row):
        with args.output.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(dict(cell_id=args.cell_id,model=args.model,event_epoch_s=time.time(),**row),ensure_ascii=False,allow_nan=False)+'\n')
    def generate(case,condition,ns,witness=False,compiled=False,salt=None):
        rid=args.cell_id+'-'+ns+'-'+condition
        wire=salt if salt is not None else args.policy_hash+':private:'+rid
        result=business_generate(args,case['candidate_messages'] if compiled else case['raw_messages'],
                                 case['output_budget'],rid,witness=witness,salt=wire)
        counts['business']=counts.get('business',0)+1
        record(dict(event='business',case_id=case['case_id'],condition=condition,
                    actual_wire_salt=wire,compiled_input=compiled,score=score(result,case),response=result))
        return result
    def qualify(case,raw,ns):
        candidate=actual_plan(args,case)
        registrar=SingleShotRegistrar(plan['raw_margin_floor'],plan['candidate_and_eos_margin_floor'])
        response=registrar.register(args,ns,candidate['query_scope'],raw,
            dict(allow_verification=True,reason='predeclared mechanism diagnostic without economic screening',plan=candidate),
            record=lambda x:record(dict(event='qualification_detail',case_id=case['case_id'],namespace=ns,**x)))
        counts['verification']=counts.get('verification',0)+len(response.get('attempts',[]))
        record(dict(event='qualification',case_id=case['case_id'],namespace=ns,plan=candidate,result=response))
        return candidate,response

    for case in plan['behavior_cases']:
        ns='behavior-'+case['case_id']
        raw=generate(case,'raw_witness',ns,witness=True)
        raw_repeat=generate(case,'raw_repeat',ns)
        unchecked=generate(case,'unchecked_same_candidate',ns,compiled=True)
        candidate,decision=qualify(case,raw,ns)
        issued=decision.get('certificate_issued') is True
        routed=generate(case,'post_decision_compiled' if issued else 'post_decision_raw',ns,compiled=issued,
                        salt=args.policy_hash+':'+ns if issued else None)
        record(dict(event='behavior_case_complete',case_id=case['case_id'],family=case['family'],
                    declared_risk=case['declared_risk'],raw_repeat=difference(raw,raw_repeat),
                    unchecked_difference=difference(raw,unchecked),routed_difference=difference(raw,routed),
                    raw_score=score(raw,case),raw_repeat_score=score(raw_repeat,case),
                    unchecked_score=score(unchecked,case),routed_score=score(routed,case),
                    certificate_issued=issued,observed_unchecked_score_delta=score(unchecked,case)-score(raw,case),
                    source_unit='controlled family/variant; repeated model processes are not new sources'))

    # Adapter explicitly invokes existing registration validation and binding
    # BEFORE it dispatches any compiled business request. No public gateway is claimed.
    issue,check=binding_functions(args.root)
    secret=secrets.token_bytes(32)
    identity=json.loads(args.identity.read_text(encoding='utf-8'))
    bind_args=SimpleNamespace(cell_id=args.cell_id,policy_hash=args.policy_hash,
        model_identity=identity['model_identity'],model_revision=identity['model_revision'],
        tokenizer=identity['tokenizer'],chat_template_hash=identity['chat_template_hash'],
        runtime_revision=identity['runtime_revision'],qualification_hash=args.policy_hash)
    basecase=next(c for c in plan['manifest_cases'] if not c['trusted_semantic_mislabel'] and c['case_id'].endswith('ALPHA'))
    for control in plan['manifest_registration_controls']:
        manifest=deepcopy(basecase['manifest']);role='operator'
        private=next(x for x in manifest['segments'] if x['id']=='PRIVATE')
        if control=='explicit_private_publication':private['publish']=True
        elif control=='mutable_publication':
            private.update(visibility='domain_shared',publish=True,stable=False)
        else:role='tenant'
        errors=registration_errors(manifest,signature(manifest,secret),secret,'trusted-operator',role)
        assert errors
        ns='registration-'+control
        fallback=generate(basecase,'registration_rejected_raw_fallback',ns)
        record(dict(event='registration_control',control=control,namespace=ns,errors=errors,
                    registration_adapter='controlled trusted-client call of existing helper',
                    verifier_dispatched=False,actual_raw_request_id=fallback['request_id']))

    for mislabel in (False,True):
        case=next(c for c in plan['manifest_cases'] if c['trusted_semantic_mislabel']==mislabel and c['case_id'].endswith('ALPHA'))
        ns='manifest-'+('trusted_mislabel' if mislabel else 'correct_declaration')
        manifest=case['manifest']
        errors=registration_errors(manifest,signature(manifest,secret),secret,'trusted-operator','operator')
        record(dict(event='registration',case_id=case['case_id'],namespace=ns,errors=errors,
                    trusted_semantic_mislabel=mislabel,synthetic_marker=case['synthetic_marker']))
        assert not errors
        raw=generate(case,'raw_witness',ns,witness=True)
        raw_repeat=generate(case,'raw_repeat',ns)
        candidate,decision=qualify(case,raw,ns)
        issued=decision.get('certificate_issued') is True
        committed=int(decision.get('committed_tokens',0))
        committed_text=None;decode_error=None
        if committed:
            try:
                decoded=post_json(api_root(args.base_url)+'/detokenize',
                                  dict(model=args.model,tokens=candidate['prompt_token_ids'][:committed]),args.timeout)
                committed_text=decoded.get('prompt')
            except Exception as exc:decode_error=repr(exc)
        sample=dict(service_template_id=ns)
        scope=dict(authorization_domain='domain-a',service_epoch=1,
                   stable_content_hash=candidate['stable_content_hash'],layout_hash=candidate['layout_hash'],
                   private_suffix_excluded=True)  # trusted DECLARATION, not inferred confidentiality
        binding_protocol=dict(generation_budgets={'synthetic_manifest':case['output_budget']})
        signed,tag=issue(bind_args,sample,scope,binding_protocol,secret)
        certificate=dict(signed_binding=signed,binding_signature=tag) if issued else {}
        record(dict(event='manifest_publication',case_id=case['case_id'],namespace=ns,
                    certificate_issued=issued,committed_tokens=committed,
                    committed_prefix_detokenized=committed_text,detokenize_error=decode_error,
                    synthetic_marker_in_committed_prefix=(case['synthetic_marker'] in committed_text) if committed_text is not None else None,
                    raw_repeat=difference(raw,raw_repeat),signed_binding=signed if issued else None))
        for control in plan['manifest_business_controls']:
            target=case
            if control=='different_private_value_same_domain':
                target=next(c for c in plan['manifest_cases'] if c['trusted_semantic_mislabel']==mislabel and c['case_id'].endswith('BETA'))
            target_plan=actual_plan(args,target)
            request_scope=dict(scope,stable_content_hash=target_plan['stable_content_hash'],layout_hash=target_plan['layout_hash'])
            if control=='matching_private_value_other_domain':request_scope['authorization_domain']='domain-b'
            if control=='stale_version':request_scope['service_epoch']=2
            binding_errors=check(bind_args,dict(sample,tenant_id='tenant-B'),request_scope,binding_protocol,certificate,secret)
            admit=issued and not binding_errors
            output=generate(target,control,ns,compiled=admit,salt=args.policy_hash+':'+ns if admit else None)
            record(dict(event='manifest_request_complete',case_id=case['case_id'],namespace=ns,control=control,
                        trusted_semantic_mislabel=mislabel,binding_errors=binding_errors,compiled_route=admit,
                        actual_business_request_id=output['request_id'],score=score(output,target),
                        declared_private_suffix_excluded=True,
                        enforcement_location='controlled trusted-client adapter before real model request; backend is not an untrusted-user gateway'))
    assert counts['business']==len(plan['behavior_cases'])*4+15
    assert counts.get('verification',0)<=len(plan['behavior_cases'])+2
    record(dict(event='diagnostic_cell_complete',counts=counts,diagnostic_client_wall_s=time.perf_counter()-started,
                all_cases_preserved=True,service_performance_claim=False))
    print(json.dumps(dict(cell=args.cell_id,counts=counts)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--identity',type=Path,required=True);p.add_argument('--base-url',required=True);p.add_argument('--model',required=True)
    p.add_argument('--cell-id',required=True);p.add_argument('--policy-hash',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=300);run(p.parse_args())
