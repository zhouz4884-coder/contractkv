"""CPU-only historical cost/statistics closure, retaining original estimands.

Historical bootstrap replay uses original seeds and draws. The synchronized
RULER source-cluster analysis is an explicitly post-hoc sensitivity analysis.
"""
from pathlib import Path
from collections import Counter, defaultdict
import csv, gzip, hashlib, json, random, re, statistics, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.summarize_submission_supplement import clusters, verifier_by_session, percentile
from scripts.summarize_tsc_submission_closure import cluster_index, number
OUT=ROOT/'results/tsc_revision_remaining_audit_20261018'
IN=OUT/'inputs'

def rows(path):
    p=Path(path)
    if p.suffix=='.gz':return [json.loads(l) for l in gzip.decompress(p.read_bytes()).splitlines() if l.strip()]
    if p.suffix=='.csv':
        with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
    return json.loads(p.read_text(encoding='utf-8'))

def load(rel):return rows(IN/(rel+'.gz'))
def dump(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=True,allow_nan=False)+'\n',encoding='utf-8')

def fast_stat(index, selected):
    rs,cs,vs,ns,certs=map(sum,zip(*(index[sid] for sid in selected)))
    return 1-(cs/ns+vs/max(certs,1))/(rs/ns)

def ruler():
    roots={'Qwen3-8B':'results/submission_supplement/common_ruler/qwen',
           'Mistral-7B-Instruct-v0.3':'results/submission_supplement/common_ruler/mistral',
           'Llama-3.1-8B-Instruct':'results/submission_supplement/ruler_extended'}
    indexes={};sample_ids=None
    for model,base in roots.items():
        indexes[model]=[]
        for repeat in (1,2,3):
            raw=load(f'{base}/repeat{repeat}/raw-order.jsonl')
            strategy=load(f'{base}/repeat{repeat}/contractkv-full.jsonl')
            r,c,v=clusters(raw),clusters(strategy),verifier_by_session(strategy)
            ids=sorted(set(r)&set(c));assert len(ids)==30
            if sample_ids is None:sample_ids=ids
            assert ids==sample_ids
            index={sid:(sum(float(x['ttft_ms']) for x in r[sid]),sum(float(x['ttft_ms']) for x in c[sid]),
                        v.get(sid,0),len(r[sid]),sum(x.get('certificate_issued') is True for x in c[sid])) for sid in ids}
            assert all(len(r[sid])==len(c[sid])==9 for sid in ids)
            indexes[model].append(index)
    original=rows(ROOT/'results/submission_supplement/common_ruler_cross_model_bootstrap_v0.json')['rows']
    results=[]
    for mi,(model,parts) in enumerate(indexes.items()):
        rng=random.Random(26100+mi);draw=[]
        for _ in range(10000):
            draw.append(statistics.fmean(fast_stat(index,rng.choices(sample_ids,k=30)) for index in rng.choices(parts,k=3)))
        point=statistics.fmean(fast_stat(p,sample_ids) for p in parts)
        lo,hi=percentile(draw,.025),percentile(draw,.975)
        saved=next(r for r in original if r['model']==model)
        for key,val in [('estimate_net_mean_ttft_reduction',point),('bootstrap95_low_net_mean_ttft_reduction',lo),('bootstrap95_high_net_mean_ttft_reduction',hi)]:
            assert abs(saved[key]-val)<1e-12,(model,key,saved[key],val)
        results.append({'model':model,'point_pct':100*point,'historical95_pct':[100*lo,100*hi]})
    rng=random.Random(26333);draw=[]
    for _ in range(10000):
        draw.append(statistics.fmean(statistics.fmean(fast_stat(index,rng.choices(sample_ids,k=30)) for index in rng.choices(parts,k=3)) for parts in indexes.values()))
    point=statistics.fmean(r['point_pct'] for r in results)
    old_ci=[100*percentile(draw,.025),100*percentile(draw,.975)]
    saved=original[-1]
    assert abs(saved['estimate_net_mean_ttft_reduction']*100-point)<1e-10
    assert max(abs(old_ci[i]-saved[k]*100) for i,k in enumerate(['bootstrap95_low_net_mean_ttft_reduction','bootstrap95_high_net_mean_ttft_reduction']))<1e-10
    # One sampled directory of sources is shared across all repeats and models.
    # Models are fixed strata; process draws remain model-specific.
    rng=random.Random(20261018);shared=[]
    for _ in range(10000):
        selected=rng.choices(sample_ids,k=30)
        shared.append(statistics.fmean(statistics.fmean(fast_stat(p,selected) for p in rng.choices(parts,k=3)) for parts in indexes.values()))
    sessions=load('results/submission_supplement/ruler_extended_sessions_v0.jsonl')
    dump('ruler_ci_audit_v1.json',{'original_points_and_intervals_reproduced':True,'models':results,'macro_point_pct':point,
        'historical_macro95_pct':old_ci,'historical_estimand':'Fixed three-model macro, process then session resampling independently within model/repeat; no model resampling.',
        'historical_limit':'The same 30 sessions recur across models/repeats, but original draws did not synchronize those source identities. 90 process-session clusters per model are not 90 unique sources.',
        'posthoc_synchronized_source_process95_pct':[100*percentile(shared,.025),100*percentile(shared,.975)],
        'sensitivity_seed':20261018,'sensitivity_iterations':10000,'sensitivity_unit':'30 common session IDs shared across all process/model draws; fixed models; preserve all nine future turns together',
        'session_records':len(sessions),'session_record_keys':list(sessions[0]),'new_GPU_requests':0,
        'interpretation':'Conditional finite-scope precision, not model-population variation or non-RULER generality. A mean CI need not contain the three component means.'})
    print('RULER original bootstrap reproduced; paired sensitivity',100*percentile(shared,.025),100*percentile(shared,.975),flush=True)

