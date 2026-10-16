"""Prespecified latency strata and selective-label admission calibration audit."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write
from scripts.tsc_revision_r2_select_policy import percentile
from scripts.tsc_revision_r4_policy_v2 import reference_scope_contract
from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci


def compact(path):
    summary=json.loads((path/'summary.json').read_text(encoding='utf-8'));rows=read(path/'raw.jsonl')
    business=[r for r in rows if r['row_type'] in ('warm','future')]
    plans={(r['certificate_namespace'],r['query_scope']):r for r in rows if r['row_type']=='prospective_plan'}
    decisions={(r['certificate_namespace'],r['query_scope']):r for r in rows if r['row_type']=='verification'}
    first={}
    for r in business:first.setdefault((r['certificate_namespace'],r['query_scope']),r)
    witness={}
    for r in business:
        if r['scope_first_raw_business']:witness.setdefault((r['certificate_namespace'],r['query_scope']),r)
    return summary,business,plans,decisions,first,witness


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    config=json.loads((a.root/'freeze.json').read_text(encoding='utf-8'))['protocol'];cells=a.root/'cells'
    catalog=json.loads((a.root/'source_snapshot'/config['selected_catalog']).read_text(encoding='utf-8'))
    oldcatalog=json.loads((a.root/'source_snapshot'/config['previous_catalog']).read_text(encoding='utf-8'))
    perf=[];gate_rows=[];errors=[];warm_records=[]
    for path in sorted(cells.glob('*')):
        if not (path/'summary.json').exists():continue
        summary,business,plans,decisions,first,witness=compact(path)
        model=business[0]['model'];study=summary['study'];policy=summary['policy'];repeat=summary['repeat']
        for r in business:
            if r['row_type']!='future':continue
            perf.append({k:r[k] for k in ('study','model','policy','repeat','source_group','family','session_id','turn_id','effective_level','ready_ttft_ms','ttft_ms','latency_ms')})
            perf[-1].update({'ready_latency_ms':r.get('ready_latency_ms',r['latency_ms']+r['ready_ttft_ms']-r['ttft_ms']),
                            'queue_before_controller_ms':r.get('queue_before_controller_ms',0.),'controller_to_submit_ms':r.get('controller_to_submit_ms',max(0,r['ready_ttft_ms']-r['ttft_ms']))})
        if policy!='risk-tail':continue
        oldpath=cells/f'{study}_{next(k for k,v in {"qwen":"Qwen3-8B","mistral":"Mistral-7B-Instruct-v0.3","llama":"Llama-3.1-8B-Instruct"}.items() if v==model)}_previous-refined_r{repeat}'
        previous=compact(oldpath) if (oldpath/'summary.json').exists() else None
        oldfirst=previous[4] if previous else {};oldwitness=previous[5] if previous else {};olddecisions=previous[3] if previous else {};oldplans=previous[2] if previous else {}
        for key,plan in plans.items():
            decision=decisions.get(key);owner=first[key];oldowner=oldfirst.get(key);ow=oldwitness.get(key);od=olddecisions.get(key);op=oldplans.get(key)
            identity=bool(oldowner and owner['prompt_token_ids']==oldowner['prompt_token_ids'] and owner['output_token_ids']==oldowner['output_token_ids'])
            samelevel=bool(op and catalog['models'][model][study][owner['family']]['level']==oldcatalog['models'][model][owner['family']]['level'])
            attempts=decision['attempts'] if decision else [];issued=bool(decision and decision['certificate_issued'])
            features=plan.get('fine_cost_features',{});pre=plan.get('coarse_gate',plan)
            label=None;eligible=None
            if identity and samelevel and ow and od and 'scope_case' in plan:
                scope=reference_scope_contract(plan['scope_case'],ow['output_text'],plan['max_literal_answer_words'],ow.get('reference_margins'),plan['nonliteral_ambiguity_boundary'])
                eligible=bool(scope['shareable_query_scope'] and ow.get('witness_available') and ow['finish_reason']=='stop'
                              and min(ow['reference_margins'],default=-float('inf'))>=.0625
                              and (owner['family']!='RepoBench' or python_statement_contract(ow['output_text'])['passed']))
                # Previous-control rejection before a GPU call is an eligibility label only.
                if not eligible:label=False
                elif od['attempts']:label=bool(od['certificate_issued'])
            record={'study':study,'model':model,'policy':policy,'repeat':repeat,'family':owner['family'],'source_group':owner['source_group'],
                    'certificate_namespace':key[0],'query_scope':key[1],'pre_allowed':plan['allow_verification'],'pre_reason':plan['reason'],
                    'coarse_reason':pre['reason'],'prefix_state':plan.get('prefix_state'),'p_joint_lower':pre.get('p_joint_lower'),
                    'p_eligible_upper':pre.get('p_eligible_upper'),'p_pass_given_eligible_lower':features.get('p_pass_given_eligible_lower'),
                    'expected_net_ms':plan.get('expected_net_ms'),'post_allowed':decision.get('post_reference_benefit',{}).get('allow_verification') if decision and decision.get('post_reference_benefit') else None,
                    'actual_gpu_calls':len(attempts),'actual_issued':issued,'actual_gpu_rpc_ms':sum(x['verification_ms'] for x in attempts),
                    'actual_registration_controller_ms':decision.get('complete_verification_ms') if decision else None,
                    'previous_first_raw_actual_IDs_and_outputs_match':identity,'same_candidate_level':samelevel,
                    'previous_control_gpu_calls':len(od['attempts']) if od else None,'previous_control_issued':bool(od['certificate_issued']) if od else None,
                    'previous_control_rpc_ms':sum(x['verification_ms'] for x in od['attempts']) if od else None,
                    'control_supported_joint_label':label,'control_supported_scope_eligible':eligible,
                    'label_boundary':'Matched previous control evidence, not a new probe of rejected scope; numerical/timing counterfactual is not measured.'}
            gate_rows.append(record)
            for attempt in attempts:
                if plan.get('prefix_state')=='warm':
                    read_tokens=attempt.get('cached_prefix_read_tokens',0)
                    warm_records.append({'study':study,'model':model,'repeat':repeat,'family':owner['family'],'namespace':key[0],'query_scope':key[1],
                                         'actual_cached_prefix_read_tokens':read_tokens,'forecast_warm_miss':read_tokens<=0,'actual_verification_ms':attempt['verification_ms']})
    raw={(r['study'],r['model'],r['repeat'],r['session_id'],r['turn_id']):r for r in perf if r['policy']=='raw-order'}
    pairs=[]
    for r in perf:
        if r['policy']=='raw-order':continue
        ref=raw.get((r['study'],r['model'],r['repeat'],r['session_id'],r['turn_id']))
        if ref:pairs.append({**r,**{'raw_'+k:ref[k] for k in ('ready_ttft_ms','ready_latency_ms','ttft_ms','latency_ms','queue_before_controller_ms','controller_to_submit_ms')}})
    strata=[];groups=defaultdict(list)
    for r in pairs:
        for kind,value in [('global','ALL'),('family',r['family']),('template',r['source_group']),('tenant',r['session_id'])]:
            groups[r['study'],r['model'],r['policy'],kind,value].append(r)
    for (study,model,policy,kind,value),rows in sorted(groups.items()):
        out={'study':study,'model':model,'policy':policy,'stratum':kind,'value':value,'pairs':len(rows),'sources':len({r['source_group'] for r in rows}),'repeats':len({r['repeat'] for r in rows})}
        for field in ('ready_ttft_ms','ready_latency_ms','ttft_ms','latency_ms','queue_before_controller_ms','controller_to_submit_ms'):
            for prefix in ('raw_',''):
                values=[r[prefix+field] for r in rows]
                out[prefix+field+'_mean']=statistics.fmean(values)
                for q in (.5,.95,.99,1.):out[prefix+field+'_p'+str(int(q*100))]=percentile(values,q)
        out['p99_ready_reduction_pct']=100*(1-out['ready_ttft_ms_p99']/out['raw_ready_ttft_ms_p99'])
        # Source/tenant rows are descriptive; few-source family intervals are explicitly exploratory.
        if kind=='family' and not a.allow_partial:
            lo,hi=clustered_tail_ci(rows);out['family_source_repeat_p99_ci95_low']=lo;out['family_source_repeat_p99_ci95_high']=hi
        strata.append(out)
    calibration=[];groups=defaultdict(list)
    for r in gate_rows:
        for group in ('ALL',r['family']):groups[r['study'],r['model'],group].append(r)
    for (study,model,family),rows in sorted(groups.items()):
        labelled=[r for r in rows if r['control_supported_joint_label'] is not None]
        rejected=[r for r in rows if not r['pre_allowed']]
        matchedreject=[r for r in rejected if r['control_supported_joint_label'] is not None]
        observed=[r for r in rows if r['actual_gpu_calls']]
        calibration.append({'study':study,'model':model,'family':family,'plans':len(rows),'pre_rejections':len(rejected),
                            'actual_gpu_calls':sum(r['actual_gpu_calls'] for r in rows),'actual_gpu_issued':sum(r['actual_issued'] for r in observed),
                            'actual_gpu_pass_rate_selected_only':statistics.fmean(r['actual_issued'] for r in observed) if observed else None,
                            'identity_and_level_matched_control_labels':len(labelled),'control_supported_joint_successes':sum(r['control_supported_joint_label'] for r in labelled),
                            'predicted_joint_lower_sum_over_control_labelled':sum(r['p_joint_lower'] or 0 for r in labelled),
                            'pre_rejections_with_control_label':len(matchedreject),'control_supported_successes_rejected':sum(r['control_supported_joint_label'] for r in matchedreject),
                            'control_supported_failures_screened':sum(not r['control_supported_joint_label'] for r in matchedreject),
                            'previous_control_GPU_calls_screened_matched':sum(r['previous_control_gpu_calls'] or 0 for r in matchedreject),
                            'previous_control_rpc_ms_screened_matched':sum(r['previous_control_rpc_ms'] or 0 for r in matchedreject),
                            'selection_bias_boundary':'Accepted-only pass rate is selective; control labels require same first raw input/output IDs and candidate level. No unseen rejected-scope success label is invented.'})
    a.output.mkdir(parents=True,exist_ok=True)
    for name,rows in [('request_latency_pairs_v1.csv',pairs),('latency_strata_v1.csv',strata),('gate_calibration_scopes_v1.csv',gate_rows),('gate_calibration_summary_v1.csv',calibration),('warm_forecast_audit_v1.csv',warm_records)]:
        if rows:write(a.output/name,rows)
    result={'schema_version':'tsc-r4.strata-calibration.v1','errors':errors,'paired_request_count':len(pairs),'scope_count':len(gate_rows),
            'warm_forecasts_with_GPU_probe':len(warm_records),'warm_forecast_actual_misses':sum(r['forecast_warm_miss'] for r in warm_records),
            'request_level_retained':True,'strata':['global','predefined family','source template','tenant','individual request'],
            'partial':a.allow_partial,'not_a_formal_probability_guarantee':True,'new_rejected_scope_outcomes_not_probed':True}
    (a.output/'strata_calibration_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
