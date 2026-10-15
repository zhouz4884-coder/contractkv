"""Seal a completed selected-case cache/batch control without changing older archives."""
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


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--study',choices=('warm_reuse_v1','batch_reuse_v1'),required=True); a=p.parse_args()
    root=a.root.resolve(); base=root/'results/tsc_revision_r2'/a.study; prefix=a.study.removesuffix('_v1')
    audit=json.loads((base/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']: raise ValueError('Complete actual-ID/cache intervention audit required')
    archive=base/(a.study+'_raw_evidence_v1.tar.gz')
    if archive.exists(): raise ValueError('Preserve immutable archive')
    declaration=json.loads((base/'freeze.json').read_text(encoding='utf-8'))
    for item in declaration['files']:
        if sha(root/item['path'])!=item['sha256'] or sha(base/'source_snapshot'/item['path'])!=item['sha256']:
            raise ValueError('Frozen generation source changed: '+item['path'])
    post=root/'results/tsc_revision_r2'/('post_'+a.study+'_original_freeze_audit_v1.json')
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_freeze_audit.py'),'--root',str(root),'--output',str(post)],check=True)
    logs=root/'logs/tsc_revision_r2'; owned=set()
    pattern=re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    for path in logs.glob(prefix+'*_server.log'):
        for line in path.open(errors='replace'):
            match=pattern.search(line)
            if match: owned.add(int(match.group(1)))
    resident={int(x) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split() if x.isdigit()}
    if resident&owned: raise RuntimeError('Owned GPU worker remains resident')
    closure={'timestamp':datetime.now(timezone.utc).isoformat(),'prospective_current_and_snapshot_checks':len(declaration['files']),
             'owned_resident_gpu_pids':sorted(resident&owned),'other_resident_gpu_pids_untouched':sorted(resident-owned),
             'all_count_identity_cache_audits_complete':True,'no_processes_stopped':True,'selected_development_not_heldout':True}
    (base/'closure_v1.json').write_text(json.dumps(closure,indent=2)+'\n',encoding='utf-8')
    code=base/'analysis_source'; code.mkdir(exist_ok=True)
    names=['tsc_revision_r2_warm_summary.py','tsc_revision_r2_package_control.py','tsc_revision_verify_archive.py','tsc_revision_split_raw_archive.py']
    if prefix=='batch_reuse': names.append('tsc_revision_r2_batch_summary.py')
    for name in names: shutil.copyfile(root/'scripts'/name,code/name)
    files=[x for x in base.rglob('*') if x.is_file() and not x.name.endswith(('.pid','.partial','.tar.gz'))
           and not x.name.startswith('raw_evidence_') and '.tar.gz.part' not in x.name]
    files+=list(logs.glob(prefix+'*'))
    files+=[post,root/'results/tsc_revision_r2'/('pre_'+prefix+'_original_freeze_audit_v1.json'),
            root/'third_party/licenses/vllm-Apache-2.0.txt',root/'third_party/licenses/README.md']
    files=sorted(set(x for x in files if x.is_file()))
    inventory=[{'path':x.relative_to(root).as_posix(),'bytes':x.stat().st_size,'sha256':sha(x)} for x in files]
    with (base/'raw_evidence_inventory_v1.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','bytes','sha256')); writer.writeheader(); writer.writerows(inventory)
    with tarfile.open(archive,'w:gz',compresslevel=6) as target:
        for item in inventory: target.add(root/item['path'],arcname=item['path'],recursive=False)
    manifest={'schema_version':'tsc-r2.selected-control-archive.v1','archive':archive.name,'archive_sha256':sha(archive),
              'archive_bytes':archive.stat().st_size,'member_files':len(files),'study':a.study,'cases':audit['cases'],
              'includes_actual_prompt_and_output_IDs_metrics_and_source_snapshots':True,'selected_development_not_heldout':True,
              'performance_claim':False}
    (base/'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__': main()
