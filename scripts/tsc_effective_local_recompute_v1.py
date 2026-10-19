"""Safely restore the raw development package and rerun its exact accounting on CPU."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import time

STUDY=Path('results/tsc_effective_reuse_recovery_20261019')


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def safe(name):
    p=PurePosixPath(name)
    assert name and not p.is_absolute() and '\\' not in name and ':' not in name and '..' not in p.parts
    assert p.as_posix()==name and p.parts[0] in {'scripts','configs','docs','results','tests'}
    reserved={'CON','PRN','AUX','NUL'}|{f'{prefix}{i}' for prefix in ('COM','LPT') for i in range(1,10)}
    assert not any(part.split('.')[0].upper() in reserved or part.endswith((' ','.')) for part in p.parts)
    return p


def main(args):
    workspace=args.workspace.resolve();package=args.package.resolve();restore=args.restore.resolve()
    archive=args.archive.resolve();records=workspace/STUDY
    assert restore.is_relative_to(workspace) and archive.is_relative_to(workspace)
    assert not restore.exists() and not (records/'local_independent_recompute_v1.json').exists()
    receipt=read(package/'package_receipt_v1.json');inventory=read(package/'inventory_v1.json')
    assert sha(package/'inventory_v1.json')==receipt['inventory_sha256']
    expected={r['path']:r for r in inventory['members']}
    assert len(expected)==len(inventory['members'])==receipt['regular_members']
    for name in expected:safe(name)
    for row in receipt['parts']:
        assert Path(row['path']).name==row['path']
        p=package/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    assert sum(row['bytes'] for row in receipt['parts'])==receipt['bytes']
    archive.parent.mkdir(parents=True,exist_ok=True)
    if archive.exists():assert sha(archive)==receipt['sha256']
    else:
        with archive.open('xb') as output:
            for row in receipt['parts']:
                p=package/row['path']
                with p.open('rb') as f:shutil.copyfileobj(f,output,8<<20)
    assert archive.stat().st_size==receipt['bytes'] and sha(archive)==receipt['sha256']
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        assert len(members)==len(expected) and {m.name for m in members}==set(expected)
        assert all(m.isfile() and m.size==expected[m.name]['bytes'] for m in members)
        restore.mkdir(parents=True)
        for m in members:
            path=restore.joinpath(*safe(m.name).parts);assert path.is_relative_to(restore)
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as out:shutil.copyfileobj(tar.extractfile(m),out,8<<20)
            assert sha(path)==expected[m.name]['sha256']
    study=restore/STUDY;freeze=read(study/'freeze_development_v2.json')
    assert len(freeze['files'])==1182
    for version in [1,2]:
        for row in read(study/f'freeze_development_v{version}.json')['files']:assert sha(restore/row['path'])==row['sha256']
    write(records/'local_archive_verification_v1.json',dict(status='PASS',archive_sha256=receipt['sha256'],
        archive_bytes=receipt['bytes'],regular_members=len(members),frozen_files=1182,
        safe_paths_and_no_overwrite_verified=True,new_GPU_requests=0,restore_root=str(restore)))
    source=restore/'scripts/tsc_effective_development_analysis_v1.py';target=study/'local_independent_analysis_v1'
    assert not target.exists()
    command=[sys.executable,'-B',str(source),'--root',str(restore),'--output',str(target)]
    started=time.time()
    with (records/'local_independent_console_v1.log').open('xb') as log:
        done=subprocess.run(command,cwd=restore,stdout=log,stderr=subprocess.STDOUT)
    write(records/'local_independent_execution_v1.json',dict(command=command,returncode=done.returncode,
        started_epoch_s=started,ended_epoch_s=time.time(),analysis_source_sha256=sha(source),new_GPU_requests=0))
    assert done.returncode==0,'Preserve failed independent execution; do not overwrite'
    before=read(study/'analysis_development_v1/summary_v1.json');after=read(target/'summary_v1.json')
    assert before==after,'Full summary differs; do not silently apply a numerical tolerance'
    files=[]
    for p in sorted((study/'analysis_development_v1').glob('*.csv')):
        q=target/p.name;assert p.read_bytes()==q.read_bytes(),p.name
        files.append(dict(file=p.name,sha256=sha(q),bytes=q.stat().st_size))
    assert len(files)==3
    for name,row in expected.items():assert sha(restore/name)==row['sha256']
    write(records/'local_independent_recompute_v1.json',dict(status='PASS',independently_recomputed_business=600,
        actual_cells=3,summary_all_values_exact=True,CSV_bytes_equal=files,
        original_archive_members_unchanged=len(expected),no_prompt_or_output_IDs_reconstructed=True,
        new_GPU_requests=0,source_sha256=sha(Path(__file__)),analysis_source_sha256=sha(source),
        archive_sha256=receipt['sha256'],formal_freeze_sha256=sha(study/'freeze_development_v2.json')))
    print(json.dumps(dict(status='PASS',business_requests=600,cells=3,CSV_files_exact=3,new_GPU_requests=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['workspace','package','restore','archive']:p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
