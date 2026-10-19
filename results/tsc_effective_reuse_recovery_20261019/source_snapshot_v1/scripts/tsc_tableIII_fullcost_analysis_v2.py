"""Full frozen-matrix cost coverage and paired quality, without slack subtraction."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score
from scripts.phase12_task_quality_sanity import score_answer as original_sanity_score


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in p.open(encoding='utf-8') if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def future_key(r):return (r['session_id'],int(r['turn_id']))
def write_json(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def analyze(study,output):
    if output.exists():raise FileExistsError('Do not replace an analysis attempt')
    protocol=read(study/'protocol_v1.json')
    assert sha(Path(standard_score.__code__.co_filename))==sha(study/'source_snapshot/scripts/phase20a_official_quality.py'),'Use the archived scoring definition unchanged'
    assert sha(Path(original_sanity_score.__code__.co_filename))==sha(study/'source_snapshot/scripts/phase12_task_quality_sanity.py'),'Use the original driver sanity-score definition unchanged'
    state=read(study/'execution_state_v1.json')
    assert state['status']=='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS' and state['formal_GPU_cells_completed']==24
    assert len(state['completed_pairs'])==12
    output.mkdir(parents=True)
    all_cost=[];quality=[];coverage=[];inventories=[]
    for model in protocol['models']:
        samples={x['phase19b_session_id']:x for x in rows(study/'inputs'/model['session_file'])}
        for repeat in (1,2,3):
            matches=[study/x for x in state['completed_pairs'] if x.startswith('cells/'+model['key']+'_r'+str(repeat)+'/')]
            assert len(matches)==1;pair=matches[0];paired=read(pair/'pair_completion_v1.json')
            assert paired['status']=='complete' and paired['model']==model['model']
            rawrows=rows(pair/'raw/requests.jsonl');candidate=rows(pair/'contract/requests.jsonl')
            raw={future_key(r):r for r in rawrows if r.get('row_type')=='future'}
            compiled={future_key(r):r for r in candidate if r.get('row_type')=='future'}
            assert set(raw)==set(compiled) and len(raw)==model['sessions']*9
            assert all(r['success'] for r in list(raw.values())+list(compiled.values()))
            for policy in ('raw','contract'):
                cell=pair/policy;completion=read(cell/'completion_v1.json')
                for f in completion['files']:assert sha(cell/f['path'])==f['sha256']
                inventories.append(dict(model=model['model'],repeat=repeat,policy=policy,path=str(cell),
                    complete_client_wall_s=completion['checks']['client_wall_s'],
                    service_wall_s=completion['checks']['service_wall_with_drain_s'],
                    final_drain_s=completion['checks']['final_drain_s']))
            audit=rows(pair/'contract/audit/complete_controller_events_v1.jsonl')
            controllers=[r for r in audit if r['event']=='complete_controller']
            canaries=[r for r in candidate if r.get('row_type')=='canary']
            canary_index={r['session_id']:r for r in canaries}
            assert len(controllers)==len(canaries)==model['sessions']
            assert set(r['session_id'] for r in controllers)==set(samples)
            # Calls are serial inside each archived canary loop. Its final
            # controller event supplies the key even for a failed RPC.
            pending=[];groups={}
            for event in audit:
                if event['event'] in ('generate_raw','compact_verify'):pending.append(event)
                if event['event']=='complete_controller':
                    assert event['session_id'] not in groups
                    groups[event['session_id']]=pending;pending=[]
            assert not pending,'Unassigned calls after final controller'
            for controller in controllers:
                sid=controller['session_id'];calls=groups[sid]
                assert all(r['elapsed_ms']>0 for r in calls)
                if not calls:assert controller['decision']=='NOT_REQUIRED','Unexpected missing qualification calls'
                coverage.append(dict(model=model['model'],repeat=repeat,session_id=sid,
                    controller_ms=controller['controller_ms'],raw_calls=sum(r['event']=='generate_raw' for r in calls),
                    verifier_calls=sum(r['event']=='compact_verify' for r in calls),
                    verifier_failed_calls=sum(r['event']=='compact_verify' and not r.get('certificate_issued',False) for r in calls),
                    exception_calls=sum(r['outcome']=='exception' for r in calls),
                    raw_reference_ms=sum(r['elapsed_ms'] for r in calls if r['event']=='generate_raw'),
                    all_verifier_ms=sum(r['elapsed_ms'] for r in calls if r['event']=='compact_verify'),
                    unaccounted_controller_residual_ms=controller['controller_ms']-sum(r['elapsed_ms'] for r in calls),
                    no_RPC_L0_warmup_fully_in_controller=not calls,
                    certificate_issued=controller['certificate_issued'],raw_finish_reason=controller.get('raw_finish_reason'),
                    canary_failure=canary_index[sid].get('failure_reason',canary_index[sid].get('error_message',''))))
            rpc=[r for r in audit if r['event']=='compact_verify'];references=[r for r in audit if r['event']=='generate_raw']
            rawmean=statistics.fmean(float(r['ttft_ms']) for r in raw.values())
            cm=statistics.fmean(float(r['ttft_ms']) for r in compiled.values())
            full=sum(float(r['controller_ms']) for r in controllers)
            rawwall=read(pair/'raw/completion_v1.json')['checks']['service_wall_with_drain_s']
            cwall=read(pair/'contract/completion_v1.json')['checks']['service_wall_with_drain_s']
            selected=[k for k,r in compiled.items() if r.get('certificate_issued') and r.get('certificate_scope_valid',True) and r.get('effective_level')!='L0']
            legacy_keys=selected if model['key'] in ('qwen','mistral') else list(compiled)
            legacy_residual=sum(float(r.get('unhidden_verifier_ms',0)) for r in canaries)
            legacy_full_rpc=sum(float(r.get('verification_ms',0)) for r in canaries)
            legacy_estimate=(100*(1-(statistics.fmean(float(compiled[k]['ttft_ms']) for k in legacy_keys)+legacy_residual/max(1,len(selected)))/
                                     statistics.fmean(float(raw[k]['ttft_ms']) for k in legacy_keys))) if legacy_keys else None
            all_cost.append(dict(model=model['model'],model_key=model['key'],repeat=repeat,future_pairs=len(raw),
                compiled_future_pairs=len(selected),compiled_fraction=len(selected)/len(raw),
                raw_future_mean_ttft_ms=rawmean,contract_future_mean_ttft_ms=cm,
                controller_count=len(controllers),complete_controller_ms=full,
                raw_reference_calls=len(references),raw_reference_ms=sum(r['elapsed_ms'] for r in references),
                all_verifier_calls=len(rpc),all_verifier_ms=sum(r['elapsed_ms'] for r in rpc),
                failed_verifier_calls=sum(not r.get('certificate_issued',False) for r in rpc),
                exception_calls=sum(r['outcome']=='exception' for r in references+rpc),
                controller_amortized_all_future_ms=full/len(raw),
                full_controller_zero_slack_amortized_ttft_reduction_pct=100*(1-(cm+full/len(raw))/rawmean),
                complete_verification_call_zero_slack_amortized_ttft_reduction_pct=100*(1-(cm+sum(r['elapsed_ms'] for r in rpc)/len(raw))/rawmean),
                raw_service_wall_s=rawwall,contract_service_wall_s=cwall,direct_full_wall_multiplier=rawwall/cwall,
                raw_recorded_non_canary_success_rows=sum(r.get('row_type')!='canary' and r.get('success') is True for r in rawrows),
                contract_future_business_requests=len(compiled),
                historical_policy_slack_ms=model['historical_slack_ms'],slack_subtracted_from_full_cost_ms=0,
                legacy_canary_saved_verification_ms=legacy_full_rpc,legacy_saved_residual_verification_ms=legacy_residual,
                residual_diagnostic_selected_future_denominator=len(legacy_keys),residual_canary_RPC_diagnostic_pct=legacy_estimate,
                claim='New frozen-original-cohort replay; controller amortization is component accounting, direct wall is separate measured service time.'))
            for key,c in compiled.items():
                r=raw[key];sample=samples[key[0]]
                a,metric,_=standard_score(r['dataset'],r['task'],r['output_text'],sample.get('answer',''))
                b,_,_=standard_score(c['dataset'],c['task'],c['output_text'],sample.get('answer',''))
                sanity_raw=original_sanity_score(r['output_text'],sample.get('answer',''),r['dataset'])['score']
                sanity_contract=original_sanity_score(c['output_text'],sample.get('answer',''),c['dataset'])['score']
                if 'task_score' in r:assert abs(r['task_score']-sanity_raw)<1e-6
                if 'task_score' in c:assert abs(c['task_score']-sanity_contract)<1e-6
                quality.append(dict(model=model['model'],repeat=repeat,session_id=key[0],turn_id=key[1],
                    dataset=r['dataset'],task=r['task'],sample_id=r['sample_id'],effective_level=c.get('effective_level',c.get('effective_policy')),
                    compiled_route=key in selected,raw_score=a,contract_score=b,delta=b-a,
                    score_up=b-a>0.03,score_down=b-a< -0.03,raw_positive=a>0,
                    output_text_equal=r['output_text']==c['output_text'],raw_finish_reason=r.get('finish_reason','not_retained_by_archived_client'),
                    contract_finish_reason=c.get('finish_reason','not_retained_by_archived_client'),metric=metric,
                    token_ID_equality='unavailable in archived client transport; do not infer from text',
                    stored_raw_driver_sanity_score=r.get('task_score'),stored_contract_driver_sanity_score=c.get('task_score'),
                    recomputed_original_raw_sanity_score=sanity_raw,recomputed_original_contract_sanity_score=sanity_contract,
                    original_sanity_score_up=sanity_contract-sanity_raw>0.03,original_sanity_score_down=sanity_contract-sanity_raw< -0.03,
                    scoring_boundary='task_score is the unchanged driver sanity proxy when stored; raw_score/contract_score are separately recomputed archived Phase20 benchmark-aligned diagnostics',
                    raw_request_id=r['request_id'],contract_request_id=c['request_id']))
    assert len(quality)==4725 and len(all_cost)==12 and len(coverage)==525
    for name,data in [('per_repeat_cost_v1.csv',all_cost),('controller_coverage_v1.csv',coverage),('quality_pairs_v1.csv',quality)]:
        with (output/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    model_summary=[]
    for model in protocol['models']:
        costs=[x for x in all_cost if x['model']==model['model']];qq=[x for x in quality if x['model']==model['model']]
        def quality_group(rs):
            return dict(pairs=len(rs),text_differences=sum(not x['output_text_equal'] for x in rs),
                score_up=sum(x['score_up'] for x in rs),score_down=sum(x['score_down'] for x in rs),
                mean_raw_score=statistics.fmean(x['raw_score'] for x in rs) if rs else None,
                mean_contract_score=statistics.fmean(x['contract_score'] for x in rs) if rs else None)
        model_summary.append(dict(model=model['model'],repeats=costs,
            full_wall_multiplier_mean=statistics.fmean(x['direct_full_wall_multiplier'] for x in costs),
            full_wall_multiplier_range=[min(x['direct_full_wall_multiplier'] for x in costs),max(x['direct_full_wall_multiplier'] for x in costs)],
            full_controller_zero_slack_reduction_mean_pct=statistics.fmean(x['full_controller_zero_slack_amortized_ttft_reduction_pct'] for x in costs),
            archived_benchmark_aligned_secondary_whole_route=quality_group(qq),
            archived_benchmark_aligned_secondary_compiled=quality_group([x for x in qq if x['compiled_route']]),
            archived_benchmark_aligned_secondary_raw_L0=quality_group([x for x in qq if not x['compiled_route']]),
            original_driver_sanity_proxy=dict(stored_raw_rows=sum(x['stored_raw_driver_sanity_score'] is not None for x in qq),
                stored_contract_rows=sum(x['stored_contract_driver_sanity_score'] is not None for x in qq),
                stored_values_all_recomputed_exactly=True,
                recomputed_raw_mean=statistics.fmean(x['recomputed_original_raw_sanity_score'] for x in qq),
                recomputed_contract_mean=statistics.fmean(x['recomputed_original_contract_sanity_score'] for x in qq),
                score_up=sum(x['original_sanity_score_up'] for x in qq),score_down=sum(x['original_sanity_score_down'] for x in qq)),
            counterexample_sources=sorted({x['session_id'] for x in qq if x['score_down']})))
    report=dict(status='complete',fresh_server_cells=24,future_pairs=len(quality),full_controllers=len(coverage),
        all_controller_and_RPC_durations_actual=True,models=model_summary,cell_walls=inventories,
        old_missing_timestamps_recovered=False,new_same_protocol_replay=True,
        restrictions=['Legacy policy/slack/renderer/scope unchanged; not strict R4 behavior certification.',
                      'No slack is subtracted in either new full-cost measure.',
                      'Amortized TTFT with summed controller is accounting, not the measured request readiness distribution.',
                      'Direct client wall includes original warmup/reference preparation; server startup excluded, final drain included.',
                      'Timed compact_verify calls include their preparation/transport/checking work; they are not pure GPU-kernel or pure HTTP durations.',
                      'New measurements do not fill old discarded timestamps. Per-repeat ranges are descriptive, not independent-source confidence intervals.',
                      'Legacy client does not retain complete prompt/output token IDs; paired text equality is not claimed as token-ID equality.'])
    report['quality_scoring_boundary']='No driver score or generation/admission changed. Original Phase12 sanity proxy and separately frozen Phase20 benchmark-aligned post-hoc diagnostics are retained in distinct columns; Llama client did not store task_score, so its original-proxy values are explicitly recomputed, not recovered.'
    write_json(output/'summary_v1.json',report)
    write_json(output/'input_manifest_v1.json',dict(protocol_sha256=sha(study/'protocol_v1.json'),
        pair_completions=[dict(path=p,sha256=sha(study/p/'pair_completion_v1.json')) for p in state['completed_pairs']]))
    print(json.dumps(dict(cells=24,pairs=len(quality),controllers=len(coverage),models=[dict(model=x['model'],wall=x['full_wall_multiplier_mean'],zero_slack=x['full_controller_zero_slack_reduction_mean_pct']) for x in model_summary])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.study,a.output)
