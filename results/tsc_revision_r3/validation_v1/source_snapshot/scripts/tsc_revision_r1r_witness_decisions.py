"""Expose full/read admission differences without assuming bitwise invariance."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write


def indexed(rows):
    business={(r['session_id'],r['query_scope'],r['turn_id']):r for r in rows if r['row_type'] in ('warm','future')}
    result={}
    for row in rows:
        if row['row_type']=='verification':
            result[(row['certificate_namespace'],row['query_scope'])]=(row,business[(row['session_id'],row['query_scope'],row['turn_id'])])
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cells={}
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        rows=read(path.parent/'raw.jsonl'); first=next(r for r in rows if r['row_type']=='future')
        cells[(first['study'],first['model'],first['repeat'],first['policy'])]=indexed(rows)
    differences=[]; compared=0; same_refs=0; changed=0; summary=[]
    for key,prefix in cells.items():
        study,model,repeat,policy=key
        if policy!='query-prefix' or (study,model,repeat,'query-full') not in cells: continue
        full=cells[(study,model,repeat,'query-full')]
        for scope_key,(pr,pw) in prefix.items():
            if scope_key not in full: continue
            fr,fw=full[scope_key]; compared+=1
            equal=pw['output_token_ids']==fw['output_token_ids'] and pw['finish_reason']==fw['finish_reason']
            same_refs+=equal
            fa={r['level']:r for r in fr['attempts']}; pa={r['level']:r for r in pr['attempts']}
            outcome_changed=(fr['certificate_issued'],fr['selected_level'])!=(pr['certificate_issued'],pr['selected_level'])
            changed+=outcome_changed
            for level in sorted(fa.keys()&pa.keys()):
                x,y=fa[level],pa[level]
                if x['certificate_issued']==y['certificate_issued']: continue
                differences.append({'study':study,'model':model,'repeat':repeat,'namespace':scope_key[0],'query_scope':scope_key[1],
                                    'level':level,'same_raw_reference_ids':equal,'same_witness_turn':fw['turn_id']==pw['turn_id'],
                                    'full_issued':x['certificate_issued'],'prefix_issued':y['certificate_issued'],
                                    'full_candidate_q05':x.get('candidate_margin_q05'),'prefix_candidate_q05':y.get('candidate_margin_q05'),
                                    'full_stop_margin':x.get('terminal_stop_margin'),'prefix_stop_margin':y.get('terminal_stop_margin'),
                                    'prefix_read_tokens':y.get('cached_prefix_read_tokens',0),
                                    'full_failure':x.get('failure_reason'),'prefix_failure':y.get('failure_reason')})
    a.output.mkdir(parents=True,exist_ok=True)
    if differences: write(a.output/'witness_decision_differences_v1.csv',differences)
    result={'scope_registrations_compared':compared,'same_raw_reference_id_registrations':same_refs,
            'different_final_admissions_or_levels':changed,'different_matched_level_decisions':len(differences),
            'different_matched_level_decisions_with_same_reference':sum(r['same_raw_reference_ids'] for r in differences),
            'same_reference_decision_changes_with_zero_prefix_read':sum(r['same_raw_reference_ids'] and r['prefix_read_tokens']==0 for r in differences),
            'same_reference_decision_changes_with_actual_prefix_read':sum(r['same_raw_reference_ids'] and r['prefix_read_tokens']>0 for r in differences),
            'claim':'Controlled color probes check agreement. Real workloads need not have bitwise-identical admission decisions.',
            'hypothesis_not_proven':'Cached-vs-recomputed FP16 and batch-shape arithmetic can change rank-one decisions near a boundary; raw reference and EOS changes are separate possibilities. A same-input repeated cold/read replay is required to identify the numerical cause.',
            'no_data_retuning':True}
    (a.output/'witness_decision_audit_v1.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
