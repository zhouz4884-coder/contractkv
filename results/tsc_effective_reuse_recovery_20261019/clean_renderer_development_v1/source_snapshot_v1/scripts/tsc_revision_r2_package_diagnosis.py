"""Seal the first development diagnostic, including its original join failure."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args()
    root=a.root.resolve(); base=root/'results/tsc_revision_r2/diagnosis_v1'
    audit=json.loads((base/'analysis_v2/completion_audit_v2.json').read_text())
    if not audit['execution_complete']: raise ValueError('Additional exact-ID/count audit required')
    archive=base/'r2_diagnosis_raw_evidence_v1.tar.gz'
    if archive.exists(): raise ValueError('Preserve the existing archive')
    declaration=json.loads((base/'freeze.json').read_text())
    for item in declaration['files']:
        if sha(root/item['path'])!=item['sha256'] or sha(base/'source_snapshot'/item['path'])!=item['sha256']:
            raise ValueError('Frozen file changed: '+item['path'])
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_freeze_audit.py'),'--root',str(root),
                    '--output',str(root/'results/tsc_revision_r2/post_diagnosis_original_freeze_audit_v1.json')],check=True)
    logs=root/'logs/tsc_revision_r2'; owned=set()
    pattern=re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    for path in logs.glob('diagnosis_*_server.log'):
        for line in path.open(errors='replace'):
            match=pattern.search(line)
            if match: owned.add(int(match.group(1)))
    resident={int(x) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split() if x.isdigit()}
    if owned&resident: raise RuntimeError('Owned diagnostic GPU worker remains resident')
    record={'timestamp':datetime.now(timezone.utc).isoformat(),'all_30_current_and_snapshot_files_match':True,
            'owned_resident_gpu_pids':sorted(owned&resident),'other_resident_gpu_pids_untouched':sorted(resident-owned),
            'no_processes_stopped_by_this_audit':True,'original_driver_join_failure_and_missing_marker_retained':True,
            'additional_exact_engine_ID_audit_complete':True,'no_scientific_success_inferred_from_hashes':True}
    (base/'closure_v1.json').write_text(json.dumps(record,indent=2)+'\n')
    code=base/'analysis_source'; code.mkdir(exist_ok=True)
    for name in ('tsc_revision_r2_diagnose_summary.py','tsc_revision_r2_package_diagnosis.py','tsc_revision_verify_archive.py','tsc_revision_split_raw_archive.py'):
        shutil.copyfile(root/'scripts'/name,code/name)
    files=[x for x in base.rglob('*') if x.is_file() and not x.name.endswith(('.pid','.partial','.tar.gz'))
           and not x.name.startswith('raw_evidence_') and '.tar.gz.part' not in x.name]
    files+=list(logs.glob('diagnosis*'))
    files+=[root/'results/tsc_revision_r2/pre_original_freeze_audit_v1.json',
            root/'results/tsc_revision_r2/post_diagnosis_original_freeze_audit_v1.json',
            root/'third_party/licenses/vllm-Apache-2.0.txt',root/'third_party/licenses/README.md']
    files=sorted(set(x for x in files if x.is_file()))
    inventory=[{'path':x.relative_to(root).as_posix(),'bytes':x.stat().st_size,'sha256':sha(x)} for x in files]
    with (base/'raw_evidence_inventory_v1.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','bytes','sha256')); writer.writeheader(); writer.writerows(inventory)
    with tarfile.open(archive,'w:gz',compresslevel=6) as target:
        for item in inventory: target.add(root/item['path'],arcname=item['path'],recursive=False)
    manifest={'schema_version':'tsc-r2.development-diagnostic-archive.v1','archive':archive.name,'archive_sha256':sha(archive),
              'archive_bytes':archive.stat().st_size,'member_files':len(inventory),'free_generations':48,
              'full_logprob_requests_with_one_continuation':42,'internal_verification_requests':30,
              'postexecution_exact_engine_metric_joins':120,'frozen_driver_completion_false_preserved':True,
              'selected_development_cases_not_heldout':True,'performance_claim':False}
    (base/'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))


if __name__=='__main__': main()
