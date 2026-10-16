"""Freeze the independent matrix only after the full development pilot audit."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope
from scripts.tsc_revision_build_inputs import source

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    protocol=root/'configs/tsc_revision_r2_validation_v1.json';config=json.loads(protocol.read_text(encoding='utf-8'))
    base=root/'results/tsc_revision_r2/validation_v1'
    if (base/'freeze.json').exists():raise RuntimeError('Preserve independent matrix freeze')
    pilot=root/'results/tsc_revision_r2/development_pilot_v1/analysis/completion_audit_v1.json'
    completed=json.loads(pilot.read_text(encoding='utf-8'))
    if not completed['execution_complete'] or completed['complete_cells']!=18:raise ValueError('Complete pilot required before independent validation')
    comparisons=list(csv.DictReader((pilot.parent/'performance_comparison_v1.csv').open(encoding='utf-8',newline='')))
    quality=list(csv.DictReader((pilot.parent/'quality_summary_v1.csv').open(encoding='utf-8',newline='')))
    review={'schema_version':'tsc-r2.development-pilot-before-test-review.v1','complete_pilot_audit_sha256':sha(pilot),
        'policy_version_in_pilot':'v1 raw floor .03125, candidate .0625, factor1; retained development control',
        'policy_for_independent_validation':'v2 raw/candidate .0625, factor1; same levels/cost predictors, known-negative constraint before test',
        'quality_all_families':[r for r in quality if r['family']=='ALL'],'performance_comparison':comparisons,
        'pilot_weaknesses_not_removed':'Single development repeat, source dependence, possible cold/p99 weakness retained. V2 raises only the raw pointwise floor; complete independent results must determine its quality/economics.',
        'not_a_positive_serving_result_declaration':True,'new_heldout_outcomes_used':False}
    for filename,key in [('heldout_sealed_sessions_v1.jsonl','heldout_sessions_sha256'),('heldout_fanout_v1.jsonl','fanout_sessions_sha256')]:
        if sha(root/'results/tsc_revision_r2/inputs'/filename)!=config[key]:raise ValueError('Independent frozen input changed')
    inputs=root/'results/tsc_revision_r2/inputs';samples=[json.loads(x) for x in (inputs/'heldout_sealed_sessions_v1.jsonl').read_text(encoding='utf-8').splitlines()]
    groups={r['revision_source_group'] for r in samples}
    if len(groups)!=50 or set(Counter(s['revision_family'] for s in samples).values())!={10}:raise ValueError('Fixed five-family independent coverage')
    commitment=json.loads((inputs/'input_commitment_v1.json').read_text(encoding='utf-8'));excluded=set()
    for item in commitment['exclusion_files']:
        path=root/item['file']
        if sha(path)!=item['sha256']:raise ValueError('Prior exclusion source changed')
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            r=json.loads(line)
            excluded.add(source(r))
    if len(excluded)!=commitment['excluded_source_groups'] or hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest()!=commitment['excluded_source_set_sha256']:
        raise ValueError('Canonical prior-source exclusion commitment changed')
    development=[json.loads(x) for x in (inputs/'development_sessions_v1.jsonl').read_text(encoding='utf-8').splitlines()]
    if groups&excluded or groups&{r['revision_source_group'] for r in development}:raise ValueError('Independent explicit-source overlap')
    prior=json.loads((root/'results/tsc_revision_r2/long_format_v2/freeze.json').read_text(encoding='utf-8'))
    files={r['path'] for r in prior['files']}
    files.update(('configs/tsc_revision_r2_validation_v1.json','scripts/run_tsc_revision_r2_validation.sh',
      'scripts/tsc_revision_r2_live.py','scripts/tsc_revision_r2_live_v2.py','scripts/tsc_revision_r2_admission.py','scripts/tsc_revision_r2_freeze_validation.py',
      'scripts/tsc_revision_r2_make_fanout.py','results/tsc_revision_r2/inputs/heldout_sealed_sessions_v1.jsonl',
      'scripts/tsc_revision_r2_live_summary.py','scripts/tsc_revision_r2_tail_bootstrap.py',
      'results/tsc_revision_r2/inputs/heldout_fanout_v1.jsonl','results/tsc_revision_r2/inputs/heldout_fanout_v1.commitment.json',
      'results/tsc_revision_r2/profile_v1/analysis/selection_input_v1.json',
      'results/tsc_revision_r2/profile_v1/analysis/completion_audit_v1.json',
      'results/tsc_revision_r2/catalog_v2_remote_recheck_v1.json'))
    base.mkdir(parents=True,exist_ok=True)
    (base/'development_review_v1.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    assignment=[];index=0
    for study in config['studies']:
        for repeat in range(1,config['repeats']+1):
            for model in config['models']:
                for policy in config['policy_order'][str(repeat)]:assignment.append({'cell':f'{study}_{model}_{policy}_r{repeat}','gpu_lane':index%2})
                index+=1
    with (base/'launcher_gpu_assignment_v1.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=('cell','gpu_lane'));writer.writeheader();writer.writerows(assignment)
    if len(assignment)!=config['expected_cells']:raise ValueError('Matrix assignment count')
    files.update(('results/tsc_revision_r2/validation_v1/development_review_v1.json','results/tsc_revision_r2/validation_v1/launcher_gpu_assignment_v1.csv'))
    result=freeze_scope(root,base,protocol,files,{'independent_inputs_frozen_before_any_policy_selection':True,
      'new_heldout_outputs_not_used_in_selection':True,'pilot_complete_before_matrix_freeze':True,
      'source_exclusion_commitment_sha256':sha(inputs/'input_commitment_v1.json'),
      'catalog_sha256':sha(root/config['selected_catalog']),
      'gpu_snapshot_before_queued_launch':subprocess.check_output(['nvidia-smi','--query-gpu=index,name,uuid,memory.used,memory.total,driver_version','--format=csv'],text=True)})
    snapshot=root/'logs/tsc_revision_r2/validation_snapshot_v1.sh'
    if snapshot.exists():raise RuntimeError('Preserve launcher snapshot')
    shutil.copyfile(root/'scripts/run_tsc_revision_r2_validation.sh',snapshot);print(json.dumps(result))

if __name__=='__main__':main()
