"""Append measured horizon followup without changing the original R1 producer."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
    with (args.root/'output_horizon_summary_v1.csv').open(encoding='utf-8',newline='') as stream:
        rows=[r for r in csv.DictReader(stream) if r['cohort']=='R1' and r['study']=='free-generation']
    count=sum(int(r['compiled_futures']) for r in rows)
    exceeded=sum(int(r['outputs_exceed_reference_length']) for r in rows)
    positions=sum(int(r['positions_beyond_reference_length']) for r in rows)
    marker='### Measured positions beyond the actual witness length'
    section=[marker,'',
             f'A followup over the immutable R1 raw records finds {exceeded}/{count} admitted free-generation futures longer than their own Turn-0 raw reference, totaling {positions} returned token positions beyond that reference length. These positions are reported separately and are not labelled certified. Requests share sources and repeats, and the two budget conditions are correlated. Counts include the terminal stop when returned.','',
             '| Model | Budget condition | Compiled futures | Reference length range | Future max | Longer outputs | Extra positions |',
             '|---|---|---|---|---|---|---|']
    for r in rows:
        section.append('| '+' | '.join([r['model'],r['budget_condition'],r['compiled_futures'],
                      r['reference_tokens_min']+'–'+r['reference_tokens_max'],r['future_tokens_max'],
                      r['outputs_exceed_reference_length'],r['positions_beyond_reference_length']])+' |')
    section += ['',
                'The original main retained reference lengths/hashes but no direct reference token IDs, so first divergence from that witness is unavailable. The raw-versus-compiled future-pair divergence still uses actual returned IDs. Even within the length bound, a changed token history is not covered by the original teacher-forced path. This followup changes no admission, task score or original raw record. Per-request evidence is in `results/tsc_revision_r1/output_horizon_pairs_v1.csv`; the separately versioned producer is `scripts/tsc_revision_r1r_output_horizon.py`.','']
    anchor='## X3. Complete Verification Cost and Live Zero-Slack Service'
    text=args.report.read_text(encoding='utf-8'); before,after=text.split(anchor,1)
    if marker in before: before=before.split(marker,1)[0]
    args.report.write_text(before.rstrip()+'\n\n'+'\n'.join(section)+'\n'+anchor+after,encoding='utf-8')
    result={'schema_version':'tsc-r1.horizon-followup-report.v1','compiled_free_futures':count,
            'outputs_exceed_reference_length':exceeded,'positions_beyond_reference_length':positions,
            'original_raw_data_unchanged':True,'reference_sequence_comparisons_not_invented':True}
    (args.root/'horizon_followup_report_metrics_v1.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
