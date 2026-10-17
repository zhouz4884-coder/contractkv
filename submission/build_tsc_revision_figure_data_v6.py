"""Build auditable plotting inputs from the existing measured result ledgers."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {}


def source(name):
    p = ROOT/name
    SOURCES[name] = {'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                     'bytes':p.stat().st_size}
    return p


def rows(name):
    with source(name).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))


def obj(name):
    return json.loads(source(name).read_text(encoding='utf-8'))


def only(values):
    assert len(values)==1, len(values)
    return values[0]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    primary='results/tsc_revision_r4/input_fidelity_validation_v1/analysis/'
    models=['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct']
    short=['Qwen3-8B','Mistral-7B','Llama-3.1-8B']
    perf=rows(primary+'performance_comparison_v1.csv')
    perf_cells=rows(primary+'performance_by_cell_v1.csv')
    phys=obj(primary+'physical_prefix_accounting_v1.json')['cells']
    quality=rows(primary+'quality_pairs_v1.csv')
    strict=[]
    for model,label in zip(models,short):
        pr=only([x for x in perf if x['model']==model and x['policy']=='risk-tail'])
        q=[x for x in quality if x['model']==model and x['policy']=='risk-tail']
        c=[x for x in q if x['effective_level']!='L0']
        repeats=[]
        for repeat in (1,2,3):
            r=only([x for x in perf_cells if x['model']==model and x['policy']=='raw-order' and int(x['repeat'])==repeat])
            k=only([x for x in perf_cells if x['model']==model and x['policy']=='risk-tail' and int(x['repeat'])==repeat])
            repeats.append(float(r['wall_s'])/float(k['wall_s']))
        def counts(policy,field):
            return [x[field] for x in phys if x['model']==model and x['policy']==policy]
        raw=counts('raw-order','actual_new_business_prefill_tokens')
        business=counts('risk-tail','actual_new_business_prefill_tokens')
        verify=counts('risk-tail','actual_qualification_new_prefill_including_witness_tokens')
        assert len(raw)==len(business)==len(verify)==3
        assert len(set(raw))==len(set(business))==len(set(verify))==1
        assert len(q)==1620 and int(pr['pairs'])==len(q)
        assert all(int(x['first_diverging_token'])<0 for x in c)
        strict.append({'model':model,'label':label,'wall_multiplier':float(pr['full_wall_goodput_multiplier']),
            'repeat_wall_multipliers':repeats,'repeat_min':min(repeats),'repeat_max':max(repeats),
            'business_per_repeat':600,'future_pairs':len(q),'compiled_future_pairs':len(c),
            'compiled_future_pct':100*len(c)/len(q),'raw_L0_future_pairs':len(q)-len(c),
            'raw_positive_compiled_future_pairs':sum(float(x['raw_score'])>0 for x in c),
            'raw_business_prefill_per_repeat':raw[0],'CKV_business_prefill_per_repeat':business[0],
            'qualification_prefill_per_repeat':verify[0],
            'raw_ready_p99_ms':float(pr['raw_ready_p99_ms']),
            'CKV_ready_p99_ms':float(pr['policy_ready_p99_ms']),
            'p99_reduction_CI95_low':float(pr['p99_reduction_cluster_repeat_ci95_low']),
            'p99_reduction_CI95_high':float(pr['p99_reduction_cluster_repeat_ci95_high']),
            'all_future_material_drops':sum(float(x['quality_drop'])>.03 for x in q)})
    assert [x['compiled_future_pairs'] for x in strict]==[684,342,270]
    assert [x['raw_positive_compiled_future_pairs'] for x in strict]==[684,258,90]
    audits=[]
    for directory,label in [('validation_closed_v1','Earlier bounded-input audit'),
                            ('input_fidelity_validation_v1','Faithful held-out validation')]:
        q=rows('results/tsc_revision_r4/'+directory+'/analysis/quality_pairs_v1.csv')
        c=[x for x in q if x['policy']=='risk-tail' and x['effective_level']!='L0']
        audits.append({'label':label,'compiled_future_pairs':len(c),
            'ID_divergences':sum(int(x['first_diverging_token'])>=0 for x in c),
            'raw_positive_pairs':sum(float(x['raw_score'])>0 for x in c),
            'distinct_sources':len({x['source_group'] for x in q}),
            'distinct_compiled_sources':len({x['source_group'] for x in c}),
            'studies':sorted({x['study'] for x in q}),
            'all_route_material_drops':sum(float(x['quality_drop'])>.03 for x in q)})
    assert [x['compiled_future_pairs'] for x in audits]==[2442,1296]
    assert [x['ID_divergences'] for x in audits]==[0,0]
    serving=rows('results/tsc_closure/real_task_open_loop_summary_v1.csv')
    d1d2=[]
    for policy in ('D1-frozen-safe','D2-template-contractkv'):
        r=only([x for x in serving if x['policy']==policy and float(x['slo_ttft_ms'])==500])
        d1d2.append({'policy':policy,'goodput':float(r['end_to_end_slo_goodput_rps']),
            'min':float(r['end_to_end_slo_goodput_rps_repeat_min']),
            'max':float(r['end_to_end_slo_goodput_rps_repeat_max']),
            'repeats':int(r['fresh_process_repeats']),
            'registration_wall_s':float(r['registration_wall_s']),
            'verifier_calls':float(r['actual_verifier_endpoint_calls'])})
    rejection=[]
    for name,label in [('guard_probe_qwen_v1.jsonl','Qwen3-8B'),
                       ('guard_probe_qwen14_actual_v2.jsonl','Qwen3-14B, TP=2')]:
        rr=[json.loads(s) for s in source('results/tsc_revision_r1/'+name).open(encoding='utf-8')]
        bad=[x for x in rr if x['case_type']=='order_sensitive_instruction']
        assert len(bad)==10 and all(x['dependency_order_valid'] for x in bad)
        assert all(x['raw_score']==1 and x['layout_only_score']==0 for x in bad)
        assert all(not x['certificate_issued'] and x['committed_tokens']==0 and x['zero_publication_on_reject'] for x in bad)
        rejection.append({'model':label,'bad_layouts':len(bad),'rejected':sum(not x['certificate_issued'] for x in bad),
                          'published_rejected_tokens':sum(x['committed_tokens'] for x in bad)})
    gran=rows('results/tsc_service/certificate_granularity_ablation_v0.csv')
    granularity=[]
    for policy in ('D2-session-contractkv','D2-template-contractkv'):
        r=only([x for x in gran if x['policy']==policy])
        granularity.append({'policy':policy,'calls_per_trace':float(r['mean_actual_verifier_endpoint_calls']),
            'unhidden_ms_per_future_request':float(r['mean_unhidden_verification_ms_per_future_request']),
            'repeats':int(r['fresh_process_repeats']),'future_requests_total':int(r['future_requests'])})
    lc=rows('results/tsc_service/service_locality_aggregate_v0.csv')
    load=[]
    for fraction in (.6,.8,1.,1.2,1.4):
        v={}
        for policy in ('D0-native-apc','D2-template-contractkv'):
            r=only([x for x in lc if x['model']=='qwen' and int(x['tenants_per_template'])==25
                    and float(x['load_fraction'])==fraction and float(x['slo_ttft_ms'])==500 and x['policy']==policy])
            v[policy]=float(r['mean_slo_compliant_goodput_rps'])
        load.append({'load_pct':100*fraction,'raw_goodput':v['D0-native-apc'],
                     'CKV_goodput':v['D2-template-contractkv']})
    mt=rows('results/tsc_service/multi_tenant_aggregate_v0.csv')
    density=[]
    for n in (10,20,30,40,60,80):
        for policy in ('D0-native-apc','D2-full-contractkv'):
            r=only([x for x in mt if x['kind']=='density' and x['service_class']=='ALL'
                    and int(x['tenants'])==n and x['policy']==policy])
            density.append({'tenants':n,'policy':policy,'tiered_SLO_goodput':float(r['mean_slo_compliant_goodput_rps']),
                'peak_used_blocks':float(r['mean_peak_used_gpu_blocks']),
                'minimum_free_blocks':float(r['mean_minimum_free_gpu_blocks'])})
    sharing=[]
    for ratio in (0,.25,.5,.75,1):
        r=only([x for x in mt if x['kind']=='stageC' and x['service_class']=='ALL' and int(x['tenants'])==40
                and float(x['sharing_ratio'])==ratio and x['policy']=='D0-native-apc'])
        k=only([x for x in mt if x['kind']=='stageC' and x['service_class']=='ALL' and int(x['tenants'])==40
                and float(x['sharing_ratio'])==ratio and x['policy']=='D2-full-contractkv'])
        sharing.append({'sharing_pct':100*ratio,'TTFT_reduction_pct':100*(1-float(k['mean_mean_ttft_ms'])/float(r['mean_mean_ttft_ms']))})
    residency=[]
    for x in rows('results/tsc_service/locality_residency_policy_comparison_v0.csv'):
        if float(x['slo_ttft_ms'])==500:
            residency.append({'active_templates':int(x['active_templates']),'distribution':x['arrival_distribution'],
                'net_TTFT_reduction_pct':100*float(x['net_mean_ttft_reduction']),
                'CKV_prefix_hit_pct':100*float(x['contractkv_prefix_hit_ratio'])})
    assert len(residency)==6
    additional=rows('results/tsc_revision_r4/cost_adaptation_validation_v1/analysis/performance_comparison_v1.csv')
    additional_quality=rows('results/tsc_revision_r4/cost_adaptation_validation_v1/analysis/quality_summary_v1.csv')
    for x in additional:
        q=only([z for z in additional_quality if z['family']=='ALL' and z['policy']==x['policy']])
        x['compiled_future_pairs']=int(q['compiled_pairs'])
    baselines=[x for x in rows('results/tsc_revision_r1/matched_baseline_quality_thresholds_v1.csv')
               if x['family']=='ALL' and float(x['threshold'])==.03]
    legacy=[]
    for x in rows('results/submission_repeats/submission_repeat_aggregate_v0.csv'):
        legacy.append({'model':{'qwen':'Qwen3-8B','mistral':'Mistral-7B'}[x['model']],
                       'net_TTFT_reduction_pct':100*float(x['mean_net_mean_ttft_reduction']),
                       'tool_slack_ms':2000,'repeats':3})
    x=only(rows('results/scale_up/qwen3_14b_tp2_v0/aggregate_summary_v0.csv'))
    legacy.append({'model':'Qwen3-14B TP=2','net_TTFT_reduction_pct':100*float(x['net_mean_ttft_reduction_vs_raw']),
                   'tool_slack_ms':2000,'repeats':3})
    x=only([x for x in rows('results/cross_model/llama_broad_generalization_r3/heldout_scope_aggregate_v0.csv') if x['scope']=='all'])
    legacy.append({'model':'Llama-3.1-8B','net_TTFT_reduction_pct':100*float(x['net_mean_ttft_reduction']),
                   'tool_slack_ms':6000,'repeats':3})
    for name in ('scripts/run_submission_repeats.sh','scripts/run_phase22r_llama_broad.sh',
                 'docs/phase23_qwen3_14b_tp2_scaleup_report.md','submission/gen_tsc_figures_v5.py'):
        source(name)
    gates=rows('results/tsc_service/economics/heldout_gate_v1.csv')
    data={'schema_version':'contractkv.figure-data.v6','strict':strict,'behavior_audits':audits,
          'd1_d2':d1d2,'live_rejection':rejection,'granularity':granularity,'open_arrival_load':load,
          'density':density,'sharing':sharing,'residency':residency,
          'additional_Qwen_validation':additional,'matched_quality_tables':baselines,
          'legacy_slack_TTFT':legacy,'frozen_gate_table':gates,
          'protocol_boundaries':{'strict':'16K faithful inputs; greedy; closed loop; zero tool slack; six held-out sources; three fresh-process pairs/model.',
           'prefill':'Mean count per process, 600 business requests; initial scheduler prompt-minus-native-hit counters, certification counted separately; not GPU-kernel time.',
           'fig4':'Panel a five-process same-engine control; panel b live legal-layout controls; panel c three-process deployment-template granularity ablation. Do not merge their denominators.',
           'fig5_6':'Original deployment-template protocols, distinct from strict raw-witness validation. 80 tenant identities do not mean 80 simultaneous GPU requests.',
           'sharing_correction':'Fig6 old generator displayed 0.0% at zero sharing. Paired source CSV yields the actual negative point; no clipping.'}}
    (a.output/'figure_data_v6.json').write_bytes((json.dumps(data,indent=2)+'\n').encode())
    manifest={'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'sources':list(SOURCES.values()),'no_experimental_records_modified':True,
              'palette_and_style_base':'submission/gen_tsc_figures_v5.py'}
    (a.output/'source_manifest_v6.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
    print(json.dumps({'source_files':len(SOURCES),'strict_multipliers':[x['wall_multiplier'] for x in strict],
                      'coverage_pct':[x['compiled_future_pct'] for x in strict],
                      'zero_sharing_pct':sharing[0]['TTFT_reduction_pct']}))


if __name__=='__main__':main()
