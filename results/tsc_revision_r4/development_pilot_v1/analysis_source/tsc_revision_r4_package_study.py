"""Seal a completed serving/long study with current, snapshot and ownership audits."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import csv

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--study',choices=('diagnosis_v1','development_pilot_v1','clock_smoke_v1','validation_closed_v1','validation_arrival_v1'),required=True);a=p.parse_args()
    root=a.root.resolve();base=root/'results/tsc_revision_r4'/a.study
    proof=json.loads((base/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not proof['execution_complete']:raise ValueError('All expected actual cells and audits must complete')
    archive=base/(a.study+'_raw_evidence_v1.tar.gz')
    if archive.exists():raise ValueError('Preserve sealed archive')
    freeze=json.loads((base/'freeze.json').read_text(encoding='utf-8'))
    for r in freeze['files']:
        if sha(root/r['path'])!=r['sha256'] or sha(base/'source_snapshot'/r['path'])!=r['sha256']:raise ValueError('Frozen source drift: '+r['path'])
    dispatch_count=0
    if (base/'execution_dispatch_freeze_v1.json').exists():
        dispatch=json.loads((base/'execution_dispatch_freeze_v1.json').read_text(encoding='utf-8'))
        if dispatch['primary_freeze_sha256']!=sha(base/'freeze.json'):raise ValueError('Dispatch primary freeze mismatch')
        for item in dispatch['files']:
            if sha(root/item['path'])!=item['sha256'] or sha(base/item['snapshot'])!=item['sha256']:raise ValueError('Dispatch source drift')
        dispatch_count=len(dispatch['files'])
    post=root/'results/tsc_revision_r4'/('post_'+a.study+'_original_freeze_audit_v1.json')
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_freeze_audit.py'),'--root',str(root),'--output',str(post)],check=True)
    prefix={'diagnosis_v1':'diagnosis_','development_pilot_v1':'pilot_','clock_smoke_v1':'clock_',
            'validation_closed_v1':'closed_','validation_arrival_v1':'arrival_'}[a.study]
    logs=list((root/'logs/tsc_revision_r4').glob(prefix+'*_server.log'))
    logs+=list((root/'logs/tsc_revision_r4').glob(a.study+'*'))
    if a.study in ('validation_closed_v1','validation_arrival_v1'):logs.append(root/'logs/tsc_revision_r4/validation_v1.log')
    snapshots={'diagnosis_v1':'diagnosis_snapshot_v1.sh','development_pilot_v1':'development_pilot_snapshot_v1.sh',
               'clock_smoke_v1':'clock_smoke_snapshot_v1.sh','validation_closed_v1':'validation_snapshot_v1.sh','validation_arrival_v1':'validation_snapshot_v1.sh'}
    logs.append(root/'logs/tsc_revision_r4'/snapshots[a.study])
    owned=set();pattern=re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    for path in logs:
        if path.exists():
            for line in path.open(errors='replace'):
                match=pattern.search(line)
                if match:owned.add(int(match.group(1)))
    resident={int(x) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split() if x.isdigit()}
    if owned&resident:raise RuntimeError('Owned GPU workers remain resident')
    closure={'timestamp':datetime.now(timezone.utc).isoformat(),'frozen_current_and_snapshot_files':len(freeze['files']),'additional_dispatch_frozen_files':dispatch_count,'owned_resident_gpu_pids':sorted(owned&resident),'other_resident_gpu_pids_untouched':sorted(resident-owned),'no_process_stopped_by_packager':True,'experiment_execution_complete_scientific_success_separate':True}
    (base/'closure_v1.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    code=base/'analysis_source';code.mkdir(exist_ok=True)
    names=['tsc_revision_r4_package_study.py','tsc_revision_verify_archive.py','tsc_revision_split_raw_archive.py']
    names+=(['tsc_revision_r4_known_summary.py'] if a.study=='diagnosis_v1' else
            ['tsc_revision_r4_live_summary.py','tsc_revision_r4_audit_cell.py','tsc_revision_r4_strata_calibration.py',
             'tsc_revision_r4_arrival_protocol.py','tsc_revision_r2_tail_bootstrap.py'])
    names+=['tsc_revision_r2_margin_smoke.py','tsc_revision_r2_margin_policy.py']
    for name in names:shutil.copyfile(root/'scripts'/name,code/name)
    files=[p for p in base.rglob('*') if p.is_file() and 'progress_analysis' not in p.relative_to(base).parts and not p.name.endswith(('.pid','.partial','.tar.gz')) and '.tar.gz.part' not in p.name and not p.name.startswith('raw_evidence_')]
    files+=logs+[post,root/'third_party/licenses/vllm-Apache-2.0.txt',root/'third_party/licenses/README.md']
    inventory=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(x for x in files if x.is_file()))]
    with (base/'raw_evidence_inventory_v1.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','bytes','sha256'));writer.writeheader();writer.writerows(inventory)
    with tarfile.open(archive,'w:gz',compresslevel=6) as out:
        for item in inventory:out.add(root/item['path'],arcname=item['path'],recursive=False)
    result={'schema_version':'tsc-r4.complete-study-archive.v1','archive':archive.name,'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'member_files':len(inventory),'study':a.study,'cases':proof['cases'],'experimental_execution_complete_scientific_success_separate':True,'actual_prompt_output_ids_requests_metrics_runtime_source_and_analysis_included':True}
    (base/'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
