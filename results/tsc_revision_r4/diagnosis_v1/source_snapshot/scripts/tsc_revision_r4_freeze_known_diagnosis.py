"""Freeze known-case controls and the independent input commitment before GPU use."""
import argparse
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
    base=root/'results/tsc_revision_r4/diagnosis_v1';protocol=root/'configs/tsc_revision_r4_known_diagnosis_v1.json'
    parent=json.loads((root/'results/tsc_revision_r3/validation_v1/freeze.json').read_text(encoding='utf-8'))
    files={r['path'] for r in parent['files']}
    files.update(('scripts/tsc_revision_r4_known_diagnosis.py','scripts/tsc_revision_r4_prepare_known_case.py',
                  'scripts/tsc_revision_r4_freeze_inputs.py','scripts/tsc_revision_r4_freeze_known_diagnosis.py',
                  'scripts/tsc_revision_r4_diagnose_prior.py','scripts/run_tsc_revision_r4_known_diagnosis.sh',
                  'configs/tsc_revision_r4_known_diagnosis_v1.json','results/tsc_revision_r4/model_registry_v1.json',
                  'results/tsc_revision_r4/environment_preflight_v1.json','results/tsc_revision_r4/phase2_integrity_preflight_v1.json',
                  'results/tsc_revision_r4/known_case_v1/sessions.jsonl','results/tsc_revision_r4/known_case_v1/actual_prompt_ids_v1.json',
                  'results/tsc_revision_r4/inputs/input_commitment_v1.json','results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl',
                  'results/tsc_revision_r4/inputs/heldout_fanout_v1.jsonl'))
    inputs=json.loads((root/'results/tsc_revision_r4/inputs/input_commitment_v1.json').read_text(encoding='utf-8'))
    if inputs['excluded_sources']!=462 or inputs['selection_uses_model_outputs_or_scores']:raise ValueError('New source split')
    for name,item in inputs['cohorts'].items():
        if sha(root/'results/tsc_revision_r4/inputs'/name)!=item['sha256']:raise ValueError('Sealed input mismatch')
    result=freeze_scope(root,base,protocol,files,{'selected_known_failure_not_unseen_validation':True,
                         'all_prior_sources_unchanged':True,'new50_excludes462_inputs_frozen_before_first_phase3_forward':True})
    logs=root/'logs/tsc_revision_r4';logs.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/'scripts/run_tsc_revision_r4_known_diagnosis.sh',logs/'diagnosis_snapshot_v1.sh')
    print(json.dumps(result))


if __name__=='__main__':main()