def fig5():
    cells={};summaries={};compact={}
    for repeat in (1,2,3):
        for policy in ('D0-native-apc','D2-template-contractkv'):
            base=f'results/tsc_service/locality_cells/qwen_g25_r{repeat}_{policy}_fp8'
            key=(repeat,policy);cells[key]=load(base+'/raw.jsonl')
            summaries[key]=next(r for r in load(base+'/summary.jsonl') if number(r['slo_ttft_ms'])==1500)
            ts,ss,rs=cluster_index(cells[key])
            compact[key]=(ts,ss,{s:(sum(number(r['ttft_ms']) for r in rr),len(rr),sum(number(r['new_prefill_tokens']) for r in rr),
                *(sum(number(r['ttft_ms'])<=slo for r in rr) for slo in (500,1000,1500,3000))) for s,rr in rs.items()})
    rng=random.Random(27020);draws={s:[] for s in (500,1000,1500,3000)}
    for _ in range(10000):
        goodputs={s:[[],[]] for s in draws}
        for repeat in [rng.choice((1,2,3)) for _ in range(3)]:
            for pi,policy in enumerate(('D0-native-apc','D2-template-contractkv')):
                ts,ss,rs=compact[(repeat,policy)];selected=[]
                for t in [rng.choice(ts) for _ in ts]:
                    selected.extend(rng.choice(ss[t]) for _ in ss[t])
                counts=[sum(rs[s][j] for s in selected) for j in range(3,7)]
                summary=summaries[(repeat,policy)]
                wall=int(summary['completed_requests'])/number(summary['achieved_throughput_rps'])
                for i,slo in enumerate(draws):goodputs[slo][pi].append(counts[i]/wall)
        for slo in draws:draws[slo].append(tuple(statistics.fmean(v) for v in goodputs[slo]))
    saved_rows=rows(ROOT/'results/tsc_service/service_locality_confidence_intervals_v0.csv')
    result=[]
    for slo,draw in draws.items():
        points=[]
        for policy in ('D0-native-apc','D2-template-contractkv'):
            pp=[]
            for repeat in (1,2,3):
                summary=summaries[(repeat,policy)];wall=int(summary['completed_requests'])/number(summary['achieved_throughput_rps'])
                pp.append(sum(number(r['ttft_ms'])<=slo for r in cells[(repeat,policy)])/wall)
            points.append(statistics.fmean(pp))
        delta=points[1]-points[0];ci=[percentile([b-a for a,b in draw],q) for q in (.025,.975)]
        identifiable=percentile([a for a,b in draw],.025)>0
        ratios=[b/a for a,b in draw if a>0]
        ratio_ci=[percentile(ratios,q) for q in (.025,.975)] if identifiable else None
        old=next(r for r in saved_rows if r['model']=='qwen' and int(float(r['slo_ttft_ms']))==slo)
        fields={'raw_slo_goodput_rps':points[0],'contract_slo_goodput_rps':points[1],'slo_goodput_delta_rps':delta,
                'slo_goodput_delta_ci_low':ci[0],'slo_goodput_delta_ci_high':ci[1]}
        if ratio_ci:fields.update(slo_goodput_multiplier_ci_low=ratio_ci[0],slo_goodput_multiplier_ci_high=ratio_ci[1])
        for key,val in fields.items():assert abs(float(old[key])-val)<1e-11,(slo,key,old[key],val)
        result.append({'slo_ms':slo,'raw_rps':points[0],'contract_rps':points[1],'delta_rps':delta,'delta95_rps':ci,'ratio':points[1]/points[0],
                       'ratio95':ratio_ci,'all_compared_values_reproduced':True})
    dump('fig5_ci_audit_v1.json',{'Qwen_existing_headline_CI_recomputed':True,'seed':27020,'iterations':10000,'rows':result,
        'protocol':'Qwen,25 tenants/template,80% calibrated load,three fresh processes; elapsed wall held at each observed repeat/policy value.',
        'resampling':'Paired process index; templates and tenant sessions independently drawn in raw/compiled policies by the historical generator; all turns kept in session.',
        'inference_limit':'Conditional request-compliance variability at this measured point, not an estimated capacity curve or a confidence interval over unobserved arrival rates; templates/session resampling is not synchronized across policies.',
        'source_rows':sum(map(len,cells.values())),'new_GPU_requests':0})
    print('Fig5 historical bootstrap point and CI reproduced',result[0],flush=True)

