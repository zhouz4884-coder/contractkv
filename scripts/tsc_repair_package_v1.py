"""Package immutable repair evidence and byte-exact executable source mirrors."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

STUDY=Path('results/tsc_authorization_task_repair_20261019')
PARENT=Path('results/tsc_revision_mechanism_controls_20261018')


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2);f.write('\n')


def main(root):
    study=root/STUDY;assert read(study/'execution_state_v2.json')['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS'
    assert read(study/'worker_exit_v2.json')['returncode']==0
    assert read(study/'analysis_v1/summary_v1.json')['business_requests']==828
    output=study/'evidence_package_v1';output.mkdir()
    selected={}
    for p in study.rglob('*'):
        rel=p.relative_to(study)
        if any(part in {'cache','tmp','preflight_v3','evidence_package_v1','CPU_tmp','__pycache__'} for part in rel.parts):continue
        if not p.is_file() or p.is_symlink() or p.suffix=='.pyc':continue
        if p.name in {'deployment_transport_v2.tar.gz','postprocess_v1.log'}:continue
        selected[p.relative_to(root).as_posix()]=p
    projection=[]
    for p in (study/'source_snapshot_v2/scripts').rglob('*'):
        if not p.is_file() or p.suffix=='.pyc':continue
        rel=p.relative_to(study/'source_snapshot_v2').as_posix()
        if rel in selected:assert sha(selected[rel])==sha(p)
        else:selected[rel]=p
        projection.append(dict(archive_path=rel,executed_snapshot_path=p.relative_to(root).as_posix(),sha256=sha(p)))
    freeze=read(study/'freeze_v2.json')
    for row in freeze['files']:
        p=root/row['path'];assert sha(p)==row['sha256']
        if row['path'] in selected:assert sha(selected[row['path']])==row['sha256']
        else:selected[row['path']]=p
    for name in ['tsc_repair_analyze_v1.py','tsc_repair_marker_positions_v1.py','tsc_repair_package_v1.py','tsc_repair_postprocess_v1.py','tsc_repair_launch_v2.py']:
        selected['scripts/'+name]=root/'scripts'/name
    for p in (root/PARENT/'preflight_v3').glob('*.json'):
        selected[p.relative_to(root).as_posix()]=p
    projection_path=study/'archive_source_projection_v1.json'
    write(projection_path,dict(byte_exact_source_mirrors=projection,
        reason='Expose the actual executed source_snapshot scripts at importable root paths for offline recomputation; preserve both originals. No Prompt/Output IDs or timing reconstructed.',new_GPU_requests=0))
    selected[projection_path.relative_to(root).as_posix()]=projection_path
    inventory=[dict(path=name,bytes=p.stat().st_size,sha256=sha(p)) for name,p in sorted(selected.items())]
    write(output/'inventory_v1.json',dict(files=len(inventory),members=inventory,all_raw_logs_and_pre_GPU_versions_retained=True,
        original_frozen_files=len(freeze['files']),all_original_frozen_files_included=True))
    archive=output/'authorization_repair_raw_v1.tar.gz'
    with tarfile.open(archive,'x:gz') as tar:
        for name,p in sorted(selected.items()):tar.add(p,arcname=name,recursive=False)
    with tarfile.open(archive,'r:gz') as tar:
        mm=tar.getmembers();assert len(mm)==len(inventory)
        expected={x['path']:x for x in inventory}
        for m in mm:
            assert m.isfile() and m.name in expected
            assert hashlib.sha256(tar.extractfile(m).read()).hexdigest()==expected[m.name]['sha256']
    parts=[]
    with archive.open('rb') as f:
        n=0
        while True:
            data=f.read(32<<20)
            if not data:break
            p=output/(archive.name+f'.part{n:03d}')
            with p.open('xb') as w:w.write(data)
            parts.append(dict(path=p.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()));n+=1
    receipt=dict(archive=archive.name,sha256=sha(archive),bytes=archive.stat().st_size,regular_members=len(inventory),
        inventory_sha256=sha(output/'inventory_v1.json'),parts=parts,member_roundtrip_bytes_verified=True,
        frozen_root_dependencies=len(freeze['files']),all_frozen_dependencies_included=True,
        source_sha256=sha(Path(__file__)),no_models_or_runtime_cache_copied=True)
    write(output/'package_receipt_v1.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root.resolve())
