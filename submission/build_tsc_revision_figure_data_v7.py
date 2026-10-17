"""Extend the preserved v6 ledgers for the information-focused v7 figures."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

import build_tsc_revision_figure_data_v6 as base
from extract_tsc_revision_trace_v7 import extract

ROOT=Path(__file__).resolve().parents[1]


def write(path,value):path.write_bytes((json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode())


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017_v7');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    previous=sys.argv;sys.argv=[sys.argv[0],'--output',str(a.output)]
    try:base.main()
    finally:sys.argv=previous
    d=json.loads((a.output/'figure_data_v6.json').read_text(encoding='utf-8'))
    d['schema_version']='contractkv.figure-data.v7'
    perf=base.rows('results/tsc_revision_r4/input_fidelity_validation_v1/analysis/performance_comparison_v1.csv')
    cells=base.rows('results/tsc_revision_r4/input_fidelity_validation_v1/analysis/performance_by_cell_v1.csv')
    q=base.rows('results/tsc_revision_r4/input_fidelity_validation_v1/analysis/quality_summary_v1.csv')
    catalog=base.obj('results/tsc_revision_r4/development_fit_v3/calibration_v1.json')
    for r in d['strict']:
        row=base.only([x for x in perf if x['model']==r['model'] and x['policy']=='risk-tail'])
        r.update(raw_ready_mean_ms=float(row['raw_ready_mean_ms']),CKV_ready_mean_ms=float(row['policy_ready_mean_ms']),
                 ready_mean_reduction_pct=float(row['ready_mean_reduction_pct']),
                 ready_mean_reduction_CI95_low=float(row['ready_mean_cluster_repeat_ci95_low']),
                 ready_mean_reduction_CI95_high=float(row['ready_mean_cluster_repeat_ci95_high']))
        r['repeat_ready_means_ms']={policy:[float(x['mean_ready_ttft_ms']) for x in sorted(cells,key=lambda x:int(x['repeat']))
            if x['model']==r['model'] and x['policy']==policy] for policy in ('raw-order','risk-tail')}
        r['net_prefill_reduction_pct']=100*(1-(r['CKV_business_prefill_per_repeat']+r['qualification_prefill_per_repeat'])/r['raw_business_prefill_per_repeat'])
        families=[]
        for family in ('HotpotQA','RepoBench'):
            x=base.only([x for x in q if x['model']==r['model'] and x['family']==family and x['policy']=='risk-tail'])
            inherited=catalog['models'][r['model']]['template-fanout'][family].get('reason')=='inherited_family_L0'
            if inherited:assert int(x['compiled_pairs'])==0
            families.append({'family':family,'future_pairs':int(x['pairs']),'compiled_pairs':int(x['compiled_pairs']),
                             'coverage_pct':100*int(x['compiled_pairs'])/int(x['pairs']),
                             'inherited_L0':inherited})
        assert all(x['future_pairs']==810 for x in families)
        r['family_coverage']=families
    earlier=base.rows('results/tsc_revision_r4/validation_closed_v1/analysis/quality_pairs_v1.csv')
    groups=defaultdict(list)
    for x in earlier:
        if x['policy']=='risk-tail' and x['effective_level']!='L0':groups[(x['family'],x['study'])].append(x)
    audit=[]
    for (family,study),values in sorted(groups.items()):
        scorer='string-match credit' if family=='RULER' else ('code similarity credit' if family=='RepoBench' else 'QA F1 credit')
        audit.append({'family':family,'study':study,'scorer_group':scorer,'compiled_future_pairs':len(values),
                      'raw_score_positive':sum(float(x['raw_score'])>0 for x in values),
                      'raw_score_zero':sum(float(x['raw_score'])==0 for x in values)})
    assert sum(x['compiled_future_pairs'] for x in audit)==2442
    assert sum(x['raw_score_positive'] for x in audit)==2442
    d['earlier_positive_score_audit']=audit
    with (a.output/'earlier_score_credit_audit_v7.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(audit[0]));w.writeheader();w.writerows(audit)
    excerpt,trace=extract(a.output/'trace_log_excerpt_v7.json')
    base.source((a.output/'trace_log_excerpt_v7.json').relative_to(ROOT).as_posix())
    d['measured_trace']=trace
    d['upstream_trace_files']=excerpt['upstream_files']
    d['governance_goodput_retained_pct']=100*d['d1_d2'][1]['goodput']/d['d1_d2'][0]['goodput']
    for x in d['live_rejection']:
        assert x['published_rejected_tokens']==0
        x['rejected_candidate_blocks_promoted']=0
        x['block_zero_evidence']='Zero committed candidate tokens on each FAIL/ABORT; no claim that native raw fallback caching is disabled.'
    density=base.rows('results/tsc_service/multi_tenant_cell_summary_v0.csv')
    d['density80_same_cell_audit']=[]
    for policy in ('D0-native-apc','D2-full-contractkv'):
        v=[x for x in density if x['kind']=='density' and x['service_class']=='ALL' and int(x['tenants'])==80 and x['policy']==policy]
        assert len(v)==3
        agg=base.only([x for x in d['density'] if x['tenants']==80 and x['policy']==policy])
        assert abs(sum(float(x['slo_compliant_goodput_rps']) for x in v)/3-agg['tiered_SLO_goodput'])<1e-10
        assert all(float(x['peak_used_gpu_blocks'])==agg['peak_used_blocks'] and float(x['minimum_free_gpu_blocks'])==agg['minimum_free_blocks'] for x in v)
        d['density80_same_cell_audit'].append({'policy':policy,'rows':[{
            k:x[k] for k in ('cell_id','repeat','slo_compliant_goodput_rps','peak_used_gpu_blocks','minimum_free_gpu_blocks')} for x in v]})
    d['protocol_boundaries']['fig5_6']='Original deployment-template protocols. Fig5(a): open-arrival, 500-ms SLO. Fig5(b): separate 80-identity wave density replay with class-specific 750/1500/3000-ms SLOs. Same density cells supply block and goodput values; no capacity-causality claim.'
    for name in ('submission/build_tsc_revision_figure_data_v6.py','scripts/tsc_multi_tenant_live.py',
                 'scripts/run_tsc_multi_tenant.sh','scripts/phase20a_official_quality.py',
                 'Paper/figures/revision_20261017/supporting_tables_v6.md'):
        base.source(name)
    write(a.output/'figure_data_v7.json',d)
    write(a.output/'source_manifest_v7.json',{'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sources':list(base.SOURCES.values()),'upstream_full_trace_containers':excerpt['upstream_files'],
        'trace_bundle_boundary':'Compact bundle includes exact selected trace records. Full archived raw/metric file hashes and line indices are retained for independent re-extraction.',
        'no_experimental_records_modified':True,'previous_figures_preserved':'Paper/figures/revision_20261017'})
    print(json.dumps({'version':7,'sources':len(base.SOURCES),'family_compiled':[[x['compiled_pairs'] for x in r['family_coverage']] for r in d['strict']],
                      'mean_ready_reduction_pct':[r['ready_mean_reduction_pct'] for r in d['strict']],
                      'trace_verified':trace['actual_identical_output_IDs'],'D2_retained_pct':d['governance_goodput_retained_pct']}))


if __name__=='__main__':main()
