"""Reaccount original Table-III requests; never fill missing timings with zero.

The historical reporting denominator is retained in one column and a common
all-future denominator in another. Verifier RPC time is distinct from the full
canary/controller path and directly measured complete service wall.
"""
from pathlib import Path
import csv
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/tsc_revision_evidence_closure_20261017/tableIII_audit'
RAW = OUT.parent/'original_tableIII'


def load(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as f:return list(csv.DictReader(f))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    repeats=[];provenance=[];canary_projection=[]
    for model in ['qwen','mistral','qwen14','llama']:
        for repeat in [1,2,3]:
            if model in ['qwen','mistral']:
                folder=RAW/f'results/submission_repeats/{model}/repeat{repeat}'
                rp,cp=folder/'raw-order.jsonl',folder/'contractkv-full.jsonl'
            elif model=='qwen14':
                folder=RAW/f'results/scale_up/qwen3_14b_tp2_v0/r{repeat}'
                rp,cp=folder/f'r{repeat}-raw.jsonl',folder/f'r{repeat}-contract.jsonl'
            else:
                folder=ROOT/f'results/cross_model/llama_broad_generalization_r3/repeat{repeat}'
                rp,cp=folder/f'r{repeat}-raw.jsonl',folder/f'r{repeat}-contract.jsonl'
            raw,compiled=load(rp),load(cp)
            future_raw=[r for r in raw if r.get('row_type')=='future']
            future=[r for r in compiled if r.get('row_type')=='future']
            key=lambda r:(str(r['session_id']),int(r['turn_id']))
            assert len(future)==len(future_raw) and {key(r) for r in future}=={key(r) for r in future_raw}
            assert all(r.get('success') is True for r in future+future_raw)
            canaries=[r for r in compiled if r.get('row_type')=='canary']
            n=len(future);ncert=sum(r.get('certificate_issued') is True for r in future)
            denominator=ncert if model in ['qwen','mistral'] else n
            raw_mean=statistics.fmean(float(r['ttft_ms']) for r in future_raw)
            business_mean=statistics.fmean(float(r['ttft_ms']) for r in future)
            exposed=sum(float(r.get('unhidden_verifier_ms',0) or 0) for r in canaries)
            timed=[r for r in canaries if float(r.get('verification_ms',0) or 0)>0]
            recorded_cost=sum(float(r.get('verification_ms',0) or 0) for r in canaries)
            raw_incomplete=[r for r in canaries if r.get('success') is False]
            assert all(r.get('error_type')=='VerificationIncomplete' and r.get('error_message')=='raw finish_reason=length' for r in raw_incomplete)
            # compact_verify checks raw finish_reason before initiating an RPC.
            # Incomplete raw references consume generation time, not verifier RPC time.
            if model=='llama':
                calls=sum(len(r.get('level_attempts',[])) for r in canaries)
                missing=calls-len(timed)
            else:
                calls=len(canaries)-len(raw_incomplete);missing=calls-len(timed)
                assert missing==0
            known_controller=[r for r in canaries if r.get('latency_ms') is not None]
            controller_lower=sum(float(r['latency_ms']) for r in known_controller)
            old_reduction=100*(1-(business_mean+exposed/denominator)/raw_mean)
            if model in ['qwen','mistral']:
                reference=next(r for r in csv_rows(ROOT/'results/submission_repeats/submission_repeat_cells_v0.csv') if r['model']==model and int(r['repeat'])==repeat and r['policy']=='contractkv-full')
                expected=float(reference['net_mean_ttft_ms'])
            elif model=='qwen14':
                reference=next(r for r in csv_rows(ROOT/'results/scale_up/qwen3_14b_tp2_v0/repeat_summary_v0.csv') if int(r['repeat'])==repeat)
                expected=float(reference['contract_net_mean_ttft_ms'])
            else:
                reference=next(r for r in csv_rows(ROOT/'results/cross_model/llama_broad_generalization_r3/heldout_scope_repeats_v0.csv') if int(r['repeat'])==repeat and r['scope']=='all')
                expected=business_mean
            assert abs(business_mean+exposed/denominator-expected)<1e-7
            for row in canaries:
                canary_projection.append({k:row.get(k) for k in ['session_id','dataset','task','certificate_issued','success','verification_ms','verify_endpoint_ms','unhidden_verifier_ms','latency_ms','level_attempts','error_type','error_message']}|{'model':model,'repeat':repeat})
            record={'model':model,'repeat':repeat,'future_pairs':n,'certified_future':ncert,
                'canaries':len(canaries),'raw_mean_ttft_ms':raw_mean,'business_mean_ttft_ms':business_mean,
                'historical_cost_denominator':denominator,'historical_denominator_kind':'certified future requests' if model in ['qwen','mistral'] else 'all future requests',
                'reported_slack_s':6 if model=='llama' else 2,
                'recorded_exposed_verifier_ms':exposed,'recorded_verifier_ms':recorded_cost,
                'reported_reduction_pct_reproduced':old_reduction,
                'zero_slack_recorded_RPC_legacy_denominator_pct':100*(1-(business_mean+recorded_cost/denominator)/raw_mean),
                'zero_slack_recorded_RPC_all_future_pct':100*(1-(business_mean+recorded_cost/n)/raw_mean),
                'verifier_RPC_calls':calls,'timed_verifier_RPC_calls':len(timed),'missing_verifier_RPC_timings':missing,
                'verifier_RPC_timer_coverage_complete':missing==0,
                'incomplete_raw_reference_generations':len(raw_incomplete),
                'recorded_controller_canaries':len(known_controller),'missing_controller_canary_timings':len(canaries)-len(known_controller),
                'known_controller_elapsed_ms_lower_bound':controller_lower if known_controller else None,
                'full_controller_cost_identifiable':False,
                'full_pipeline_wall_identifiable':False}
            repeats.append(record)
            provenance.extend({'model':model,'repeat':repeat,'policy':policy,'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'records':len(data)} for policy,p,data in [('raw',rp,raw),('strategy',cp,compiled)])
    summary=[]
    for model in ['qwen','qwen14','mistral','llama']:
        rows=[r for r in repeats if r['model']==model]
        fields=['reported_reduction_pct_reproduced','zero_slack_recorded_RPC_legacy_denominator_pct','zero_slack_recorded_RPC_all_future_pct']
        item={'model':model,**{key:statistics.fmean(r[key] for r in rows) for key in fields},
            'future_pairs':sum(r['future_pairs'] for r in rows),
            'verifier_RPC_calls':sum(r['verifier_RPC_calls'] for r in rows),
            'timed_verifier_RPC_calls':sum(r['timed_verifier_RPC_calls'] for r in rows),
            'missing_verifier_RPC_timings':sum(r['missing_verifier_RPC_timings'] for r in rows),
            'incomplete_raw_reference_generations':sum(r['incomplete_raw_reference_generations'] for r in rows),
            'missing_controller_canary_timings':sum(r['missing_controller_canary_timings'] for r in rows),
            'zero_slack_status':'Exact reaccounting of recorded verifier-RPC component' if model!='llama' else 'Upper bound on reduction: intermediate failed-call timings missing'}
        summary.append(item)
    assert [round(r['reported_reduction_pct_reproduced'],2) for r in summary]==[37.81,44.69,31.72,29.41]
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'matched_cost_per_repeat_v1.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(repeats[0]));w.writeheader();w.writerows(repeats)
    (OUT/'canary_timing_projection_v1.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in canary_projection),encoding='utf-8')
    report={'schema_version':'contractkv.original-tableIII-matched-cost.v1','source_sha256':sha(Path(__file__)),
        'summary':summary,'raw_record_sources':provenance,'new_GPU_requests':0,
        'all_four_original_reported_means_reproduced':True,
        'all_four_full_verification_costs_closed':False,
        'limits':['Verifier-RPC costs are not full canary/controller wall or live readiness TTFT.',
                  'Qwen/Mistral originally divide residual cost by certified future requests; Qwen14/Llama use all future requests.',
                  'Incomplete raw references are rejected before verifier invocation; their lost generation/controller times are not silently treated as zero.',
                  'Llama discards intermediate rejected-attempt timings and retains the final successful call only, or zero after complete rejection.',
                  'The Llama zero-slack numbers are upper bounds on improvement, not complete-cost performance results.',
                  'Three-process mean values are not source-level confidence intervals.']}
    (OUT/'matched_cost_summary_v1.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'four_original_means_reproduced':True,'summary':summary}))


if __name__=='__main__':main()
