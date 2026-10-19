"""Two additional paired development repeats for the two flagged tail cells."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();r4=root/'results/tsc_revision_r4'
 base=r4/'development_repeat_check_v1'
 if base.exists():raise ValueError('Preserve repeat check version')
 pilot=r4/'development_pilot_v1';audit=json.loads((pilot/'analysis/completion_audit_v1.json').read_text())
 if not audit['execution_complete']:raise ValueError('Original18 audit first')
 parent=json.loads((r4/'clock_smoke_v1/freeze.json').read_text())
 for r in parent['files']:
  if sha(root/r['path'])!=r['sha256']:raise ValueError('Parent source changed')
 config={'schema_version':'tsc-r4.development-repeat-check.v1','development_only':True,'profile':'balanced',
  'targets':[{'study':'single-session','model':'qwen'},{'study':'template-fanout','model':'mistral'}],
  'policies':['raw-order','risk-tail'],'new_repeats':[2,3],'expected_cells':8,'expected_actual_generations':2480,'expected_future_requests':2232,
  'input_files':json.loads((pilot/'freeze.json').read_text())['protocol']['input_files'],
  'studies':{'single-session':1,'template-fanout':10},'selected_catalog':'results/tsc_revision_r4/development_fit_v3/calibration_v1.json',
  'previous_catalog':'configs/tsc_revision_r3_catalog_v1.json','generation_protocol':'configs/tsc_revision_r1r_validation_protocol_v1.json',
  'clock':'Original closed-loop shared two-request waves, unchanged frozen149 client and balanced profile.',
  'purpose':'One-process source-only bootstrap showed Qcold+2.278ms and Mfan+25.976ms p99. Add exactly2 fresh paired process repeats, combine originalr1 withr2/r3; do not sample until significance changes.',
  'original_pilot_archive_sha256':json.loads((pilot/'raw_evidence_archive_manifest_v1.json').read_text())['archive_sha256'],
  'no_new50_model_forward':True,'policy_changed':False,'gpu_assignment':{'2':1,'3':0},
  'policy_order':{'2-single-session':['risk-tail','raw-order'],'2-template-fanout':['raw-order','risk-tail'],
                  '3-single-session':['raw-order','risk-tail'],'3-template-fanout':['risk-tail','raw-order']},
  'selection_rule':'Use combined paired source/repeat p99 interval for flagged conditions, not one-process source-only interval. Preserve point estimates and all regressions. New formal50 must remain unseen until selection.'}
 target=root/'configs/tsc_revision_r4_development_repeat_check_v1.json'
 with target.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(config,indent=2)+'\n')
 seeds={r['path'] for r in parent['files']}
 seeds.update([target.relative_to(root).as_posix(),'scripts/tsc_revision_r4_freeze_repeat_check.py','scripts/run_tsc_revision_r4_repeat_check.sh',
               'scripts/tsc_revision_r4_repeat_summary.py','scripts/tsc_revision_r4_audit_cell.py','scripts/tsc_revision_r4_live_summary.py'])
 print(json.dumps(freeze_scope(root,base,target,seeds,{'exactly_two_additional_development_repeats':True,'new50_model_outcomes_unused':True})))

if __name__=='__main__':main()
