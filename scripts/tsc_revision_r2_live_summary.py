"""Independent all-route quality, admission and actual serving-cost audit."""
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_live import load_metrics
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.tsc_revision_r2_select_policy import percentile
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.tsc_revision_r1r_output_horizon import horizon_measures

MODELS={'qwen':'Qwen3-8B','mistral':'Mistral-7B-Instruct-v0.3','llama':'Llama-3.1-8B-Instruct'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def clustered_ci(pairs,draws=3000):
    bysource=defaultdict(lambda:defaultdict(list))
    for r in pairs:bysource[r['source_group']][r['repeat']].append(r)
    sources=sorted(bysource);repeats=sorted({r['repeat'] for r in pairs});rng=random.Random(10672128)
    reduced={s:{rep:(sum(r['raw_ready_ttft_ms'] for r in rs),sum(r['ready_ttft_ms'] for r in rs)) for rep,rs in reps.items()} for s,reps in bysource.items()};values=[]
    for _ in range(draws):
        raw=policy=0.;chosen=rng.choices(repeats,k=len(repeats))
        for source in rng.choices(sources,k=len(sources)):
            for rep in chosen:
                x,y=reduced[source][rep];raw+=x;policy+=y
        values.append(100*(1-policy/raw))
    return percentile(values,.025),percentile(values,.975)

def audit_cell(directory,expected,freeze_sha,catalog):
    closed=json.loads((directory/'summary.json').read_text(encoding='utf-8'));rows=read(directory/'raw.jsonl');errors=[]
    if not closed['execution_complete'] or sha(directory/'raw.jsonl')!=closed['raw_file_sha256']:errors.append('completion/hash')
    metrics=load_metrics(directory/'metrics.jsonl');manifest=json.loads((directory/'runtime_manifest.json').read_text(encoding='utf-8'))
    if manifest['freeze_sha256']!=freeze_sha or manifest['sessions_sha256']!=closed['sessions_sha256']:errors.append('runtime/input freeze')
    business=[r for r in rows if r['row_type'] in ('warm','future')];positions=[(r['session_id'],r['turn_id']) for r in business]
    if len(set(positions))!=len(positions) or set(positions)!={(sid,t) for sid in expected for t in range(10)}:errors.append('session/turn coverage')
    if len({r['request_id'] for r in business})!=len(business):errors.append('duplicate business request')
    requests={};responses={};decisions={};witnesses={};plans={};attempts=0;published=0;compiled_hits=0
    for r in rows:
        kind=r['row_type']
        if kind=='prospective_plan':plans[(r['certificate_namespace'],r['query_scope'])]=r;continue
        if kind=='verification_request':
            rid=r['request_id'];requests[rid]=r
            if r['prompt_ids_sha256']!=digest(r['payload']['prompt_token_ids']) or not r['request_hash_computed_before_dispatch']:errors.append('verification pre-dispatch hash')
            event=metrics.get(rid)
            if not event or event['prompt_tokens']!=len(r['payload']['prompt_token_ids']):errors.append('verification metric')
            continue
        if kind=='verification_response':responses[r['request_id']]=r['response'];continue
        key=(r['certificate_namespace'],r['query_scope'])
        if kind=='verification':
            if key in decisions:errors.append('duplicate decision for scope')
            decisions[key]=r;attempts+=len(r['attempts'])
            if closed['policy']=='margin-benefit' and len(r['attempts'])>1:errors.append('single-shot violated')
            witness=witnesses.get(key)
            for attempt in r['attempts']:
                rid=attempt.get('request_id');request=requests.get(rid);response=responses.get(rid)
                if request is None or response is None:errors.append('missing request/response');continue
                payload=request['payload'];n=payload['verify_start_token']
                if witness is None or payload['prompt_token_ids'][n:]!=witness['output_token_ids'] or payload['reference_raw_margins']!=witness['reference_margins'][:-1]:errors.append('actual witness forced path')
                if payload['stable_content_hash']!=digest(payload['prompt_token_ids'][:payload['stable_prefix_end_token']]):errors.append('qualification stable identity')
                if not response['certificate_issued']:published+=int(response['committed_tokens'])
            if r['certificate_issued']:
                if not witness or witness['finish_reason']!='stop' or not witness.get('witness_available'):errors.append('missing natural-stop witness')
                if closed['policy']=='margin-benefit':
                    plan=plans.get(key)
                    if not plan or not plan['allow_verification'] or plan['estimated_saved_ms']<=plan['safety_adjusted_cost_ms']:errors.append('prospective gate violation')
                    if min(witness['reference_margins'])<catalog['raw_token_margin_floor'] or r['candidate_margin_min']<catalog['candidate_token_margin_floor'] or r['terminal_stop_margin']<catalog['candidate_token_margin_floor'] or not r['minimum_margin_guard_passed']:errors.append('pointwise violation')
                    if r['selected_level']!=catalog['models'][witness['model']][witness['family']]['level']:errors.append('catalog level violation')
            continue
        if kind not in ('warm','future'):errors.append('unknown row');continue
        sample=expected.get(r['session_id']);event=metrics.get(r['request_id']);ids=r['prompt_token_ids']
        if sample is None or (sample['revision_source_group'],sample['revision_family'])!=(r['source_group'],r['family']):errors.append('source/family identity');continue
        if not (r['success'] and r['stream_done'] and r['prompt_ids_available'] and r['token_ids_available'] and len(ids)==r['prompt_tokens'] and len(r['output_token_ids'])==r['completion_tokens'] and digest(ids)==r['prompt_ids_sha256']):errors.append('actual IDs/usage/hash')
        if not event or event['prompt_tokens']!=len(ids) or r['prefix_hit_tokens']!=event['prefix_hit_tokens'] or r['new_prefill_tokens']!=len(ids)-event['prefix_hit_tokens']:errors.append('business actual metric')
        score,metric,source=standard_score(sample['dataset'],sample['task'],r['output_text'],sample.get('answer',''))
        if (score,metric,source)!=(r['task_score'],r['task_metric'],r['metric_source']):errors.append('official score')
        if r['scope_first_raw_business']:
            witnesses.setdefault(key,r)
            if r.get('witness_available'):
                body={'choices':[{'token_ids':r['output_token_ids'],'finish_reason':r['finish_reason'],
                     'message':{'content':r['output_text']},'logprobs':{'content':r['raw_generation_logprob_content']}}]}
                _,margins,_,_=extract_raw_tokens_and_margins(body)
                if margins!=r['reference_margins']:errors.append('actual LP vector recomputation')
        if r['effective_level']!='L0':
            decision=decisions.get(key)
            if not decision or not decision['certificate_issued'] or decision['selected_level']!=r['effective_level']:errors.append('uncertified compiled business')
            elif digest(ids[:decision['stable_prefix_tokens']])!=decision['stable_prefix_hash']:errors.append('compiled prompt stable hash')
            elif event and event['prefix_hit_tokens']>=decision['committed_tokens']:compiled_hits+=1
        if r['scope_invalid_admission']:errors.append('reported invalid scope')
    if set(requests)!=set(responses):errors.append('incomplete RPC result')
    if len(requests)!=attempts or attempts!=closed['verification_calls']:errors.append('verification count')
    if published:errors.append('rejected publication')
    if closed['policy']=='margin-benefit':
        env=manifest['gate_and_trace_environment']
        if float(env['CONTRACTKV_MIN_RAW_TOKEN_MARGIN'])!=catalog['raw_token_margin_floor'] or float(env['CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN'])!=catalog['candidate_token_margin_floor']:errors.append('backend floor mismatch')
    control=json.loads((directory/'pre_measurement_control.summary.json').read_text(encoding='utf-8'))
    if not all(control[k] for k in ('cold_read_decisions_agree','cached_read_observed','no_unapproved_or_generic_read','zero_rejected_publication')):errors.append('pre-measurement control')
    fullcontrol=directory/'pre_measurement_full_ids.jsonl'
    if fullcontrol.exists():
        records=read(fullcontrol)
        if len(records)!=21:errors.append('control full logging count')
        for r in records:
            if r['row_type']=='control_raw_generation':
                ids=r['prompt_token_ids'];response=r['response'];event=metrics.get(r['request_id'])
                if r['prompt_ids_sha256']!=digest(ids) or response['prompt_token_ids']!=ids or response['usage']['prompt_tokens']!=len(ids) or not event or event['prompt_tokens']!=len(ids):errors.append('control actual raw IDs')
            elif r['row_type']=='control_verification_request':
                if r['prompt_ids_sha256']!=digest(r['payload']['prompt_token_ids']) or not r['request_hash_computed_before_dispatch']:errors.append('control verification requesthash')
    elif directory.parents[1].name!='development_pilot_v1':errors.append('missing full infrastructure-control IDs')
    return {'cell':directory.name,'errors':sorted(set(errors)),'business_requests':len(business),'future_requests':sum(r['row_type']=='future' for r in rows),'verification_calls':attempts,'rejected_published_tokens':published,'actual_compiled_cache_hits':compiled_hits},closed,rows,manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    freeze=json.loads((a.root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol'];fsha=sha(a.root/'freeze.json')
    catalog_path=a.root/'source_snapshot'/config.get('selected_catalog','configs/tsc_revision_r2_selected_catalog_v1.json')
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    pilot=config['schema_version']=='tsc-r2.development-serving-pilot.v1'
    paths={'single-session':'development_sessions_v1.jsonl' if pilot else 'heldout_sealed_sessions_v1.jsonl','template-fanout':'development_fanout_pilot_v1.jsonl' if pilot else 'heldout_fanout_v1.jsonl'}
    expected={};samples={}
    for study,filename in paths.items():
        ss=read(a.root/'source_snapshot/results/tsc_revision_r2/inputs'/filename);samples[study]=ss;expected[study]={}
        for s in ss:
            for tenant in range(config['studies'][study]):
                sid=s['revision_session_id']+(f'-tenant{tenant:02d}' if config['studies'][study]>1 else '')
                expected[study][sid]=s
    cells={};audits=[];missing=[];performance=[]
    for study,key,policy,repeat in itertools.product(config['studies'],MODELS,config['policies'],range(1,config['repeats']+1)):
        name=f'{study}_{key}_{policy}_r{repeat}';base=a.root/'cells'/name
        if not (base/'summary.json').exists():missing.append(name);continue
        audit,summary,rows,manifest=audit_cell(base,expected[study],fsha,catalog);audits.append(audit)
        if summary['catalog_sha256']!=sha(catalog_path):audit['errors'].append('catalog hash')
        if summary['policy']!=policy or summary['repeat']!=repeat or summary['study']!=study:audit['errors'].append('cell label')
        futures=[r for r in rows if r['row_type']=='future'];wall=summary['wall_s_including_all_setup_and_verification']
        cells[(study,MODELS[key],policy,repeat)]=(summary,rows,manifest)
        performance.append({'cell':name,'study':study,'model':MODELS[key],'policy':policy,'repeat':repeat,'futures':len(futures),'wall_s':wall,'future_goodput_rps':len(futures)/wall,'slo1500_goodput_rps':sum(r['ready_ttft_ms']<=1500 for r in futures)/wall,'mean_ready_ttft_ms':statistics.fmean(r['ready_ttft_ms'] for r in futures),'p99_ready_ttft_ms':percentile([r['ready_ttft_ms'] for r in futures],.99),'verification_calls':summary['verification_calls'],'compiled_futures':sum(r['effective_level']!='L0' for r in futures)})
    pairs=[];comparison=[];quality=[];decisions=[]
    for (study,model,policy,repeat),(summary,rows,manifest) in cells.items():
        witnesses={};plans={}
        for r in rows:
            if r['row_type'] in ('warm','future') and r['scope_first_raw_business']:witnesses.setdefault((r['certificate_namespace'],r['query_scope']),r)
            elif r['row_type']=='prospective_plan':plans[(r['certificate_namespace'],r['query_scope'])]=r
            elif r['row_type']=='verification':
                key=(r['certificate_namespace'],r['query_scope']);witness=witnesses.get(key);gate=plans.get(key,{})
                decisions.append({'study':study,'model':model,'policy':policy,'repeat':repeat,'family':r['family'],'certificate_namespace':key[0],'query_scope':key[1],'selected_level':r['selected_level'],'issued':r['certificate_issued'],'actual_GPU_verification_calls':len(r['attempts']),'failure_reason':r['failure_reason'],'complete_controller_verification_ms':r['complete_verification_ms'],'pre_business_planning_ms':r.get('pre_business_planning_ms'),'post_business_registration_ms':r.get('post_business_registration_ms'),'verification_RPC_ms':sum(x['verification_ms'] for x in r['attempts']),'rejected_RPC_ms':sum(x['verification_ms'] for x in r['attempts'] if not x.get('certificate_issued')),'raw_full_min_including_eos':min(witness['reference_margins']) if witness and witness.get('witness_available') else None,'prospective_allowed':gate.get('allow_verification'),'prospective_reason':gate.get('reason'),'predicted_saved_ms':gate.get('estimated_saved_ms'),'predicted_cost_ms':gate.get('estimated_cost_ms'),'declared_reuse_hint':gate.get('declared_remaining_reuse_hint')})
    for (study,model,policy,repeat),(summary,rows,manifest) in cells.items():
        if policy=='raw-order' or (study,model,'raw-order',repeat) not in cells:continue
        refsum,refrows,refmanifest=cells[(study,model,'raw-order',repeat)]
        if manifest['declared_gpu_lane']!=refmanifest['declared_gpu_lane']:audits.append({'cell':summary['cell'],'errors':['paired GPU lane differs']})
        raw={(r['session_id'],r['turn_id']):r for r in refrows if r['row_type']=='future'}
        witnesses={}
        for r in rows:
            if r['row_type'] in ('warm','future') and r['scope_first_raw_business']:
                witnesses.setdefault((r['certificate_namespace'],r['query_scope']),r)
        for r in rows:
            if r['row_type']!='future':continue
            ref=raw[(r['session_id'],r['turn_id'])]
            horizon={'reference_returned_tokens':None,'future_returned_tokens':len(r['output_token_ids']),'positions_beyond_reference_length':None,'witness_ids_available':False,'first_divergence_from_witness':None,'future_positions_from_first_divergence':None}
            if r['effective_level']!='L0':
                witness=witnesses[(r['certificate_namespace'],r['query_scope'])]
                horizon=horizon_measures(len(witness['output_token_ids']),r['output_token_ids'],witness['output_token_ids'])
            pairs.append({'study':study,'model':model,'policy':policy,'repeat':repeat,'source_group':r['source_group'],'family':r['family'],'session_id':r['session_id'],'turn_id':r['turn_id'],'effective_level':r['effective_level'],'raw_score':ref['task_score'],'candidate_score':r['task_score'],'quality_drop':ref['task_score']-r['task_score'],'first_diverging_token':first_divergence(ref['output_token_ids'],r['output_token_ids']),'raw_output_tokens':len(ref['output_token_ids']),'candidate_output_tokens':len(r['output_token_ids']),'raw_finish':ref['finish_reason'],'candidate_finish':r['finish_reason'],'raw_ready_ttft_ms':ref['ready_ttft_ms'],'ready_ttft_ms':r['ready_ttft_ms'],**horizon})
    for study,model,policy in itertools.product(config['studies'],MODELS.values(),[x for x in config['policies'] if x!='raw-order']):
        pp=[r for r in pairs if (r['study'],r['model'],r['policy'])==(study,model,policy)]
        if not pp:continue
        for family in ('ALL',*sorted({r['family'] for r in pp})):
            group=pp if family=='ALL' else [r for r in pp if r['family']==family]
            compiled=[r for r in group if r['effective_level']!='L0']
            quality.append({'study':study,'model':model,'policy':policy,'family':family,'pairs':len(group),'compiled_pairs':len(compiled),'all_material_drops':sum(r['quality_drop']>.03 for r in group),'compiled_material_drops':sum(r['quality_drop']>.03 for r in compiled),'fallback_material_drops':sum(r['quality_drop']>.03 and r['effective_level']=='L0' for r in group),'compiled_ID_divergences':sum(r['first_diverging_token']!=-1 for r in compiled),'max_compiled_drop':max((r['quality_drop'] for r in compiled),default=None),'distinct_sources':len({r['source_group'] for r in group}),'compiled_outputs_beyond_witness_length':sum(r['positions_beyond_reference_length']>0 for r in compiled),'positions_beyond_witness_length':sum(r['positions_beyond_reference_length'] for r in compiled),'compiled_divergences_from_witness':sum(r['first_divergence_from_witness']!=-1 for r in compiled),'raw_mean_output_tokens':statistics.fmean(r['raw_output_tokens'] for r in group),'policy_mean_output_tokens':statistics.fmean(r['candidate_output_tokens'] for r in group)})
        available=sorted({r['repeat'] for r in pp});rawf=[];policf=[];rawwall=policywall=0;gains=[]
        for repeat in available:
            rs,rr,_=cells[(study,model,'raw-order',repeat)];ps,pr,_=cells[(study,model,policy,repeat)]
            rawf += [r for r in rr if r['row_type']=='future'];policf += [r for r in pr if r['row_type']=='future'];rawwall+=rs['wall_s_including_all_setup_and_verification'];policywall+=ps['wall_s_including_all_setup_and_verification'];gains.append(rs['wall_s_including_all_setup_and_verification']/ps['wall_s_including_all_setup_and_verification'])
        lo,hi=clustered_ci(pp)
        comparison.append({'study':study,'model':model,'policy':policy,'paired_repeats':len(available),'pairs':len(pp),'full_wall_goodput_multiplier':rawwall/policywall,'paired_repeat_multiplier_min':min(gains),'paired_repeat_multiplier_max':max(gains),'raw_ready_mean_ms':statistics.fmean(r['ready_ttft_ms'] for r in rawf),'policy_ready_mean_ms':statistics.fmean(r['ready_ttft_ms'] for r in policf),'ready_mean_reduction_pct':100*(1-statistics.fmean(r['ready_ttft_ms'] for r in policf)/statistics.fmean(r['ready_ttft_ms'] for r in rawf)),'ready_mean_source_repeat_ci95_low':lo,'ready_mean_source_repeat_ci95_high':hi,'raw_ready_p99_ms':percentile([r['ready_ttft_ms'] for r in rawf],.99),'policy_ready_p99_ms':percentile([r['ready_ttft_ms'] for r in policf],.99)})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,values in [('performance_by_cell_v1.csv',performance),('quality_pairs_v1.csv',pairs),('quality_summary_v1.csv',quality),('performance_comparison_v1.csv',comparison),('scope_decisions_v1.csv',decisions)]:
        if values:write(a.output/name,values)
    result={'schema_version':'tsc-r2.live-completion-audit.v1','execution_complete':not missing and not any(x['errors'] for x in audits) and len(cells)==config['expected_cells'],'missing_cells':missing,'complete_cells':len(cells),'expected_cells':config['expected_cells'],'measured_futures':sum(x.get('future_requests',0) for x in audits),'expected_futures':config['expected_future_requests'],'cases':audits,'development_only':pilot,'scientific_success_is_separate':True,'ci_unit':'Source template and paired fresh repeat; all turns/tenants remain clustered. Pilot has one repeat and cannot establish repeat uncertainty.','full_wall_uncertainty':'Paired repeat min/max, not a source-cluster wall confidence interval.'}
    if result['measured_futures']!=config['expected_future_requests']:result['execution_complete']=False
    (a.output/'completion_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ('cases','missing_cells')}));return 0 if result['execution_complete'] or a.allow_partial else 2

if __name__=='__main__':raise SystemExit(main())
