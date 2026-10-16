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
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci

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

from scripts.tsc_revision_r4_audit_cell import audit_cell

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    freeze=json.loads((a.root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol'];fsha=sha(a.root/'freeze.json')
    models={k:MODELS[k] for k in config['models']}
    catalog_path=a.root/'source_snapshot'/config.get('selected_catalog','configs/tsc_revision_r2_selected_catalog_v1.json')
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    pilot=config.get('development_only',False)
    paths=config['input_files']
    expected={};samples={}
    for study,filename in paths.items():
        ss=read(a.root/'source_snapshot'/filename);samples[study]=ss;expected[study]={}
        for s in ss:
            for tenant in range(config['studies'][study]):
                sid=s['revision_session_id']+(f'-tenant{tenant:02d}' if config['studies'][study]>1 else '')
                expected[study][sid]=s
    cells={};audits=[];missing=[];performance=[]
    for study,key,policy,repeat in itertools.product(config['studies'],models,config['policies'],range(1,config['repeats']+1)):
        name=f'{study}_{key}_{policy}_r{repeat}';base=a.root/'cells'/name
        if not (base/'summary.json').exists():missing.append(name);continue
        audit,summary,rows,manifest=audit_cell(base,expected[study],fsha,catalog);audits.append(audit)
        if summary['catalog_sha256']!=sha(catalog_path):audit['errors'].append('catalog hash')
        if summary['policy']!=policy or summary['repeat']!=repeat or summary['study']!=study:audit['errors'].append('cell label')
        futures=[r for r in rows if r['row_type']=='future'];wall=summary['wall_s_including_all_setup_and_verification']
        cells[(study,MODELS[key],policy,repeat)]=(summary,rows,manifest)
        performance.append({'cell':name,'study':study,'model':MODELS[key],'policy':policy,'repeat':repeat,'futures':len(futures),'wall_s':wall,'future_goodput_rps':len(futures)/wall,'slo1500_goodput_rps':sum(r['ready_ttft_ms']<=1500 for r in futures)/wall,'mean_ready_ttft_ms':statistics.fmean(r['ready_ttft_ms'] for r in futures),'p99_ready_ttft_ms':percentile([r['ready_ttft_ms'] for r in futures],.99),'verification_calls':summary['verification_calls'],'compiled_futures':sum(r['effective_level']!='L0' for r in futures),'pre_information_rejections':audit['pre_information_rejections'],'post_information_rejections':audit['post_information_rejections']})
    pairs=[];comparison=[];quality=[];decisions=[];raw_repeats=[]
    for study,model in itertools.product(config['studies'],models.values()):
        available=sorted(rep for st,mo,po,rep in cells if (st,mo,po)==(study,model,'raw-order'))
        for first,second in itertools.combinations(available,2):
            _,one,m1=cells[(study,model,'raw-order',first)];_,two,m2=cells[(study,model,'raw-order',second)]
            baseline={(r['session_id'],r['turn_id']):r for r in one if r['row_type']=='future'}
            for r in two:
                if r['row_type']!='future':continue
                ref=baseline[(r['session_id'],r['turn_id'])];same=ref['prompt_token_ids']==r['prompt_token_ids']
                if not same:audits.append({'cell':r['session_id'],'errors':['raw repeat actual prompt IDs differ']})
                raw_repeats.append({'study':study,'model':model,'source_group':r['source_group'],'family':r['family'],'session_id':r['session_id'],'turn_id':r['turn_id'],'repeat1':first,'repeat2':second,'gpu1':m1['declared_gpu_lane'],'gpu2':m2['declared_gpu_lane'],'same_GPU':m1['declared_gpu_lane']==m2['declared_gpu_lane'],'same_actual_prompt_IDs':same,'first_output_ID_divergence':first_divergence(ref['output_token_ids'],r['output_token_ids']),'score_abs_diff':abs(ref['task_score']-r['task_score'])})
    for (study,model,policy,repeat),(summary,rows,manifest) in cells.items():
        witnesses={};plans={}
        for r in rows:
            if r['row_type'] in ('warm','future') and r['scope_first_raw_business']:witnesses.setdefault((r['certificate_namespace'],r['query_scope']),r)
            elif r['row_type']=='prospective_plan':plans[(r['certificate_namespace'],r['query_scope'])]=r
            elif r['row_type']=='verification':
                key=(r['certificate_namespace'],r['query_scope']);witness=witnesses.get(key);gate=plans.get(key,{})
                decisions.append({'study':study,'model':model,'policy':policy,'repeat':repeat,'family':r['family'],'certificate_namespace':key[0],'query_scope':key[1],'selected_level':r['selected_level'],'issued':r['certificate_issued'],'actual_GPU_verification_calls':len(r['attempts']),'failure_reason':r['failure_reason'],'complete_controller_verification_ms':r['complete_verification_ms'],'pre_business_planning_ms':r.get('pre_business_planning_ms'),'post_business_registration_ms':r.get('post_business_registration_ms'),'verification_RPC_ms':sum(x['verification_ms'] for x in r['attempts']),'rejected_RPC_ms':sum(x['verification_ms'] for x in r['attempts'] if not x.get('certificate_issued')),'raw_full_min_including_eos':min(witness['reference_margins']) if witness and witness.get('witness_available') else None,'prospective_allowed':gate.get('allow_verification'),'prospective_reason':gate.get('reason'),'predicted_saved_ms':gate.get('estimated_saved_ms'),'predicted_cost_ms':gate.get('estimated_cost_ms'),'declared_reuse_hint':gate.get('declared_remaining_reuse_hint'),'prefix_state':gate.get('prefix_state'),'coarse_reason':gate.get('coarse_gate',{}).get('reason'),'pre_expected_net_ms':gate.get('expected_net_ms'),'p_joint_lower':gate.get('p_joint_lower'),'p_eligible_upper':gate.get('p_eligible_upper'),'p_pass_given_eligible_lower':gate.get('p_pass_given_eligible_lower'),'post_expected_net_ms':r.get('post_reference_benefit',{}).get('expected_net_ms') if r.get('post_reference_benefit') else None})
    for (study,model,policy,repeat),(summary,rows,manifest) in cells.items():
        if policy=='raw-order' or (study,model,'raw-order',repeat) not in cells:continue
        refsum,refrows,refmanifest=cells[(study,model,'raw-order',repeat)]
        if manifest['declared_gpu_lane']!=refmanifest['declared_gpu_lane']:audits.append({'cell':summary['cell'],'errors':['paired GPU lane differs']})
        for field in ('arrival_trace_sha256','arrival_protocol','arrival_requests','planned_last_arrival_offset_s'):
            if summary.get(field)!=refsum.get(field):audits.append({'cell':summary['cell'],'errors':['paired arrival declaration differs: '+field]})
        for field in ('model_registry_sha256','model_artifact_identity_sha256','installed_distribution_versions','numerical_environment','native_extensions'):
            if manifest[field]!=refmanifest[field]:audits.append({'cell':summary['cell'],'errors':['paired runtime identity differs: '+field]})
        raw={(r['session_id'],r['turn_id']):r for r in refrows if r['row_type']=='future'}
        witnesses={}
        for r in rows:
            if r['row_type'] in ('warm','future') and r['scope_first_raw_business']:
                witnesses.setdefault((r['certificate_namespace'],r['query_scope']),r)
        for r in rows:
            if r['row_type']!='future':continue
            ref=raw[(r['session_id'],r['turn_id'])]
            if r['effective_level']=='L0' and ref['prompt_token_ids']!=r['prompt_token_ids']:audits.append({'cell':summary['cell'],'errors':['raw fallback actual prompt IDs differ from baseline']})
            horizon={'reference_returned_tokens':None,'future_returned_tokens':len(r['output_token_ids']),'positions_beyond_reference_length':None,'witness_ids_available':False,'first_divergence_from_witness':None,'future_positions_from_first_divergence':None}
            if r['effective_level']!='L0':
                witness=witnesses[(r['certificate_namespace'],r['query_scope'])]
                horizon=horizon_measures(len(witness['output_token_ids']),r['output_token_ids'],witness['output_token_ids'])
            pairs.append({'study':study,'model':model,'policy':policy,'repeat':repeat,'source_group':r['source_group'],'family':r['family'],'session_id':r['session_id'],'turn_id':r['turn_id'],'effective_level':r['effective_level'],'raw_score':ref['task_score'],'candidate_score':r['task_score'],'quality_drop':ref['task_score']-r['task_score'],'first_diverging_token':first_divergence(ref['output_token_ids'],r['output_token_ids']),'raw_output_tokens':len(ref['output_token_ids']),'candidate_output_tokens':len(r['output_token_ids']),'raw_finish':ref['finish_reason'],'candidate_finish':r['finish_reason'],'raw_ready_ttft_ms':ref['ready_ttft_ms'],'ready_ttft_ms':r['ready_ttft_ms'],**horizon})
    for study,model,policy in itertools.product(config['studies'],models.values(),[x for x in config['policies'] if x!='raw-order']):
        pp=[r for r in pairs if (r['study'],r['model'],r['policy'])==(study,model,policy)]
        if not pp:continue
        for family in ('ALL',*sorted({r['family'] for r in pp})):
            group=pp if family=='ALL' else [r for r in pp if r['family']==family]
            compiled=[r for r in group if r['effective_level']!='L0']
            quality.append({'study':study,'model':model,'policy':policy,'family':family,'pairs':len(group),'compiled_pairs':len(compiled),'all_material_drops':sum(r['quality_drop']>.03 for r in group),'compiled_material_drops':sum(r['quality_drop']>.03 for r in compiled),'compiled_any_score_decrease':sum(r['quality_drop']>0 for r in compiled),'compiled_score_drop_gt0_01':sum(r['quality_drop']>.01 for r in compiled),'compiled_score_drop_gt0_05':sum(r['quality_drop']>.05 for r in compiled),'fallback_material_drops':sum(r['quality_drop']>.03 and r['effective_level']=='L0' for r in group),'compiled_ID_divergences':sum(r['first_diverging_token']!=-1 for r in compiled),'max_compiled_drop':max((r['quality_drop'] for r in compiled),default=None),'distinct_sources':len({r['source_group'] for r in group}),'compiled_outputs_beyond_witness_length':sum(r['positions_beyond_reference_length']>0 for r in compiled),'positions_beyond_witness_length':sum(r['positions_beyond_reference_length'] for r in compiled),'compiled_divergences_from_witness':sum(r['first_divergence_from_witness']!=-1 for r in compiled),'raw_mean_output_tokens':statistics.fmean(r['raw_output_tokens'] for r in group),'policy_mean_output_tokens':statistics.fmean(r['candidate_output_tokens'] for r in group)})
        available=sorted({r['repeat'] for r in pp});rawf=[];policf=[];rawwall=policywall=0;gains=[]
        for repeat in available:
            rs,rr,_=cells[(study,model,'raw-order',repeat)];ps,pr,_=cells[(study,model,policy,repeat)]
            rawf += [r for r in rr if r['row_type']=='future'];policf += [r for r in pr if r['row_type']=='future'];rawwall+=rs['wall_s_including_all_setup_and_verification'];policywall+=ps['wall_s_including_all_setup_and_verification'];gains.append(rs['wall_s_including_all_setup_and_verification']/ps['wall_s_including_all_setup_and_verification'])
        cold_cohorts={s['revision_source_group']:'cold-wave-pair-'+str(i//2) for i,s in enumerate(samples[study])}
        ci_pairs=[{**r,'source_group':cold_cohorts[r['source_group']]} for r in pp] if study=='single-session' else pp
        cluster_unit='two-source readiness-wave cohort' if study=='single-session' else 'source template including all ten tenants'
        lo,hi=clustered_ci(ci_pairs)
        tail_lo,tail_hi=clustered_tail_ci(ci_pairs) if not missing else (None,None)
        legacy_tail=(None,None);legacy_tail_point=legacy_wall_gain=None
        if policy=='risk-tail':
            legacy_pairs={(r['session_id'],r['turn_id'],r['repeat']):r for r in pairs if (r['study'],r['model'],r['policy'])==(study,model,'previous-refined')}
            if all((r['session_id'],r['turn_id'],r['repeat']) in legacy_pairs for r in pp):
                paired=[{'source_group':r['source_group'],'repeat':r['repeat'],'raw_ready_ttft_ms':legacy_pairs[(r['session_id'],r['turn_id'],r['repeat'])]['ready_ttft_ms'],'ready_ttft_ms':r['ready_ttft_ms']} for r in pp]
                legacy_tail_point=100*(1-percentile([r['ready_ttft_ms'] for r in paired],.99)/percentile([r['raw_ready_ttft_ms'] for r in paired],.99))
                ci_legacy=[{**r,'source_group':cold_cohorts[r['source_group']]} for r in paired] if study=='single-session' else paired
                legacy_tail=clustered_tail_ci(ci_legacy) if not missing else (None,None)
                legacy_wall_gain=sum(cells[(study,model,'previous-refined',repeat)][0]['wall_s_including_all_setup_and_verification'] for repeat in available)/policywall
        comparison.append({'study':study,'model':model,'policy':policy,'paired_repeats':len(available),'pairs':len(pp),'ci_cluster_unit':cluster_unit,'full_wall_goodput_multiplier':rawwall/policywall,'paired_repeat_multiplier_min':min(gains),'paired_repeat_multiplier_max':max(gains),'raw_ready_mean_ms':statistics.fmean(r['ready_ttft_ms'] for r in rawf),'policy_ready_mean_ms':statistics.fmean(r['ready_ttft_ms'] for r in policf),'ready_mean_reduction_pct':100*(1-statistics.fmean(r['ready_ttft_ms'] for r in policf)/statistics.fmean(r['ready_ttft_ms'] for r in rawf)),'ready_mean_cluster_repeat_ci95_low':lo,'ready_mean_cluster_repeat_ci95_high':hi,'raw_ready_p99_ms':percentile([r['ready_ttft_ms'] for r in rawf],.99),'policy_ready_p99_ms':percentile([r['ready_ttft_ms'] for r in policf],.99),'p99_reduction_cluster_repeat_ci95_low':tail_lo,'p99_reduction_cluster_repeat_ci95_high':tail_hi,'new_vs_previous_full_wall_goodput_multiplier':legacy_wall_gain,'new_vs_previous_p99_reduction_pct':legacy_tail_point,'new_vs_previous_p99_reduction_ci95_low':legacy_tail[0],'new_vs_previous_p99_reduction_ci95_high':legacy_tail[1]})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,values in [('performance_by_cell_v1.csv',performance),('quality_pairs_v1.csv',pairs),('quality_summary_v1.csv',quality),('performance_comparison_v1.csv',comparison),('scope_decisions_v1.csv',decisions),('raw_repeat_controls_v1.csv',raw_repeats)]:
        if values:write(a.output/name,values)
    result={'schema_version':'tsc-r4.live-completion-audit.v1','execution_complete':not missing and not any(x['errors'] for x in audits) and len(cells)==config['expected_cells'],'missing_cells':missing,'complete_cells':len(cells),'expected_cells':config['expected_cells'],'measured_futures':sum(x.get('future_requests',0) for x in audits),'expected_futures':config['expected_future_requests'],'cases':audits,'development_only':pilot,'scientific_success_is_separate':True,'ci_unit':'Cold: two-source readiness-wave cohort. Fanout: source template including all tenants. Joint paired fresh repeats. Pilot has one repeat and cannot establish repeat uncertainty.','mean_bootstrap_draws':3000,'p99_bootstrap_draws':2000,'p99_bootstrap_seed':10672129,'full_wall_uncertainty':'Paired repeat min/max, not a source-cluster wall confidence interval.'}
    if result['measured_futures']!=config['expected_future_requests']:result['execution_complete']=False
    (a.output/'completion_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ('cases','missing_cells')}));return 0 if result['execution_complete'] or a.allow_partial else 2

if __name__=='__main__':raise SystemExit(main())
