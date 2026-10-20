"""Render separately scoped accounting evidence; never invent historical costs."""
from pathlib import Path
import csv,json,statistics
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'evidence'


def table(caption,label,cols,heading,body,wide=False):
    env='table*' if wide else 'table'
    return (f'\\begin{{{env}}}[!htb]\n\\centering\\small\n\\caption{{{caption}}}\n\\label{{{label}}}\n'
        f'\\begin{{tabular}}{{@{{}}{cols}@{{}}}}\n\\toprule\n'+heading+r'\\'+'\n\\midrule\n'+
        '\n'.join(' & '.join(map(str,r))+r'\\' for r in body)+f'\n\\bottomrule\n\\end{{tabular}}\n\\end{{{env}}}\n')


def main():
    structural=json.loads((E/'closure_tableI_crosswalk_v1.json').read_text())
    cost=json.loads((E/'closure_tableIII_cost_v1.json').read_text())
    binding=json.loads((E/'closure_binding_boundary_v1.json').read_text())
    with (E/'closure_tableIII_repeats_v1.csv').open(encoding='utf-8',newline='') as f:repeats=list(csv.DictReader(f))
    labels={'Qwen3-8B':'Qwen','Mistral-7B-Instruct-v0.3':'Mistral','Llama-3.1-8B-Instruct':'Llama'}
    body=[]
    for model in labels:
        for family in ['RULER','HotpotQA','NarrativeQA','Qasper','RepoBench']:
            r=next(r for r in structural['rows'] if r['cohort']=='bounded_five_family_controls' and r['study']=='single-session' and r['model']==model and r['family']==family)
            assert r['sources']==10 and r['future_requests']==270
            body.append([labels[model],family,f"{r['stable_body_fraction_pct']:.3f}",f"{r['native_total_hit_fraction_pct']:.3f}",f"{r['stable_body_recovery_pct']:.3f}"])
    five=table('Bounded five-family raw controls, separate from the faithful cohort: ten sources and 270 future requests over three repetitions per model/family. Token-weighted percentages.',
        'tab:s-five-family-structure','llrrr',r'Model & Family & Stable/all & Hits/all & Recovered',body)
    dev=[]
    for cohort,label in [('same_four_development_sources_word_cap','Word-cap packing'),('same_four_development_sources_faithful','Structure-preserving')]:
        r=next(r for r in structural['rows'] if r['cohort']==cohort and r['family']=='ALL')
        assert r['sources']==4 and r['future_requests']==360
        dev.append([label,f"{r['stable_body_fraction_pct']:.3f}",f"{r['native_total_hit_fraction_pct']:.3f}",f"{r['stable_body_recovery_pct']:.3f}"])
    paired=table('Same four development sources, Qwen, 360 future requests/input condition, identical 16K window and declared service protocol. Percentages use the same definitions as the five-family table. This comparison changes input construction; it is not a comparison between the original motivation aggregates and a new held-out population.',
        'tab:s-structure-paired','lrrr',r'Input & Stable/all & Hits/all & Stable recovered',dev)
    models={'qwen':'Qwen3-8B','qwen14':'Qwen3-14B TP2','mistral':'Mistral-7B','llama':'Llama-3.1-8B'}
    cb=[]
    for r in cost['summary']:
        model=r['model'];rr=[x for x in repeats if x['model']==model]
        for key in ['reported_reduction_pct_reproduced','zero_slack_recorded_RPC_legacy_denominator_pct','zero_slack_recorded_RPC_all_future_pct']:
            assert abs(statistics.fmean(float(x[key]) for x in rr)-r[key])<1e-8
        prefix=r'$\leq$' if model=='llama' else ''
        cb.append([models[model],f"{r['reported_reduction_pct_reproduced']:.2f}",
            prefix+f"{r['zero_slack_recorded_RPC_legacy_denominator_pct']:.2f}",prefix+f"{r['zero_slack_recorded_RPC_all_future_pct']:.2f}"])
    cost_table=table('Matched-request deployment accounting: mean-TTFT reductions (\\%) over three processes. Recorded reproduces residual-slack accounting; zero slack charges recorded RPCs. Llama values bound savings above because 33 durations are missing. These are not complete controller wall or measured p99.',
        'tab:s-matched-original-cost','lrrr',r'Configuration & Recorded & Zero/legacy & Zero/all',cb)
    assert binding['case_count']==19 and binding['binding_error_cases']==17
    bindings=table('CPU checks of the actual deployment-client issue/check function bodies extracted from their source. Binding errors deny compiled selection and retain raw routing; these checks do not implement a public authentication proxy or measure GPU publication. The tenant-label acceptance is expected under the domain wildcard and requires application-level user authorization.',
        'tab:s-client-binding','P{1.9in}rr',r'Condition & Cases & \shortstack{Compiled\\admissible}',[
        ['Matching domain binding',1,1],['Changed bound identity/scope/settings',14,0],
        ['Missing binding, bad tag, expiry',3,0],['Different tenant label; domain wildcard',1,1]])
    text=r'''\section{Structural Measurement and Cost Granularity}
\label{sec:s-closure}
The main structural table concerns its six-source faithful cohort. Table~\ref{tab:s-five-family-structure} adds separately frozen five-family raw controls; Table~\ref{tab:s-structure-paired} holds four development sources fixed while changing input construction. Stable/all is stable body divided by all input tokens, Hits/all is total native hits divided by all input tokens, and Recovered is native hits on stable body divided by stable body tokens. Different cohorts and token attribution conventions are not treated as a before/after update of one aggregate. The token ledgers preserve actual prompt-ID alignment flags and separate source-macro from pooled token ratios.

'''+five+'\n'+paired+r'''
\subsection{Matched Deployment Cost Components}
For a trace with business mean $\bar T$, recorded verification durations $c_j$, slack $s$ and normalization count $N$, residual accounting is $\bar T+\sum_j\max(c_j-s,0)/N$. Setting $s=0$ on the same recorded requests gives $\bar T+\sum_jc_j/N$. Table~\ref{tab:s-matched-original-cost} preserves the original normalization and also gives an all-future denominator; these are component means, not new service-wall measurements. Qwen8B/Mistral originally normalize RPC cost by certified future requests; Qwen14B/Llama use all future requests. There are 1,350 future pairs/configuration, except Qwen14B with 675.

Qwen8B, Mistral and Qwen14B retain 147/147, 126/126 and 72/72 verifier-RPC timers, respectively. Three, 24 and three raw-reference generations instead reach their output limit before a verifier RPC is invoked. Their generation/controller elapsed times were not retained on the exception path. Llama records 75/108 RPC durations: rejected intermediate attempts retain decisions but lose timings. Full rejection also overwrites the cost with zero. Those missing costs are not imputed; the Llama savings are bounded above by the recorded-cost result. Missing preprocessing and raw-reference time prevent reconstructing complete historical controller cost. The independent registration-cost supplement and the primary directly measured service wall remain separate evidence.

'''+cost_table+r'''
\subsection{Where Binding Checks Execute}
The source call chain places HMAC binding validation in the trusted deployment client before compiled/raw route selection, rather than in a separately deployed network gateway. Table~\ref{tab:s-client-binding} tests that function boundary. The domain-level certificate uses a wildcard tenant field; the application must authenticate users, enforce membership and mediate access to the engine. The separate manifest-helper cases in Table~\ref{tab:s-manifest} test declaration consistency, not semantic confidentiality. No new GPU requests are used in these CPU audits.

'''+bindings
    (ROOT/'sections/supplement_evidence_closure.tex').write_text(text,encoding='utf-8')
    print(json.dumps({'generated_tables':4,'main_tableI_values_changed':False,'cost_timers_incomplete_preserved':33,'binding_cases':19}))


if __name__=='__main__':main()