def costs_and_points():
    cc=rows(ROOT/'results/tsc_revision_evidence_closure_20261017/tableIII_audit/matched_cost_per_repeat_v1.csv')
    lower=[]
    for model in ['qwen','qwen14','mistral','llama']:
        rr=[r for r in cc if r['model']==model]
        reduction=(statistics.fmean(100*(1-(float(r['business_mean_ttft_ms'])+float(r['known_controller_elapsed_ms_lower_bound'])/int(r['future_pairs']))/float(r['raw_mean_ttft_ms'])) for r in rr)
                   if all(r['known_controller_elapsed_ms_lower_bound'] for r in rr) else None)
        lower.append({'model':model,'known_controller_cost_all_future_reduction_upper_bound_pct':reduction,
                      'missing_controller_canaries':sum(int(r['missing_controller_canary_timings']) for r in rr),
                      'meaning':'Upper bound under controller-component amortized mean accounting, not complete live latency.'})
    metrics=[]
    for p in sorted(IN.rglob('*contract_metrics.jsonl.gz')):
        rr=rows(p);verify=[r for r in rr if 'verify' in str(r.get('request_id',''))]
        metrics.append({'file':p.relative_to(ROOT).as_posix(),'rows':len(rr),'verify_observations':len(verify),
                        'prefill_gpu_duration_present':sum(r.get('prefill_gpu_ms') is not None for r in rr),
                        'decode_gpu_duration_present':sum(r.get('decode_gpu_ms') is not None for r in rr),
                        'wall_timestamp_fields':sorted({k for r in rr for k in r if 'timestamp' in k or k.endswith('_time')})})
    logs=[]
    for p in sorted(IN.rglob('*contract_server.log.gz')):
        text=gzip.decompress(p.read_bytes()).decode('utf-8','replace')
        lines=[l for l in text.splitlines() if 'POST /v1/contractkv/verify' in l]
        logs.append({'file':p.relative_to(ROOT).as_posix(),'verify_HTTP_responses':len(lines),'representative_line':re.sub(r'\x1b\[[0-9;]*m','',lines[0]) if lines else None})
    same=rows(ROOT/'results/tsc_closure/real_task_open_loop_summary_v1.json')
    a=next(r for r in same['rows'] if r['policy']=='D0-native-apc' and float(r['slo_ttft_ms'])==500)
    b=next(r for r in same['rows'] if r['policy']=='D2-template-contractkv' and float(r['slo_ttft_ms'])==500)
    locality=rows(ROOT/'results/tsc_service/service_locality_aggregate_v0.csv')
    selected=[r for r in locality if r['model']=='qwen' and r['policy'] in ['D0-native-apc','D2-template-contractkv'] and float(r['load_fraction'])==.8 and int(float(r['tenants_per_template']))==25 and float(r['slo_ttft_ms'])==500]
    dump('operating_points_and_cost_gaps_v1.json',{'original_TableIII_full_cost_closed':False,'known_controller_cost_bounds':lower,
        'additional_original_Llama_metric_files':metrics,'additional_original_Llama_server_logs':logs,
        'missing_RPC_timers_remain':33,'why_not_recoverable_from_these_files':'Metric records retain scheduler wait but no prefill/decode GPU durations, full controller wall, or per-call start/finish timestamps. HTTP lines count calls without elapsed time. Neither can fill the discarded durations.',
        'point_92_90':{'reduction_pct':100*(1-b['mean_ttft_ms']/a['mean_ttft_ms']),'fresh_process_repeats':same['fresh_process_repeats'],
            'raw_mean_ttft_ms':a['mean_ttft_ms'],'contract_mean_ttft_ms':b['mean_ttft_ms'],'raw_e2e_goodput_rps':a['end_to_end_slo_goodput_rps'],'contract_e2e_goodput_rps':b['end_to_end_slo_goodput_rps'],
            'timing_boundary':'TTFT mean is business-request TTFT. Registration wall is charged to end_to_end_slo_goodput_rps, not added into mean_ttft_ms.',
            'source':'results/tsc_closure/real_task_open_loop_summary_v1.json','summary_rows_500ms':[a,b]},
        'point_92_62':{'source':'results/tsc_service/service_locality_aggregate_v0.csv','selected_summary_rows':selected,'fresh_process_repeats':3,
            'protocol':'Authorized service-locality,25 tenants/template,80% calibrated open-arrival load; not same-path five-repeat cohort.'},
        'new_GPU_requests':0})
    print('Cost gaps retained; 92.90/92.62 operating points distinguished',flush=True)

def main():
    manifest=rows(OUT/'retrieval_manifest_v1.json')
    for r in manifest['files']:
        p=ROOT/r['local_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['gzip_sha256']
        data=gzip.decompress(p.read_bytes());assert hashlib.sha256(data).hexdigest()==r['decompressed_sha256']
        if r['mode']=='verbatim_gzip':assert hashlib.sha256(data).hexdigest()==r['remote_sha256']
    costs_and_points();ruler();fig5()
    dump('audit_checks_v1.json',{'status':'PASS','input_files_hashed':len(manifest['files']),'new_GPU_requests':0,
        'full_original_TableIII_costs_closed':False,'historical_statistical_replays':'Qwen Fig5 and three-model RULER numerical values reproduced from recovered inputs',
        'important_new_correction':'92.90% TTFT is a business mean; full registration is charged to goodput wall, not that TTFT statistic.'})

if __name__=='__main__':main()
