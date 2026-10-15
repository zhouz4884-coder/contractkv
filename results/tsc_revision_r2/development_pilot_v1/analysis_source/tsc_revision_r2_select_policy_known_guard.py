"""Before-test amendment: known batch failures constrain the raw early gate."""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_select_policy import select
from scripts.phase17_live_common import digest

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    for name in ('plan','profile-analysis','known-batch-root','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();old=json.loads(a.plan.read_text(encoding='utf-8'));plan=deepcopy(old)
    path=a.known_batch_root/'mistral/raw.jsonl';closed=json.loads(path.with_suffix('.summary.json').read_text(encoding='utf-8'))
    if not closed['execution_complete'] or closed['raw_sha256']!=sha(path):raise ValueError('Known batch evidence changed')
    audit=json.loads((a.known_batch_root/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']:raise ValueError('Known actual batch audit required')
    rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
    references={r['repeat']:r for r in rows if r['role']=='reference'};failures=[]
    for repeat,reference in references.items():
        raw=next(r for r in rows if r['repeat']==repeat and r['role']=='raw' and r['variant']=='future')
        compiled=next(r for r in rows if r['repeat']==repeat and r['role']=='certified_salt' and r['variant']=='future')
        if raw['score']-compiled['score']>.03:
            failures.append({'repeat':repeat,'reference_prompt_ids_sha256':reference['prompt_ids_sha256'],
                'reference_output_ids_sha256':digest(reference['output_token_ids']),'raw_full_min_including_eos':min(reference['raw_margins']),
                'raw_future_score':raw['score'],'compiled_future_score':compiled['score'],
                'candidate_token_margins_not_recorded_in_this_old_batch_study':True})
    if len(failures)!=3:raise ValueError('Preidentified three repeated known-case failures not found')
    ceiling=max(r['raw_full_min_including_eos'] for r in failures)
    plan['raw_answer_minimum_margin_grid']=[x for x in old['raw_answer_minimum_margin_grid'] if x>ceiling]
    if not plan['raw_answer_minimum_margin_grid']:raise ValueError('No predeclared grid value blocks known raw reference')
    analysis=a.profile_analysis/'selection_input_v1.json'
    result,grid=select(plan,json.loads(analysis.read_text(encoding='utf-8')))
    result.update(schema_version='tsc-r2.frozen-single-shot-catalog.v2',
        selection_plan_sha256=sha(a.plan),profile_selection_input_sha256=sha(analysis),
        before_independent_heldout_amendment={'reason':'The profile-only optimum permits the already observed bad Mistral batch reference at equality. Require raw early rejection of this known negative control before independent test use.',
          'constraint':'raw_floor > maximum observed full raw-reference minimum among the three correlated repeats of one known bad batch source',
          'known_batch_raw_sha256':sha(path),'raw_floor_must_exceed':ceiling,'known_cases':failures,
          'does_not_prove_all_candidate_gate_outcomes_in_historical_batch':True,'original_v1_pilot_and_profile_preserved':True,
          'new_heldout_outcomes_not_used':True})
    if a.output.exists():raise RuntimeError('Preserve prior selected policy')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with a.output.with_suffix('.grid.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(grid[0]));writer.writeheader();writer.writerows(grid)
    print(json.dumps({'raw_floor':result['raw_token_margin_floor'],'candidate_floor':result['candidate_token_margin_floor'],'factor':result['benefit_safety_factor'],'known_bad_reference_rejected_before_GPU':all(r['raw_full_min_including_eos']<result['raw_token_margin_floor'] for r in failures),'known_cases':len(failures),'no_new_heldout_outcome_used':True,'catalog_sha256':sha(a.output)}))

if __name__=='__main__':main()
