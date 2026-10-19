"""Freeze contract-aware admission on50 untouched sources after R2 diagnosis."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    base=root/'results/tsc_revision_r3/validation_v1';configpath=root/'configs/tsc_revision_r3_validation_v1.json'
    config=json.loads(configpath.read_text());prior=root/'results/tsc_revision_r2/validation_v1'
    if (base/'freeze.json').exists():raise RuntimeError('Preserve new prospective freeze')
    audit=json.loads((prior/'analysis/completion_audit_v1.json').read_text())
    if not audit['execution_complete'] or audit['complete_cells']!=54:raise ValueError('Preserve complete R2 evidence')
    inputs=root/'results/tsc_revision_r3/inputs';commitment=json.loads((inputs/'input_commitment_v1.json').read_text())
    if commitment['excluded_sources']!=412 or commitment['selection_uses_model_outputs_or_scores']:raise ValueError('Fresh source protocol')
    for filename,key in [('heldout_sealed_sessions_v1.jsonl','heldout_sessions_sha256'),('heldout_fanout_v1.jsonl','fanout_sessions_sha256')]:
        if sha(inputs/filename)!=config[key] or sha(inputs/filename)!=commitment['cohorts'][filename]['sha256']:raise ValueError('Fresh input changed')
    original=json.loads((prior/'freeze.json').read_text());files={r['path'] for r in original['files']}
    files.update(('scripts/tsc_revision_r3_freeze_inputs.py','scripts/tsc_revision_r3_freeze_validation.py',
       'scripts/tsc_revision_r3_live.py','scripts/tsc_revision_r3_live_summary.py','scripts/tsc_revision_r3_output_contract.py',
       'scripts/run_tsc_revision_r3_validation.sh','configs/tsc_revision_r3_catalog_v1.json','configs/tsc_revision_r3_validation_v1.json',
       'results/tsc_revision_r3/inputs/input_commitment_v1.json','results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl',
       'results/tsc_revision_r3/inputs/heldout_fanout_v1.jsonl'))
    base.mkdir(parents=True,exist_ok=True);rows=[];index=0
    for study in config['studies']:
        for repeat in range(1,4):
            for model in config['models']:
                for policy in config['policy_order'][str(repeat)]:rows.append({'cell':f'{study}_{model}_{policy}_r{repeat}','gpu_lane':index%2})
                index+=1
    path=base/'launcher_gpu_assignment_v1.csv'
    with path.open('w',newline='',encoding='utf-8') as out:
        writer=csv.DictWriter(out,fieldnames=('cell','gpu_lane'));writer.writeheader();writer.writerows(rows)
    review={'timestamp':datetime.now(timezone.utc).isoformat(),'R2_archive_sha256':'9a36851190d6958c2b3258275bce31ad33a4e592cb43c8a0a28bb7eb0ceda403',
      'R2_frozen_results_preserved':True,'R2_material_compiled_drops':7,'R2_distinct_failure_model_source_units':2,
      'amendment':'CPU Python-output syntax eligibility; candidate floor .125 from old grid; raw floor .0625 and cost/levels/one-shot unchanged',
      'new_R3_source_outcomes_used':False,'known_case_replay_would_not_be_unseen_validation':True}
    (base/'development_review_v1.json').write_text(json.dumps(review,indent=2)+'\n')
    files.update(('results/tsc_revision_r3/validation_v1/development_review_v1.json','results/tsc_revision_r3/validation_v1/launcher_gpu_assignment_v1.csv'))
    result=freeze_scope(root,base,configpath,files,{'fresh50_excludes_all412_prior_sources':True,'previous_R2_results_preserved':True,
        'catalog_sha256':sha(root/config['selected_catalog']),'R3_model_outputs_unused_for_selection':True})
    logs=root/'logs/tsc_revision_r3';logs.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/'scripts/run_tsc_revision_r3_validation.sh',logs/'validation_snapshot_v1.sh')
    print(json.dumps(result))

if __name__=='__main__':main()
