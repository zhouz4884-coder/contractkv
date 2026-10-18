"""Apply the fixed, single-DEV-candidate selection rule without any new test data."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def read_csv(path):
    with Path(path).open(encoding='utf-8',newline='') as stream:return list(csv.DictReader(stream))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists()
    freeze=json.loads((args.root/'freeze.json').read_text(encoding='utf-8'))
    assert freeze['protocol']['development_only'] and freeze['protocol']['expected_cells']==3
    audit=json.loads((args.root/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    assert audit['execution_complete'] and audit['complete_cells']==3
    quality={row['policy']:row for row in read_csv(args.root/'analysis/quality_summary_v1.csv') if row['family']=='ALL'}
    performance={row['policy']:row for row in read_csv(args.root/'analysis/performance_by_cell_v1.csv')}
    timing=read_csv(args.root/'analysis/request_latency_pairs_v1.csv')
    from scripts.tsc_revision_r2_select_policy import percentile
    target={policy:percentile([float(row['ready_ttft_ms']) for row in timing if row['policy']==policy and row['family']=='RepoBench' and row['row_type']=='future'],.99)
            for policy in ('risk-tail','cost-adapted')}
    failed_work={}
    for policy in ('risk-tail','cost-adapted'):
        cell=args.root/'cells'/f'template-fanout_qwen_{policy}_r1'
        rows=[json.loads(line) for line in (cell/'raw.jsonl').open(encoding='utf-8')]
        failed_work[policy]=sum(attempt['verification_ms'] for row in rows if row['row_type']=='verification'
                                for attempt in row['attempts'] if not attempt['certificate_issued'])
    original=float(quality['risk-tail']['compiled_pairs']);adapted=float(quality['cost-adapted']['compiled_pairs'])
    checks={
        'no_compiled_ID_divergence':int(quality['cost-adapted']['compiled_ID_divergences'])==0,
        'no_compiled_any_score_decrease':int(quality['cost-adapted']['compiled_any_score_decrease'])==0,
        'all_route_material_drops_not_increased':int(quality['cost-adapted']['all_material_drops'])<=int(quality['risk-tail']['all_material_drops']),
        'compiled_future_coverage_retained_at_least_80pct':original>0 and adapted>=.8*original,
        'full_wall_lower_than_fresh_original':float(performance['cost-adapted']['wall_s'])<float(performance['risk-tail']['wall_s']),
        'full_wall_lower_than_fresh_raw':float(performance['cost-adapted']['wall_s'])<float(performance['raw-order']['wall_s']),
        'RepoBench_ready_p99_lower_than_original':target['cost-adapted']<target['risk-tail'],
        'rejected_GPU_RPC_work_lower':failed_work['cost-adapted']<failed_work['risk-tail'],
    }
    result={'schema_version':'tsc-r4.fixed-DEV-cost-candidate-selection.v1',
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'freeze_sha256':hashlib.sha256((args.root/'freeze.json').read_bytes()).hexdigest(),
            'checks':checks,'all_prespecified_DEV_checks_pass':all(checks.values()),
            'maximum_conditional_independent_Q_cells':9 if all(checks.values()) else 0,
            'original_compiled_futures':original,'adapted_compiled_futures':adapted,
            'RepoBench_ready_p99_ms':target,'failed_GPU_RPC_work_ms':failed_work,
            'all_route_material_drops':{policy:int(quality[policy]['all_material_drops']) for policy in ('risk-tail','cost-adapted')},
            'global_ready_p99_ms':{policy:float(performance[policy]['p99_ready_ttft_ms']) for policy in ('risk-tail','cost-adapted')},
            'raw_versus_policy_full_wall_s':{policy:float(row['wall_s']) for policy,row in performance.items()},
            'new_heldout_model_outputs_used_for_selection':False,
            'limits':'One DEV process, four known sources. Point selection is not a confidence claim. If false, retain the negative and stop this candidate; no new grid or reruns until favorable.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'all_prespecified_DEV_checks_pass':all(checks.values()),'checks':checks}))


if __name__=='__main__':main()
