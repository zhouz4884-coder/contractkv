"""Within-lane diagnostic for the frozen alternating-task assignment."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import write


def planned_gpu_map():
    assignments={}; index=0
    for study in ('single-session','template-fanout'):
        for repeat in (1,2,3):
            policies={1:('raw-order','query-full','query-prefix'),2:('query-prefix','raw-order','query-full'),3:('query-full','query-prefix','raw-order')}[repeat]
            for policy in policies:
                if study=='template-fanout' and policy=='query-full': continue
                for model in ('qwen','mistral','llama'):
                    assignments[f'{study}_{model}_{policy}_r{repeat}']=index%2; index+=1
    return assignments


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); assignments=planned_gpu_map()
    with (a.root/'summary/performance_by_cell_v1.csv').open(encoding='utf-8') as stream: rows=list(csv.DictReader(stream))
    groups=defaultdict(list)
    for r in rows: groups[(r['study'],r['model'],assignments[r['cell']],r['policy'])].append(r)
    comparisons=[]
    for (study,model,gpu,policy),rs in sorted(groups.items()):
        if policy=='raw-order' or (study,model,gpu,'raw-order') not in groups: continue
        raw=groups[(study,model,gpu,'raw-order')]
        comparisons.append({'study':study,'model':model,'launcher_gpu_lane':gpu,'policy':policy,
                            'raw_fresh_runs':len(raw),'policy_fresh_runs':len(rs),
                            'mean_raw_wall_s':statistics.fmean(float(r['wall_s']) for r in raw),
                            'mean_policy_wall_s':statistics.fmean(float(r['wall_s']) for r in rs),
                            'within_lane_goodput_multiplier':statistics.fmean(float(r['wall_s']) for r in raw)/statistics.fmean(float(r['wall_s']) for r in rs)})
    a.output.mkdir(parents=True,exist_ok=True)
    write(a.output/'launcher_gpu_assignment_v1.csv',[{'cell':name,'gpu_lane':lane} for name,lane in assignments.items()])
    if comparisons: write(a.output/'within_gpu_lane_diagnostic_v1.csv',comparisons)
    note={'assignment_source':'Exact task-index modulo two order in frozen validation launcher; no manual cell resumption in this run',
          'not_independent_device_telemetry':True,'hardware_snapshots':'Actual per-cell manifests retain both physical GPU UUID/memory snapshots',
          'diagnostic_only':'Within-lane run means use one or two policy runs in some groups; not a new randomized trial or replacement of primary estimands',
          'full_pair_gpu_lock_or_perfect_counterbalance_not_claimed':True}
    (a.output/'gpu_diagnostic_manifest_v1.json').write_text(json.dumps(note,indent=2)+'\n'); print(json.dumps(note))


if __name__=='__main__': main()
