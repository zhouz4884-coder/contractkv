"""Unflushed-engine authorization controls plus independent real-task work.

Test salts identify synthetic/benchmark groups only; never logs controller keys.
Serial workflow observations are not an open-arrival capacity measurement.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.contractkv_cache_identity import CacheAuthority, CacheAuthorizationError
from scripts.contractkv_authorized_requests import AuthorizedRegistrar, authorized_business_generate, REGISTRAR_ADAPTER_PROOF
from scripts.tsc_revision_r2_admission import SingleShotRegistrar
from scripts.tsc_revision_r2_business_stream import business_generate
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register
from scripts.contractkv_verifier import VerificationIncomplete
from scripts.tsc_revision_mechanism_live_v3 import binding_functions, difference
from scripts.phase17_live_common import digest, tokenize
from scripts.phase20a_official_quality import standard_score
from scripts.contractkv_pstp import lcp_length


def run(args):
    assert not args.output.exists()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.touch(exist_ok=False)
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    model = {'qwen3-8b':'Qwen3-8B','mistral-7b':'Mistral-7B-Instruct-v0.3','llama-3.1-8b':'Llama-3.1-8B-Instruct'}[args.model]
    cases = json.loads(args.cases.read_text(encoding='utf-8'))[model]
    identity = json.loads(args.identity.read_text(encoding='utf-8'))
    issue, check = binding_functions(args.source_root)
    controller_key = secrets.token_bytes(32)
    binding_key = secrets.token_bytes(32)
    started = time.perf_counter()
    counts = dict(business=0, qualification=0, actual_RPC=0, stale_identity_denied=0)
    def record(row):
        with args.output.open('a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(dict(cell_id=args.cell_id, model=args.model, event_epoch_s=time.time(),
                workflow_elapsed_ms=(time.perf_counter()-started)*1000, **row), ensure_ascii=False, allow_nan=False)+'\n')
    bind_args = SimpleNamespace(cell_id=args.cell_id, policy_hash=args.policy_hash,
        model_identity=identity['model_identity'], model_revision=identity['model_revision'],
        tokenizer=identity['tokenizer'], chat_template_hash=identity['chat_template_hash'],
        runtime_revision=identity['runtime_revision'], qualification_hash=args.policy_hash)
    # Existing narrow INCOMPLETE treatment, exactly as in accepted V5 clients.
    legacy_register = repaired_register(SingleShotRegistrar.register, VerificationIncomplete)
    record(dict(event='start', plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                cache_key_recorded=False, trusted_internal_controller=True,
                salt_values_are_synthetic_test_identities_only=True, registrar_proof=REGISTRAR_ADAPTER_PROOF))

    for case in [cases['synthetic_case']] + cases['real_cases']:
        cid = case['case_id']; synthetic = cid == 'synthetic_authorized_cache_identity'
        authority = CacheAuthority(controller_key, digest(identity), args.policy_hash, {'A':1, 'B':1},
                                   {'alice':{'A'}, 'alice2':{'A'}, 'bob':{'B'}})
        a1 = authority.bind('alice', 'A', 1, cid)
        a1_other = authority.bind('alice2', 'A', 1, cid)
        b1 = authority.bind('bob', 'B', 1, cid)
        namespace = 'repair-' + hashlib.sha256(cid.encode()).hexdigest()[:16]
        budget = case['budget']
        expected_raw = case['raw_prompt_token_ids']; expected_candidate = case['candidate_prompt_token_ids']
        def generate(condition, auth_identity=None, compiled=False, witness=False, messages=None, allowed=None):
            selected = messages if messages is not None else case['candidate_messages'] if compiled else case['raw_messages']
            rid = args.cell_id+'-'+namespace+'-'+condition
            call_start = time.perf_counter()
            if auth_identity is None:
                # Intentionally retain the historical unsalted Raw control;
                # compiled legacy calls supply the old qualification namespace.
                salt = args.policy_hash+':'+namespace+'-legacy' if compiled else None
                response = business_generate(args, selected, budget, rid, witness=witness, salt=salt)
            else:
                salt = authority.require(auth_identity)
                response = authorized_business_generate(authority, auth_identity, args, selected, budget, rid, witness=witness)
            counts['business'] += 1
            if response['success']:
                assert response['prompt_token_ids'] == (expected_candidate if compiled else expected_raw)
            if synthetic:
                text = response.get('output_text','').replace('<think>','').replace('</think>','').strip()
                score = float(response['success'] and text == 'ACK')
            else:
                score = standard_score(case['dataset'], case['task'], response.get('output_text',''), case['answer'])[0] if response['success'] else 0.
            record(dict(event='business', case_id=cid, source_group=case.get('source_group','synthetic'),
                family=case.get('family','synthetic'), condition=condition, compiled_route=compiled,
                trusted_authorization_domain=auth_identity.authorization_domain if auth_identity else 'legacy_control',
                active_epoch=auth_identity.service_epoch if auth_identity else None,
                actual_wire_cache_salt=salt, binding_errors=allowed, output_score=score,
                actual_dispatch_and_stream_ms=(time.perf_counter()-call_start)*1000, response=response))
            return response

        candidate_plan = dict(level=case['level'], messages=case['candidate_messages'],
            prompt_token_ids=expected_candidate, prompt_ids_sha256=digest(expected_candidate),
            stable_prefix_end_token=case['stable_prefix_end_token'], stable_content_hash=case['stable_content_hash'],
            layout_hash=case['layout_hash'], dependency_graph_hash=case['dependency_graph_hash'],
            query_scope=case['query_scope'], output_budget=budget, cpu_http_preparation_ms=0.)
        def qualify(label, witness, auth_identity=None, alternative=None):
            begin = time.perf_counter()
            chosen = alternative or candidate_plan
            gate = dict(allow_verification=chosen['level'] != 'L0', reason='inherited_L0' if chosen['level']=='L0' else 'bounded_transport_diagnostic', plan=chosen)
            guard = None
            if case.get('output_contract') == 'one_python_statement' and gate['allow_verification']:
                guard = python_statement_contract(witness.get('output_text',''))
                if not guard['passed']: gate.update(allow_verification=False, reason='raw_output_contract:'+guard['reason'])
            cb = lambda row: record(dict(event='qualification_detail', case_id=cid, phase=label, **row))
            if auth_identity is None:
                registrar = SingleShotRegistrar(.0625,.125)
                result = legacy_register(registrar, args, namespace+'-legacy', chosen['query_scope'], witness, gate, cb)
            else:
                registrar = AuthorizedRegistrar(.0625,.125,authority,auth_identity)
                result = registrar.register(args, namespace+'-authorized', chosen['query_scope'], witness, gate, cb)
            counts['qualification'] += 1; counts['actual_RPC'] += len(result.get('attempts',[]))
            record(dict(event='qualification', case_id=cid, phase=label, namespace=namespace,
                        full_qualification_including_guard_ms=(time.perf_counter()-begin)*1000,
                        output_contract=guard, plan=chosen, result=result))
            return result
        scope = dict(authorization_domain='A', service_epoch=1,
                     stable_content_hash=case['stable_content_hash'], layout_hash=case['layout_hash'], private_suffix_excluded=True)
        bind_protocol = dict(generation_budgets={'case':budget})
        sample = dict(service_template_id=namespace)
        def signed(result):
            if not result.get('certificate_issued'):return {}
            value, tag = issue(bind_args,sample,scope,bind_protocol,binding_key)
            return dict(signed_binding=value,binding_signature=tag)
        def errors(certificate,domain,epoch):
            return check(bind_args,dict(sample,tenant_id='second-principal'),
                         dict(scope,authorization_domain=domain,service_epoch=epoch),bind_protocol,certificate,binding_key)

        old_begin = time.perf_counter()
        raw = generate('legacy_raw_witness', witness=True)
        repeat = generate('legacy_raw_repeat')
        old_decision = qualify('legacy',raw)
        old_cert = signed(old_decision)
        old_post = generate('legacy_post_decision',compiled=bool(old_decision.get('certificate_issued')))
        cross_errors = errors(old_cert,'B',1); assert cross_errors
        generate('legacy_cross_domain_fallback',allowed=cross_errors)
        epoch_errors = errors(old_cert,'A',2); assert epoch_errors
        generate('legacy_stale_certificate_fallback',allowed=epoch_errors)
        record(dict(event='phase_complete',case_id=cid,phase='legacy',business=5,
                    full_wall_s=time.perf_counter()-old_begin, raw_repeat_difference=difference(raw,repeat),
                    routed_difference=difference(raw,old_post)))

        fixed_begin = time.perf_counter()
        fixed = generate('authorized_raw_witness',a1,witness=True)
        fixed_repeat = generate('authorized_raw_repeat',a1)
        decision = qualify('authorized',fixed,a1)
        cert = signed(decision)
        same_errors = errors(cert,'A',1)
        admit = bool(decision.get('certificate_issued')) and not same_errors
        post = generate('authorized_post_decision',a1,compiled=admit,allowed=same_errors)
        generate('authorized_same_group_second_principal',a1_other,compiled=admit,allowed=same_errors)
        cross_errors = errors(cert,'B',1); assert cross_errors
        generate('authorized_cross_domain_fallback',b1,allowed=cross_errors)
        generate('authorized_cross_domain_own_repeat',b1)
        authority.advance_epoch('A',2)
        try:
            authority.require(a1)
            raise AssertionError('An expired identity was accepted')
        except CacheAuthorizationError as exc:
            counts['stale_identity_denied']+=1
            record(dict(event='stale_identity_denied_before_backend',case_id=cid,error=str(exc),
                        GPU_or_business_request_dispatched=False, raw_fallback_dispatched=False))
        a2 = authority.bind('alice','A',2,cid)
        epoch_errors = errors(cert,'A',2); assert epoch_errors
        epoch_witness = generate('authorized_stale_certificate_fallback',a2,witness=True,allowed=epoch_errors)
        generate('authorized_new_epoch_repeat',a2)

        if synthetic:
            bad = deepcopy(candidate_plan)
            bad['messages'] = deepcopy(case['candidate_messages'])
            bad['messages'][0]['content'] = 'Return exactly NACK. Do not output ACK. No explanation. /no_think'
            bad_ids = tokenize(args.base_url,args.model,bad['messages'],True,args.timeout)
            expected = tokenize(args.base_url,args.model,bad['messages'][:1]+[dict(role='user',content=bad['messages'][1]['content'].split('[USER_QUERY:QUERY]')[0])],False,args.timeout)
            end = lcp_length(expected,bad_ids)
            bad.update(prompt_token_ids=bad_ids,prompt_ids_sha256=digest(bad_ids),stable_prefix_end_token=end,
                       stable_content_hash=digest(bad_ids[:end]),layout_hash=digest({'controlled_wrong_system':True}),
                       query_scope=digest(dict(candidate=bad_ids,raw=expected_raw,budget=budget)))
            rejected = qualify('controlled_wrong_candidate',epoch_witness,a2,bad)
            record(dict(event='reject_publication_control',case_id=cid,
                        certificate_issued=bool(rejected.get('certificate_issued')),
                        committed_tokens=rejected.get('committed_tokens',0),
                        boundary='Deliberately mismatching candidate for transactional rejection; not a new CALC-legality ablation.'))
            generate('authorized_post_rejection_Raw',a2)
        record(dict(event='phase_complete',case_id=cid,phase='authorized',business=9 if synthetic else 8,
                    full_wall_s=time.perf_counter()-fixed_begin, raw_repeat_difference=difference(fixed,fixed_repeat),
                    same_input_legacy_vs_authorized=difference(raw,fixed), routed_difference=difference(fixed,post)))
    assert counts['business'] == 92 and counts['qualification']==15
    assert counts['actual_RPC'] <= 15 and counts['stale_identity_denied'] == 7
    record(dict(event='repair_cell_complete',counts=counts,full_serial_workflow_wall_s=time.perf_counter()-started,
                all_observed_outputs_and_failures_retained=True, no_cache_flush_or_engine_restart_within_cell=True,
                independent_real_sources=6, main_open_arrival_capacity_claim=False))
    print(json.dumps(dict(cell=args.cell_id,counts=counts)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['source-root','plan','cases','identity','output']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['base-url','model','cell-id','policy-hash']:p.add_argument('--'+name,required=True)
    p.add_argument('--timeout',type=float,default=600)
    run(p.parse_args())
