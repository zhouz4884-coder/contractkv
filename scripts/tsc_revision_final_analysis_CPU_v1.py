"""Synthetic CPU edge controls for statistics, with no inference or serving claim."""
import argparse
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_serving_analysis_v1 as analysis


def main(output):
    checks=[]
    assert analysis.first_divergence([1,2],[1,2])==-1
    assert analysis.first_divergence([1,2],[1,2,3])==2
    assert analysis.first_divergence([1,2],[1,4])==1
    assert analysis.ratio(0,0) is None and analysis.ratio(0,2)==0
    checks.append('actual ID first divergence handles suffix and zero denominator without pseudocount')
    dummy=[]
    for family in ('HotpotQA','RepoBench'):
        for source in range(3):
            for repeat in (1,2,3):
                for typ in ('warm','future'):
                    compiled=family=='HotpotQA'
                    dummy.append(dict(model='CPU-fixture',load='common',source_group=f'{family}-{source}',family=family,
                        repeat=repeat,row_type=typ,compiled=compiled,output_ID_change=False,finish_change=False,
                        material_up=not compiled and source==0,material_down=False,raw_positive=True,
                        raw_score=.5,contract_score=.6 if not compiled and source==0 else .5))
    result=analysis.quality_clusters(dummy)
    for r in result:
        if r['family']=='RepoBench' and r['route']=='compiled':
            assert r['pairs']==0 and r['ID_change_rate'] is None
            assert r['source_cluster_uncertainty']['ID_change_rate']==dict(CI95=None,defined_draws=0,undefined_draws=10000)
        assert r['material_down']==0
    overall=next(r for r in result if r['family']=='ALL' and r['route']=='ALL' and r['cohort']=='ALL_business')
    assert overall['pairs']==36 and overall['compiled']==18 and overall['coverage']==.5 and overall['material_up']==6
    checks.append('stratified source bootstrap preserves all within-source repeats and empty compiled stratum; undefined draws retained')
    performance=analysis.bootstrap_ratios([dict(wall_speedup=1,primary_goodput_ratio=None,TTFT_only_goodput_ratio=1.2)]*3,202610182000)
    assert performance['primary_goodput_ratio']['undefined_pairs']==3
    assert performance['wall_speedup']['CI95']==[1,1]
    checks.append('paired process bootstrap leaves zero-baseline Goodput ratio undefined; no favorable-pair deletion')
    assert analysis.category('inherited_family_L0')=='inherited_family_L0'
    assert analysis.category('observation_scope_has_no_declared_exact_reuse')=='exact_observation_scope_without_declared_reuse'
    assert analysis.category('raw_output_contract:python_syntax_SyntaxError')=='raw_output_contract'
    checks.append('routing keeps inherited L0, exact observation scope and output contract distinct')
    assert analysis.registration_queue_bounds(4000,10,9,16)==(6000,4000,4000)
    assert analysis.registration_queue_bounds(4000,10,15,16)==(6000,0,1000)
    assert analysis.registration_queue_bounds(4000,10,17,16)==(6000,0,0)
    checks.append('registration overlap is bounded correctly for already queued, late and not-yet-arrived requests; no invented exact causal timestamps')
    value=dict(schema_version='contractkv.final-analysis-CPU.v1',all_passed=True,new_GPU_requests=0,
        checks=checks,analysis_source_sha256=analysis.sha(Path(analysis.__file__)),
        synthetic_checks_are_not_measured_effects_or_confidence_intervals=True)
    analysis.write_json(output,value);print(json.dumps(value))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();main(args.output)
