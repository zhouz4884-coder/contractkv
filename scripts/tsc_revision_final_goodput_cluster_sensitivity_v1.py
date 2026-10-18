"""Conditional source/process sensitivity at the observed clocks, not new queues."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random

STUDY='results/tsc_task_faithful_open_arrival_20261018'
SEED=202610182002
DRAWS=10000


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def csvrows(path):
    with path.open(encoding='utf-8',newline='') as handle:return list(csv.DictReader(handle))
def interval(values):
    values=sorted(values)
    def q(p):
        at=(len(values)-1)*p;low=math.floor(at);high=math.ceil(at)
        return values[low]+(values[high]-values[low])*(at-low)
    return [q(.025),q(.975)]


def main(root,output):
    assert not output.exists()
    study=root/STUDY;plan=read(study/'formal_statistics_addendum_v1.json')
    assert plan['source_sha256']==sha(Path(__file__)) and plan['seed']==SEED and plan['draws']==DRAWS
    assert plan['formal_freeze_sha256']==sha(study/'formal_freeze_v1.json')
    analysis=study/'formal_analysis_v1';summary=read(analysis/'summary_v1.json');assert summary['complete_cells']==30
    requests=csvrows(analysis/'requests_v1.csv');pairs=csvrows(analysis/'paired_performance_v1.csv')
    cells={c['cell']:c for c in summary['cells']};counts=defaultdict(Counter);families={}
    for row in requests:
        source=row['source_group'];families[source]=row['family']
        counts[row['cell']][source]+=int(row['primary_SLO_compliant']=='True')
    groups=defaultdict(list)
    for pair in pairs:groups[pair['regime'],pair['model'],pair['load']].append(pair)
    strata={family:sorted(s for s,f in families.items() if f==family) for family in sorted(set(families.values()))}
    assert len(families)==6 and all(len(s)==3 for s in strata.values())
    out=[]
    for (regime,model,load),group in sorted(groups.items()):
        group=sorted(group,key=lambda p:int(p['repeat']));assert len(group)==3
        for pair in group:
            for cell in (pair['baseline'],pair['treatment']):
                assert sum(counts[cell].values())==cells[cell]['compliant_requests']
                assert cells[cell]['business_requests']==360
        base_total=sum(cells[p['baseline']]['compliant_requests'] for p in group)
        treatment_total=sum(cells[p['treatment']]['compliant_requests'] for p in group)
        base_clock=sum(cells[p['baseline']]['wall_s'] for p in group);treatment_clock=sum(cells[p['treatment']]['wall_s'] for p in group)
        point=dict(baseline_compliant=base_total,treatment_compliant=treatment_total,business_per_policy=1080,
            baseline_goodput=base_total/base_clock,treatment_goodput=treatment_total/treatment_clock,
            absolute_goodput_change=treatment_total/treatment_clock-base_total/base_clock,
            goodput_ratio=(treatment_total/treatment_clock)/(base_total/base_clock) if base_total else None)
        rng=random.Random(SEED);baseline=[];treatment=[];delta=[];ratios=[];zero_baseline=0
        for _ in range(DRAWS):
            processes=rng.choices(group,k=3)
            sources=[s for family in sorted(strata) for s in rng.choices(strata[family],k=3)]
            b=sum(counts[p['baseline']][s] for p in processes for s in sources)
            t=sum(counts[p['treatment']][s] for p in processes for s in sources)
            bc=sum(cells[p['baseline']]['wall_s'] for p in processes);tc=sum(cells[p['treatment']]['wall_s'] for p in processes)
            bg=b/bc;tg=t/tc;baseline.append(bg);treatment.append(tg);delta.append(tg-bg)
            if bg:ratios.append(tg/bg)
            else:zero_baseline+=1
        out.append(dict(regime=regime,model=model,load=load,comparison=group[0]['comparison'],point=point,
            conditional_baseline_goodput_interval=interval(baseline),conditional_treatment_goodput_interval=interval(treatment),
            conditional_absolute_change_interval=interval(delta),
            ratio_interval=interval(ratios) if zero_baseline==0 else None,
            ratio_defined_draws=len(ratios),zero_baseline_draws=zero_baseline,
            source_clusters=6,fresh_process_pairs=3,
            no_ratio_interval_when_any_bootstrap_baseline_zero=True))
    result=dict(schema_version='contractkv.conditional-goodput-source-sensitivity.v1',seed=SEED,draws=DRAWS,results=out,
        all_observed_cell_clocks_retained=True,paired_source_and_process_weights=True,
        no_new_queue_or_GPU_work_reconstructed=True,
        boundary='Conditional sensitivity of observed SLO-compliant counts to six-source composition and3 paired repeats at their actual clocks; NOT a causal queueing, workload-population capacity or reweighted-wall confidence interval.',
        planned_before_any_formal_Contract_output=True,source_sha256=sha(Path(__file__)),new_GPU_requests=0,
        inputs=[dict(path=p.relative_to(root).as_posix(),sha256=sha(p)) for p in [analysis/'summary_v1.json',analysis/'requests_v1.csv',analysis/'paired_performance_v1.csv']])
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output)
