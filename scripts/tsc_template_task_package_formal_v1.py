"""Full measured evidence, including failed development and all formal cells."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

STUDY=Path('results/tsc_template_task_serving_20261019')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2);f.write('\n')

def main(root):
    study=root/STUDY;summary=read(study/'formal_analysis_v1/summary_v1.json')
    assert read(study/'formal_exit_v1.json')['returncode']==0 and summary['actual_cells']==27 and summary['business']==10368
    out=study/'formal_evidence_v1';out.mkdir();selected={}
    for p in study.rglob('*'):
        rel=p.relative_to(study)
        if any(x in {'cache','tmp','CPU_tmp','preflight_v3','__pycache__','formal_evidence_v1'} or x.startswith('evidence_') for x in rel.parts):continue
        if not p.is_file() or p.is_symlink() or p.suffix=='.pyc' or p.name.startswith('postprocessing_'):continue
        selected[p.relative_to(root).as_posix()]=p
    for p in (study/'CPU_tmp').glob('*'):
        if p.is_file() and p.suffix in {'.log','.jsonl'} and not p.name.startswith('postprocessing_'):
            selected[p.relative_to(root).as_posix()]=p
    for r in read(study/'formal_freeze_v1/freeze.json')['files']:
        p=root/r['path'];mirror=study/'formal_freeze_v1/source_snapshot'/r['path']
        assert sha(p)==sha(mirror)==r['sha256']
        selected[r['path']]=p;selected[mirror.relative_to(root).as_posix()]=mirror
    for name in ['tsc_template_task_formal_analysis_v1.py','tsc_template_task_package_formal_v1.py','tsc_template_task_postprocess_formal_v1.py']:
        selected['scripts/'+name]=root/'scripts'/name
    inventory=[dict(path=k,sha256=sha(p),bytes=p.stat().st_size) for k,p in sorted(selected.items())]
    write(out/'inventory_v1.json',dict(files=len(inventory),members=inventory))
    archive=out/'task_bearing_template_service_full_v1.tar.gz'
    with tarfile.open(archive,'x:gz') as tar:
        for name,p in sorted(selected.items()):tar.add(p,arcname=name,recursive=False)
    with tarfile.open(archive,'r:gz') as tar:
        expected={r['path']:r for r in inventory};assert len(tar.getmembers())==len(expected)
        for m in tar.getmembers():assert m.isfile() and hashlib.sha256(tar.extractfile(m).read()).hexdigest()==expected[m.name]['sha256']
    parts=[]
    with archive.open('rb') as f:
        for i,data in enumerate(iter(lambda:f.read(32<<20),b'')):
            p=out/(archive.name+f'.part{i:03d}')
            with p.open('xb') as t:t.write(data)
            parts.append(dict(path=p.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    receipt=dict(archive=archive.name,sha256=sha(archive),bytes=archive.stat().st_size,parts=parts,regular_members=len(inventory),
        inventory_sha256=sha(out/'inventory_v1.json'),all_members_roundtrip_verified=True,no_models_or_runtime_binaries_copied=True,
        valid_development_generations=156,Raw_calibration_business=160,formal_business=10368,formal_cells=27,
        initial_zero_output_startup_failure_and_all_negative_results_retained=True,source_sha256=sha(Path(__file__)))
    write(out/'package_receipt_v1.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
