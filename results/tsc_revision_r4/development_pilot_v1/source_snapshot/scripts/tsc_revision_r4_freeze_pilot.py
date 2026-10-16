"""Prospective freeze of observed-data real serving pilot, before new test use."""
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
    base=root/'results/tsc_revision_r4/development_pilot_v1';configpath=root/'configs/tsc_revision_r4_development_pilot_v1.json'
    config=json.loads(configpath.read_text(encoding='utf-8'))
    if (base/'freeze.json').exists():raise ValueError('Preserve pilot version')
    known=root/'results/tsc_revision_r4/diagnosis_v1'
    if not json.loads((known/'analysis/completion_audit_v1.json').read_text())['execution_complete']:raise ValueError('Known diagnostic audit first')
    parent=json.loads((known/'freeze.json').read_text(encoding='utf-8'));files={r['path'] for r in parent['files']}
    files.update(('scripts/tsc_revision_r4_live.py','scripts/tsc_revision_r4_cost_policy.py','scripts/tsc_revision_r4_policy_v2.py',
       'scripts/tsc_revision_r4_policy.py','scripts/tsc_revision_r4_fit_costs.py','scripts/tsc_revision_r4_fit_costs_v2.py',
       'scripts/tsc_revision_r4_augment_costs.py','scripts/tsc_revision_r4_make_pilot_inputs.py','scripts/tsc_revision_r4_freeze_pilot.py',
       'scripts/run_tsc_revision_r4_development_pilot.sh','configs/tsc_revision_r4_development_pilot_v1.json',
       'configs/tsc_revision_r4_development_plan_v2.json','results/tsc_revision_r4/development_fit_v3/calibration_v1.json',
       'results/tsc_revision_r4/development_inputs_v1/cold_sessions.jsonl','results/tsc_revision_r4/development_inputs_v1/fanout_sessions.jsonl',
       'results/tsc_revision_r4/development_inputs_v1/input_commitment_v1.json',
       'tests/test_tsc_revision_r4_policy.py','tests/test_tsc_revision_r4_policy_v2.py','tests/test_tsc_revision_r4_cost_policy.py'))
    commitment=json.loads((root/'results/tsc_revision_r4/development_inputs_v1/input_commitment_v1.json').read_text(encoding='utf-8'))
    for name,record in commitment['files'].items():
        if sha(root/'results/tsc_revision_r4/development_inputs_v1'/name)!=record['sha256']:raise ValueError('Development input changed')
    base.mkdir(parents=True);assign=[];index=0
    for study in config['studies']:
        for model in config['models']:
            orders=(['raw-order','previous-refined','risk-tail'],['previous-refined','risk-tail','raw-order'],['risk-tail','raw-order','previous-refined'])
            for policy in orders[index%3]:assign.append({'cell':f'{study}_{model}_{policy}_r1','gpu_lane':index%2})
            index+=1
    path=base/'launcher_gpu_assignment_v1.csv'
    with path.open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=('cell','gpu_lane'));writer.writeheader();writer.writerows(assign)
    review={'timestamp':datetime.now(timezone.utc).isoformat(),'known_case_archive_sha256':'227a59e05023e361624365c539ae2271e128d522bc05131e8fb7ecc29301f943',
            'observed_data_only':True,'real_development_not_unseen_validation':True,'formal_new50_outcomes_used':False,
            'scope_rule':'v2 short/nonabstaining; literal or nonliteralraw>.125, unchanged backendfloors .0625/.125',
            'cost_rule':'Two-stage expected cost + prior same stableprefix state, balanced profile; every CPU/GPU delay retained in actual wall',
            'formal_arrival_protocol_pending':'Must freeze same exogenous arrivals for all policies before independent validation; this pilot retains original closed-loop wave.'}
    (base/'development_review_v1.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    files.update(('results/tsc_revision_r4/development_pilot_v1/launcher_gpu_assignment_v1.csv',
                  'results/tsc_revision_r4/development_pilot_v1/development_review_v1.json'))
    result=freeze_scope(root,base,configpath,files,{'development_only':True,'new50_still_unseen':True,
        'all_previous_measured_sources_preserved':True,'profile':'balanced','independent_primary_auditor_will_be_frozen_before_formal_test':True})
    log=root/'logs/tsc_revision_r4';log.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/'scripts/run_tsc_revision_r4_development_pilot.sh',log/'development_pilot_snapshot_v1.sh')
    print(json.dumps(result))


if __name__=='__main__':main()
