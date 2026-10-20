"""Recompute manuscript tables from frozen records; no tokenizer/model execution."""
from pathlib import Path
from collections import defaultdict,Counter
from itertools import groupby
import csv,json,hashlib,statistics,math

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'evidence'
def rows(name):
    with (E/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def only(values):
    assert len(values)==1,len(values)
    return values[0]
def write(name,text):(ROOT/name).write_bytes((text.rstrip()+'\n').encode())
def latex_table(caption,label,columns,head,body,wide=False,notes=''):
    env='table*' if wide else 'table'
    return ('\\begin{'+env+'}[t]\n\\centering\\small\n\\caption{'+caption+'}\n\\label{'+label+'}\n'
        '\\begin{tabular}{@{}'+columns+'@{}}\n\\toprule\n'+head+'\\\\\n\\midrule\n'+'\n'.join(' & '.join(map(str,r))+r'\\' for r in body)+
        '\n\\bottomrule\n\\end{tabular}\n'+('\\par\\vspace{2pt}\\footnotesize '+notes+'\n' if notes else '')+'\\end{'+env+'}\n')

def main():
    displacement=rows('segment_token_displacement_v1.csv');assert len(displacement)==4695
    for r in displacement:
        assert int(r['candidate_start_token'])-int(r['raw_start_token'])==int(r['displacement_tokens'])
        assert r['render_token_identity_verified']=='True'
    cases=defaultdict(list)
    for r in displacement:cases[(r['model'],r['cohort'],r['family'],r['session_id'])].append(r)
    assert len(cases)==240
    patterns=defaultdict(Counter)
    for key,v in cases.items():
        order=sorted(v,key=lambda r:int(r['raw_order_index']))
        assert [int(r['raw_order_index']) for r in order]==list(range(len(order)))
        pattern=tuple((kind,len(list(items))) for kind,items in groupby(r['segment_type'] for r in order))
        patterns[key[2]][pattern]+=1
    families=['RULER','HotpotQA','NarrativeQA','Qasper','RepoBench']
    statistics_rows=[]
    for family in families+['ALL']:
        rr=displacement if family=='ALL' else [r for r in displacement if r['family']==family]
        delta=[int(r['displacement_tokens']) for r in rr];absolute=sorted(map(abs,delta))
        statistics_rows.append({'family':family,'segments':len(rr),
          'ordinal_moved':sum(r['raw_order_index']!=r['candidate_order_index'] for r in rr),
          'token_moved':sum(d!=0 for d in delta),'mean_abs_tokens':statistics.fmean(absolute),
          'p95_abs_tokens':absolute[math.ceil(.95*len(absolute))-1],
          'signed_min':min(delta),'signed_max':max(delta)})
    source_fields=defaultdict(Counter)
    for name in ('free_generation_sessions_v1.jsonl','hotpot_heldout_sessions_v1.jsonl'):
        for line in (E/name).read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            sample=json.loads(line)
            source_fields[sample['revision_family']][tuple(s['type'] for s in sample['segments'])]+=1
    for family,pp in source_fields.items():assert len(pp)==1,(family,pp)
    short={'SYS_PROMPT':'SYS','TOOL_OBS':'OBS','RAG_CHUNK':'RAG','SYNTHETIC_CONTEXT':'SYN','REPO_CONTEXT':'REPO','CODE_PREFIX':'CODE','USER_QUERY':'QUERY'}
    def pretty(seq):return r'$\rightarrow$'.join(short[t]+(f'$^{{{n}}}$' if n>1 else '') for t,n in seq)
    raw=[]
    for family in families:
        seq=only(list(source_fields[family]))
        rendered=list(patterns[family])
        if len(rendered)==1:after=pretty(rendered[0])
        else:
            assert family=='RepoBench'
            after=r'SYS$\rightarrow$OBS$\rightarrow$REPO$^{16}$' +r'$\rightarrow$CODE$^k\rightarrow$QUERY'
        raw.append([family,pretty([(x,1) for x in seq]),after])
    orders=latex_table('Frozen five-family input order before CALC. Prepared fields come from the archived session inputs; serving order is reconstructed from every recorded raw-order index. Repeated superscripts denote contiguous compiler units, not extra documents.',
        'tab:s-raw-orders','lP{5.1cm}P{8.1cm}','Family & Prepared task fields & Rendered serving segments',raw,True,
        r'SYS, OBS and QUERY denote SYS\_PROMPT, TOOL\_OBS and USER\_QUERY. RAG, SYN, REPO and CODE denote RAG\_CHUNK, SYNTHETIC\_CONTEXT, REPO\_CONTEXT and CODE\_PREFIX. For RepoBench, $k\in\{1,6,16\}$; the runner adds a SYS segment even when the prepared task has no system body. Outer chat-control tokens are outside this segment-order view. The metadata-only OBS is a controlled runner field, not a claim about production prevalence.')
    body=[[r['family'],f"{r['segments']:,}",f"{100*r['ordinal_moved']/r['segments']:.1f}",f"{100*r['token_moved']/r['segments']:.1f}",f"{r['mean_abs_tokens']:.2f}",r['p95_abs_tokens'],f"[{r['signed_min']}, {r['signed_max']}]"] for r in statistics_rows]
    positions=latex_table('Input displacement from 4,695 archived segment observations in 240 model/session inputs (three tokenizers over 80 session inputs). Candidate levels follow the frozen per-model policy, including L0, and are not conditioned on verifier success. These nested observations are not 4,695 independent task sources. Percentages and means are segment-weighted.',
      'tab:s-displacement','lrrrrrl','Family & Segments & Ordinal moved (\\%) & Token moved (\\%) & Mean $|d_i|$ & P95 $|d_i|$ & Signed range',body,True)
    ruler=[]
    q=rows('quality_summary_v1.csv')
    for model,label in [('Qwen3-8B','Qwen'),('Mistral-7B-Instruct-v0.3','Mistral'),('Llama-3.1-8B-Instruct','Llama')]:
        cold=only([r for r in q if r['model']==model and r['family']=='RULER' and r['policy']=='risk-tail' and r['study']=='single-session'])
        fan=only([r for r in q if r['model']==model and r['family']=='RULER' and r['policy']=='risk-tail' and r['study']=='template-fanout'])
        c,n=int(cold['compiled_pairs']),int(cold['pairs']);f,m=int(fan['compiled_pairs']),int(fan['pairs'])
        assert (c,n,f,m)==(210,270,516,540)
        ruler.append({'model':label,'cold_compiled':c,'cold_pairs':n,'fanout_compiled':f,'fanout_pairs':m,'compiled':c+f,'pairs':n+m,'coverage_pct':100*(c+f)/(n+m)})
    d0=only([r for r in rows('real_task_open_loop_summary_v1.csv') if r['policy']=='D0-native-apc' and float(r['slo_ttft_ms'])==500])
    native={'policy':'D0-native-apc','goodput':float(d0['end_to_end_slo_goodput_rps']),'min':float(d0['end_to_end_slo_goodput_rps_repeat_min']),'max':float(d0['end_to_end_slo_goodput_rps_repeat_max']),'repeats':int(d0['fresh_process_repeats'])}
    gates=rows('heldout_gate_v1.csv');assert len(gates)==4
    gatebody=[[r['stable_prefix_tokens'],r['future_reuses'],f"{int(r['tool_slack_ms'])/1000:g}",'CKV' if r['gate_accepted']=='True' else 'Raw',f"{float(r['observed_net_benefit_ms'])/1000:.2f}"] for r in gates]
    gatetable=latex_table('Four sealed operating points under the development-frozen benefit gate. Net benefit is per certificate; rejected points serve raw. Candidate diagnostics were also run for rejected points, so this table does not measure avoided online verifier calls.',
      'tab:gate','rrrrr','Prefix & Uses & Slack (s) & Route & Net benefit (s)',gatebody)
    source=json.loads((ROOT/'figures/figure_data_v7.json').read_text())
    density=source['density'];densityrows=[]
    actual_density=rows('multi_tenant_aggregate_v0.csv');density_cells=rows('multi_tenant_cell_summary_v0.csv')
    for r in density:
        a=only([x for x in actual_density if x['kind']=='density' and x['service_class']=='ALL' and int(x['tenants'])==r['tenants'] and x['policy']==r['policy']])
        cc=[x for x in density_cells if x['kind']=='density' and x['service_class']=='ALL' and int(x['tenants'])==r['tenants'] and x['policy']==r['policy']]
        assert len(cc)==3
        for key,agg,cell in [('tiered_SLO_goodput','mean_slo_compliant_goodput_rps','slo_compliant_goodput_rps'),('peak_used_blocks','mean_peak_used_gpu_blocks','peak_used_gpu_blocks'),('minimum_free_blocks','mean_minimum_free_gpu_blocks','minimum_free_gpu_blocks')]:
            assert abs(float(a[agg])-r[key])<1e-8 and abs(statistics.fmean(float(c[cell]) for c in cc)-r[key])<1e-8
    for n in [10,20,30,40,60,80]:
        rawd=only([r for r in density if r['tenants']==n and r['policy']=='D0-native-apc']);ckv=only([r for r in density if r['tenants']==n and r['policy']=='D2-full-contractkv'])
        densityrows.append([n,f"{rawd['tiered_SLO_goodput']:.3f}",f"{ckv['tiered_SLO_goodput']:.3f}",f"{rawd['peak_used_blocks']:.2f}",f"{ckv['peak_used_blocks']:.2f}"])
    densitytable=latex_table('Deployment-template density replay from 10 to 80 registered identities, three fresh processes per policy/point. The class-specific SLOs are 750/1,500/3,000 ms; the pool has 2,386 blocks. Block columns average process peaks. Client concurrency is four and server max-num-seqs is eight. Identities are not simultaneous GPU requests.',
      'tab:s-density','rrrrr','IDs & Raw req/s & CKV req/s & Raw blocks & CKV blocks',densityrows)
    legacy=[]
    agg=rows('submission_repeat_aggregate_v0.csv')
    for key,label in [('qwen','Qwen3-8B'),('mistral','Mistral-7B')]:
        r=only([r for r in agg if r['model']==key]);legacy.append({'model':label,'ttft_reduction':100*float(r['mean_net_mean_ttft_reduction']),'prefill_reduction':100*float(r['mean_new_prefill_reduction']),'slack_s':2,'execution_SLO_multiplier':1+float(r['mean_slo_goodput_gain'])})
    r=only(rows('aggregate_summary_v0.csv'));legacy.append({'model':'Qwen3-14B TP=2','ttft_reduction':100*float(r['net_mean_ttft_reduction_vs_raw']),'prefill_reduction':100*float(r['new_prefill_reduction_vs_raw']),'slack_s':2,'execution_SLO_multiplier':1+float(r['slo_goodput_gain_vs_raw'])})
    r=only([r for r in rows('heldout_scope_aggregate_v0.csv') if r['scope']=='all']);legacy.append({'model':'Llama-3.1-8B','ttft_reduction':100*float(r['net_mean_ttft_reduction']),'prefill_reduction':100*float(r['new_prefill_reduction']),'slack_s':6,'execution_SLO_multiplier':1+float(r['slo_goodput_gain'])})
    order={'Qwen3-8B':0,'Qwen3-14B TP=2':1,'Mistral-7B':2,'Llama-3.1-8B':3};legacy.sort(key=lambda r:order[r['model']])
    costs=rows('fresh_cost_decomposition_v1.csv')
    for r in legacy:
        key={'Qwen3-8B':'qwen','Qwen3-14B TP=2':'qwen14','Mistral-7B':'mistral','Llama-3.1-8B':'llama'}[r['model']]
        selected=[c for c in costs if c['model']==key and c['family']=='ALL' and c['request_class']=='ALL' and float(c['slack_ms'])==0 and ((key=='qwen14' and c['experiment']=='qwen14-full-cost' and c['budget_override']=='96') or (key!='qwen14' and c['experiment']=='free-generation' and c['budget_override']=='0'))]
        assert len(selected)==3
        for c in selected:
            charged=float(c['observed_mean_ttft_ms'])+float(c['registration_total_ms'])/int(c['future_requests'])
            assert abs(charged-float(c['net_mean_ttft_ms']))<1e-7
            assert abs(1-charged/float(c['raw_mean_ttft_ms'])-float(c['net_mean_ttft_reduction']))<1e-9
        r['zero_slack_cost_supplement_pct']=100*statistics.fmean(float(c['net_mean_ttft_reduction']) for c in selected)
    broad=latex_table('Deployment-qualified breadth over five families, three repetitions/configuration. TTFT uses recorded residual-RPC accounting after the stated slack, not complete service wall; the supplemental cost audit identifies missing attempt timers. Prefill uses the same cohort.',
      'tab:deployment-width','lrrr',r'Configuration & \shortstack{Recorded TTFT\\reduction} & Prefill & Slack (s)',
      [[r['model'],f"{r['ttft_reduction']:.2f}\\%",f"{r['prefill_reduction']:.2f}\\%",r['slack_s']] for r in legacy])
    write('sections/table_deployment_width.tex',broad);write('sections/table_frozen_gate.tex',gatetable)
    write('sections/supplement_restored_tables.tex',r'''\section{Input Structure and Displacement}
\label{sec:s-input}
We use the frozen input manifests and their measured tokenizer-position ledger to quantify how prompt compilation changes the input. Table~\ref{tab:s-raw-orders} distinguishes prepared dataset fields from the controlled serving sequence, including the metadata observation introduced by the runner. It covers all five workload families and every observed serving-order pattern.

Let $a_i$ and $b_i$ be the zero-based token positions of segment $i$'s rendered header marker in raw and candidate chat prompts. We report $d_i=b_i-a_i$, the fraction with changed ordinal index, the fraction with $d_i\ne0$, mean $|d_i|$, nearest-rank P95 $|d_i|$, and the signed range. Header markers are included; these are not body-only token offsets. Every archived record reports that direct tokenization and tokenization of the rendered chat text agree. The present CPU aggregation checks its arithmetic and completeness, without rerunning model or tokenizer inference. Table~\ref{tab:s-displacement} does not identify an attention or RoPE causal mechanism.

'''+orders+'\n'+positions+r'''
\section{Complementary Serving Controls}
\label{sec:s-serving}
'''+densitytable+'\n'+latex_table('Separate bounded-input RULER audit. Cold and fan-out traces are pooled only within this declared protocol, not with the faithful 16K HotpotQA/RepoBench cohort.','tab:s-ruler','lrrr','Model & Cold C/N & Fan-out C/N & Total C/N',[[r['model'],f"{r['cold_compiled']}/{r['cold_pairs']}",f"{r['fanout_compiled']}/{r['fanout_pairs']}",f"{r['compiled']}/{r['pairs']}"] for r in ruler])+'\n')
    clock_table=latex_table('Complementary execution-clock SLO statistics for the four-configuration deployment cohort. These ratios use archived business-batch execution wall, not complete qualification-charged service wall. Deadlines are configuration-specific and matched within each raw/ContractKV pair. Net TTFT in the main table separately adds residual verification exposure.',
      'tab:s-execution-slo','lrr','Configuration & SLO multiplier & Slack (s)',
      [[r['model'],f"{r['execution_SLO_multiplier']:.3f}$\\times$",r['slack_s']] for r in legacy])
    mechanisms=latex_table('Comparison of published mechanisms and their role in this study. The table compares responsibilities and evaluated evidence, not unreported security capabilities of the other systems.',
      'tab:s-mechanisms','lP{6.5cm}P{7.3cm}','System & Published mechanism / reuse unit & Relationship to the present evaluation',[
      [r'SGLang~\cite{sglang2024}','RadixAttention organizes exact-prefix KV reuse for structured LLM programs.','A native reuse substrate; the separate frozen-layout transfer test does not implement ContractKV certification or PSTP.'],
      [r'Prompt Cache~\cite{promptcache2024}','A schema defines reusable prompt modules and their positional treatment.','Modular reuse design; discussed as a distinct way to expose reusable attention state.'],
      [r'CacheBlend~\cite{cacheblend2025}','Cached passages are fused with selective recomputation of token KV.','Matched-native paired task outcomes are measured; cross-stack speeds are not ranked.'],
      [r'EPIC~\cite{epic2025}','Position-independent caching with LegoLink to address document-boundary attention effects.','A different execution mechanism; no direct EPIC performance reproduction is claimed.'],
      [r'Parrot~\cite{parrot2024}','Semantic Variables expose application input/output dataflow to the serving system.','Application dependency information motivates service-aware control; its optimization target is application execution.'],
      ['ContractKV','A dependency-valid stable-prefix layout is bound to behavioral qualification, authorization/lifecycle identity and a transactional publication boundary.','Same-engine admission/publication controls, template amortization, free-running task pairs and physical reuse are measured separately.']],True)
    matched=[r for r in rows('matched_baseline_quality_thresholds_v1.csv') if r['family']=='ALL' and float(r['threshold'])==.03]
    labels={'cacheblend':'CacheBlend adaptation','contractkv':'ContractKV','manual_oracle':'Manual layout control','sglang_certified':'SGLang frozen layout'}
    qualtable=latex_table('Matched-native paired task-score distributions (2,250 pairs/method). Increases and decreases use the declared 0.03 threshold. Each row retains its own baseline and prompt/runtime configuration; these means are not a common cross-stack accuracy or speed comparison.',
      'tab:s-native-quality','lP{3.1cm}rrrr','Method & Matched reference & Reference mean & Method mean & Increases & Decreases',
      [[labels[r['method']],r['matched_baseline'].replace('_',r'\_'),f"{float(r['baseline_mean_score']):.6f}",f"{float(r['candidate_mean_score']):.6f}",r['material_improvements'],r['material_regressions']] for r in matched],True)
    write('sections/supplement_service_breadth.tex',r'''\section{Reuse Mechanisms and Serving Breadth}
\label{sec:s-mechanisms}
'''+clock_table+'\n'+mechanisms+'\n'+r'\input{sections/table_frozen_gate}'+'\n'+qualtable+r'''
\paragraph{CacheBlend interpretation.} The controlled LMCache integration uses 32-token chunks and a separator-matched reference, while ContractKV uses raw order on its own runtime. The paired 0.03 statistic and these configurations differ from CacheBlend's published aggregate-quality evaluation. The adapter's positive mean-score change coexists with individual decreases; this is a controlled quality comparison, not a reproduction of the authors' performance configuration or a causal cross-stack risk ratio.
''')
    record={'segment_observations':len(displacement),'model_session_inputs':len(cases),'displacement_statistics':statistics_rows,
      'raw_order_patterns':{f:[{'segments':list(pattern),'model_session_inputs':count} for pattern,count in pp.items()] for f,pp in patterns.items()},
      'ruler_audit':ruler,'native_d0':native,'deployment_width':legacy,'density':density,'frozen_gate':gates,
      'source_hashes':[{'path':p.name,'sha256':sha(p)} for p in sorted(E.iterdir())
                       if p.is_file() and p.name not in {'restored_evidence.json','revision_audit_evidence.json'}],
      'new_GPU_measurements':0,'tokenizer_rerun':False,
      'execution_SLO_note':'Archived goodput factors use business execution wall; they are not full-wall qualification-charged throughput.',
      'gate_note':'Rejected operating points also have diagnostic PASS/COMMITTED results; no avoided-call claim.'}
    write('evidence/restored_evidence.json',json.dumps(record,indent=2))
    print(json.dumps({'displacement_segments':len(displacement),'model_session_inputs':len(cases),'families':len(families),'restored_tables':9,'D0_goodput':native['goodput']}))

if __name__=='__main__':main()
