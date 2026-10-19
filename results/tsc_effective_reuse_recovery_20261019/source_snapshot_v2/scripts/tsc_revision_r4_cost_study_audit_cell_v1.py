# Parent audit_cell SHA256: bbf599fd4fdff76f9f970d24be50b2f7438b70292bacc54d22a82d9c405d0f50
"""Independent all-route audit of staged-gate serving cells."""
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.tsc_revision_live import load_metrics
from scripts.tsc_revision_summarize import read
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract
from scripts.tsc_revision_r4_cost_policy import decide,stage_features,declared_reuses
from scripts.tsc_revision_r2_benefit_policy import prospective_benefit
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def context(rootname):
    root=Path(rootname);snap=root/'source_snapshot'
    freeze=json.loads((root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol']
    previous=json.loads((snap/config['previous_catalog']).read_text(encoding='utf-8'))
    protocol=json.loads((snap/config['generation_protocol']).read_text(encoding='utf-8'))
    return config,previous,protocol


def audit_cell(directory,expected,freeze_sha,catalog):
    root=directory.parents[1];config,previous,protocol=context(str(root))
    closed=json.loads((directory/'summary.json').read_text(encoding='utf-8'));rows=read(directory/'raw.jsonl');errors=[]
    policy=closed['policy'];risk=policy in ('risk-tail','cost-adapted');model=next(r['model'] for r in rows if r['row_type'] in ('warm','future'))
    if not closed['execution_complete'] or sha(directory/'raw.jsonl')!=closed['raw_file_sha256']:errors.append('completion/hash')
    metrics=load_metrics(directory/'metrics.jsonl');manifest=json.loads((directory/'runtime_manifest.json').read_text(encoding='utf-8'))
    if manifest['freeze_sha256']!=freeze_sha or manifest['sessions_sha256']!=closed['sessions_sha256']:errors.append('runtime/input freeze')
    if closed['profile']!=config['profile']:errors.append('profile mismatch')
    if closed['previous_catalog_sha256']!=sha(root/'source_snapshot'/config['previous_catalog']):errors.append('previous catalog changed')
    business=[r for r in rows if r['row_type'] in ('warm','future')];positions=[(r['session_id'],r['turn_id']) for r in business]
    if len(set(positions))!=len(positions) or set(positions)!={(sid,t) for sid in expected for t in range(10)}:errors.append('session/turn coverage')
    if len({r['request_id'] for r in business})!=len(business):errors.append('duplicate business ID')
    owners={}
    for r in business:
        if r['scope_first_decision_business']:owners.setdefault((r['certificate_namespace'],r['query_scope']),r)
    requests={};responses={};decisions={};witnesses={};plans={};contracts={};scope_checks={};postgates={};prefixes=defaultdict(dict)
    attempts=published=compiled_hits=0;prepared_cache={}
    def reconstructed(row):
        key=row['session_id'],row['turn_id']
        if key not in prepared_cache:
            sample=deepcopy(expected[row['session_id']]);sample['revision_session_id']=row['session_id']
            if closed['tenants_per_template']>1:sample['shared_template_id']=row['certificate_namespace']
            args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity=model,policy_hash=freeze_sha)
            prepared_cache[key]=prepare(args,sample,row['turn_id'])
        return prepared_cache[key]
    for r in rows:
        kind=r['row_type'];key=(r.get('certificate_namespace'),r.get('query_scope'))
        if kind=='prospective_plan':
            if key in plans:errors.append('duplicate prospective plan')
            plans[key]=r
            calibration=(catalog['models'][model][closed['study']][r['family']] if risk else previous['models'][model][r['family']])
            if calibration['level']=='L0':
                if r['allow_verification'] or r['plan'] is not None:errors.append('inherited L0 gate')
            elif risk:
                owner=owners.get(key)
                if owner is None:errors.append('missing first decision request');continue
                if r['scope_case']!={'segments':reconstructed(owner)[0]['segments']}:errors.append('scope case reconstruction')
                reuses=declared_reuses(r['turn_id'],closed['tenants_per_template'],protocol['runtime']['concurrency'])
                hint='warm' if prefixes[key[0]] else 'cold'
                coarse=decide(stage_features(calibration,closed['profile'],hint,closed['study']),reuses)
                if coarse!=r['coarse_gate'] or hint!=r['prefix_state_hint']:errors.append('coarse staged gate replay')
                if not coarse['allow_verification']:
                    if r['plan'] is not None or r['allow_verification']:errors.append('rejected coarse gate prepared/allowed')
                    if owner['scope_first_raw_business'] or owner['witness_requested']:errors.append('unneeded LP after coarse rejection')
                else:
                    plan=r.get('plan')
                    if not plan:errors.append('missing fine plan');continue
                    state='warm' if plan['stable_content_hash'] in prefixes[key[0]] else 'cold'
                    features=stage_features(calibration,closed['profile'],state,closed['study'],plan)
                    fine=decide(features,reuses)
                    if features!=r['fine_cost_features'] or r['prefix_hash_match']!=(state=='warm'):errors.append('fine state/features')
                    if any(r.get(k)!=v for k,v in fine.items()):errors.append('fine staged gate replay')
                    if not fine['allow_verification'] and (owner['scope_first_raw_business'] or owner['witness_requested']):errors.append('unneeded LP after fine rejection')
            elif r.get('plan'):
                plan=r['plan'];reuses=previous['expected_query_repetitions_per_registered_tenant_hint']*closed['tenants_per_template']-min(protocol['runtime']['concurrency'],closed['tenants_per_template'])
                replay=prospective_benefit(max(0,plan['stable_full_blocks']-calibration['raw_native_prefix_full_blocks_p95']),16,reuses,
                    calibration['prefill_ms_per_token'],calibration['verification_rpc_p95_ms'],plan['cpu_http_preparation_ms'],previous['benefit_safety_factor'],calibration['complete_qualification_p95_ms'])
                if any(r.get(k)!=v for k,v in replay.items()):errors.append('previous benefit replay')
            continue
        if kind=='reference_scope_contract':
            w=witnesses.get(key);plan=plans.get(key,{})
            if not risk or not w:errors.append('unexpected/missing scope witness');continue
            check=reference_scope_contract(plan['scope_case'],w['output_text'],plan['max_literal_answer_words'],w.get('reference_margins'),plan['nonliteral_ambiguity_boundary'])
            if check!=r['check']:errors.append('scope eligibility replay')
            scope_checks[key]=check;continue
        if kind=='post_reference_benefit_gate':
            plan=plans[key];replay=decide(plan['fine_cost_features'],plan['declared_remaining_reuse_hint'],True)
            if any(r.get(k)!=v for k,v in replay.items()):errors.append('post-reference benefit replay')
            if not scope_checks.get(key,{}).get('shareable_query_scope'):errors.append('postgate outside shareable scope')
            postgates[key]=r;continue
        if kind=='output_contract_check':
            w=witnesses.get(key)
            if not r['output_unchanged'] or not w or python_statement_contract(w['output_text'])!=r['check']:errors.append('Python contract replay')
            contracts[key]=r['check'];continue
        if kind=='verification_request':
            rid=r['request_id'];requests[rid]=r;payload=r['payload'];event=metrics.get(rid)
            if r['prompt_ids_sha256']!=digest(payload['prompt_token_ids']) or not r['request_hash_computed_before_dispatch']:errors.append('verification pre-dispatch hash')
            if not event or event['prompt_tokens']!=len(payload['prompt_token_ids']):errors.append('verification metric')
            if payload['policy_hash']!=freeze_sha:errors.append('verification policy binding')
            continue
        if kind=='verification_response':responses[r['request_id']]=r['response'];continue
        if kind=='verification':
            if key in decisions:errors.append('duplicate scope decision')
            decisions[key]=r;attempts+=len(r['attempts']);w=witnesses.get(key);plan=plans.get(key)
            if len(r['attempts'])>1:errors.append('single-shot violated')
            if not plan:errors.append('missing prospective plan');continue
            if not plan['allow_verification'] and r['attempts']:errors.append('pre-rejected scope made GPU call')
            if key in scope_checks and not scope_checks[key]['shareable_query_scope'] and r['attempts']:errors.append('unshareable scope made GPU call')
            if key in postgates and not postgates[key]['allow_verification'] and r['attempts']:errors.append('post-rejected scope made GPU call')
            if key in contracts and not contracts[key]['passed'] and r['attempts']:errors.append('Python-rejected scope made GPU call')
            for attempt in r['attempts']:
                rid=attempt.get('request_id');request=requests.get(rid);response=responses.get(rid)
                if not request or response is None:errors.append('missing request/response');continue
                payload=request['payload'];n=payload['verify_start_token']
                if not w or payload['prompt_token_ids'][n:]!=w['output_token_ids'] or payload['reference_raw_margins']!=w['reference_margins'][:-1]:errors.append('actual forced witness path')
                if payload['cache_salt']!=freeze_sha+':'+key[0] or payload['stable_content_hash']!=digest(payload['prompt_token_ids'][:payload['stable_prefix_end_token']]):errors.append('qualification namespace/stable identity')
                if not response['certificate_issued']:published+=int(response['committed_tokens'])
            if r['certificate_issued']:
                if not w or w['finish_reason']!='stop' or not w.get('witness_available'):errors.append('missing natural-stop witness')
                else:
                    if min(w['reference_margins'])<catalog['raw_token_margin_floor'] or r['candidate_margin_min']<catalog['candidate_token_margin_floor'] or r['terminal_stop_margin']<catalog['candidate_token_margin_floor'] or not r['minimum_margin_guard_passed']:errors.append('pointwise publication guard')
                    calibration=(catalog['models'][model][closed['study']][w['family']] if risk else previous['models'][model][w['family']])
                    if r['selected_level']!=calibration['level']:errors.append('fixed level violation')
                    if w['family']=='RepoBench' and not contracts.get(key,{}).get('passed'):errors.append('missing Python eligibility')
                if risk and (not scope_checks.get(key,{}).get('shareable_query_scope') or not postgates.get(key,{}).get('allow_verification')):errors.append('issued outside staged scope/cost admission')
                if not plan['allow_verification']:errors.append('issued outside prospective gate')
                prefixes[key[0]][r['stable_prefix_hash']]=r['certificate_hash']
            continue
        if kind not in ('warm','future'):errors.append('unknown row:'+str(kind));continue
        sample=expected.get(r['session_id']);event=metrics.get(r['request_id']);ids=r['prompt_token_ids']
        if sample is None or (sample['revision_source_group'],sample['revision_family'])!=(r['source_group'],r['family']):errors.append('source identity');continue
        if reconstructed(r)[4]!=r['query_scope']:errors.append('query scope identity')
        if not (r['success'] and r['stream_done'] and r['prompt_ids_available'] and r['token_ids_available'] and len(ids)==r['prompt_tokens'] and len(r['output_token_ids'])==r['completion_tokens'] and digest(ids)==r['prompt_ids_sha256']):errors.append('actual IDs/usage/hash')
        if not event or event['prompt_tokens']!=len(ids) or r['prefix_hit_tokens']!=event['prefix_hit_tokens'] or r['new_prefill_tokens']!=len(ids)-event['prefix_hit_tokens']:errors.append('business metric identity')
        score,metric,source=standard_score(sample['dataset'],sample['task'],r['output_text'],sample.get('answer',''))
        if (score,metric,source)!=(r['task_score'],r['task_metric'],r['metric_source']):errors.append('official score')
        if r['scope_first_raw_business']:
            witnesses.setdefault(key,r)
            if r.get('witness_available'):
                body={'choices':[{'token_ids':r['output_token_ids'],'finish_reason':r['finish_reason'],'message':{'content':r['output_text']},'logprobs':{'content':r['raw_generation_logprob_content']}}]}
                if extract_raw_tokens_and_margins(body)[1]!=r['reference_margins']:errors.append('actual LP recomputation')
        if r['effective_level']!='L0':
            decision=decisions.get(key)
            if not decision or not decision['certificate_issued'] or decision['selected_level']!=r['effective_level']:errors.append('uncertified compiled request')
            elif digest(ids[:decision['stable_prefix_tokens']])!=decision['stable_prefix_hash']:errors.append('compiled stable hash')
            elif event and event['prefix_hit_tokens']>=decision['committed_tokens']:compiled_hits+=1
        if r['scope_invalid_admission']:errors.append('reported invalid scope')
    if set(requests)!=set(responses) or len(requests)!=attempts or attempts!=closed['verification_calls']:errors.append('RPC coverage')
    if published:errors.append('rejected publication')
    if policy!='raw-order':
        env=manifest['gate_and_trace_environment']
        if float(env['CONTRACTKV_MIN_RAW_TOKEN_MARGIN'])!=catalog['raw_token_margin_floor'] or float(env['CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN'])!=catalog['candidate_token_margin_floor']:errors.append('backend margin environment')
    if abs(closed['wall_service_end_time']-closed['wall_begin_time']-closed['wall_s_including_all_setup_and_verification'])>1e-6:errors.append('wall clock declaration')
    if max(r['end_time'] for r in business)>closed['wall_service_end_time']:errors.append('wall excludes request drain')
    order={sid:i for i,sid in enumerate(expected)};waves=defaultdict(list)
    for r in business:waves[order[r['session_id']]//protocol['runtime']['concurrency'],r['turn_id']].append(r)
    last={};arrival_rows=None
    if closed.get('arrival_protocol'):
        tables=config['arrival_files'][closed['study']]
        arrival_path=root/'source_snapshot'/(tables[str(closed['repeat'])] if str(closed['repeat']) in tables else tables[model][str(closed['repeat'])])
        arrival_rows,arrival_sha,arrival_trace=load_arrivals(arrival_path,closed['sessions_sha256'],list(expected),closed['tenants_per_template'],protocol['runtime']['concurrency'])
        if arrival_trace.get('model_identity',model)!=model:errors.append('arrival model binding')
        if closed['arrival_protocol']!='frozen_exogenous_shared_wave' or closed['arrival_trace_sha256']!=arrival_sha:errors.append('frozen arrival binding')
        if closed['arrival_requests']!=len(business) or closed['planned_last_arrival_offset_s']!=arrival_trace['waves'][-1]['ready_offset_s']:errors.append('arrival coverage declaration')
    for (cohort,turn),items in sorted(waves.items()):
        readies=[r['first_time']-r['ready_ttft_ms']/1000 for r in items]
        if max(readies)-min(readies)>1e-5:errors.append('shared-wave ready mismatch')
        if arrival_rows is None:
            if turn and abs(readies[0]-last[cohort])>1e-5:errors.append('changed closed-loop ready definition')
        else:
            scheduled=arrival_rows[cohort*protocol['runtime']['concurrency'],turn]
            for r,actual in zip(items,readies):
                ready=closed['wall_begin_time']+scheduled['ready_offset_s'];processing=r['wave_processing_begin_time']
                if abs(actual-ready)>1e-5 or r['planned_ready_offset_s']!=scheduled['ready_offset_s'] or r['planned_ready_time']!=ready or r['wave_index']!=scheduled['wave_index']:errors.append('exogenous ready clock changed')
                if processing+1e-5<ready or r['end_time']>closed['wall_service_end_time']:errors.append('arrival/drain wall boundary')
                if abs(r['queue_before_controller_ms']-max(0,(processing-ready)*1000))>1e-5 or abs(r['ready_latency_ms']-(r['end_time']-ready)*1000)>1e-5:errors.append('arrival queue/latency decomposition')
                submit=r['first_time']-r['ttft_ms']/1000
                if abs(r['controller_to_submit_ms']-max(0,(submit-processing)*1000))>1e-5:errors.append('arrival controller decomposition')
        last[cohort]=max(r['end_time'] for r in items)
    control=json.loads((directory/'pre_measurement_control.summary.json').read_text(encoding='utf-8'))
    if not all(control[k] for k in ('cold_read_decisions_agree','cached_read_observed','no_unapproved_or_generic_read','zero_rejected_publication')):errors.append('pre-measurement control')
    records=read(directory/'pre_measurement_full_ids.jsonl')
    if len(records)!=21:errors.append('control logging coverage')
    for r in records:
        if r['row_type']=='control_raw_generation':
            ids=r['prompt_token_ids'];response=r['response'];event=metrics.get(r['request_id'])
            if r['prompt_ids_sha256']!=digest(ids) or response['prompt_token_ids']!=ids or response['usage']['prompt_tokens']!=len(ids) or not event or event['prompt_tokens']!=len(ids):errors.append('control actual raw IDs')
        elif r['row_type']=='control_verification_request':
            if r['prompt_ids_sha256']!=digest(r['payload']['prompt_token_ids']) or not r['request_hash_computed_before_dispatch']:errors.append('control request hash')
    return {'cell':directory.name,'errors':sorted(set(errors)),'business_requests':len(business),'future_requests':sum(r['row_type']=='future' for r in rows),
            'verification_calls':attempts,'rejected_published_tokens':published,'actual_compiled_cache_hits':compiled_hits,
            'pre_information_rejections':sum(not r['allow_verification'] and r['reason']!='inherited_family_L0' for r in plans.values()),
            'post_information_rejections':sum(not r['allow_verification'] for r in postgates.values())},closed,rows,manifest
