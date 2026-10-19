"""Portable original records plus executable sources; no model/runtime copies."""
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

def main(root,model):
    study=root/STUDY;assert read(study/'development_exit_qwen_v4.json')['returncode']==0
    assert read(study/f'analysis_{model}_v4/summary_v2.json')['generations']==52
    out=study/f'evidence_{model}_v5';out.mkdir();selected={}
    for p in study.rglob('*'):
        rel=p.relative_to(study)
        if any(x in {'cache','tmp','CPU_tmp','preflight_v3','__pycache__'} or x.startswith('evidence_') for x in rel.parts):continue
        if not p.is_file() or p.is_symlink() or p.suffix=='.pyc' or p.name.startswith('postprocessing_'):continue
        # Only completed cells belong in this archive. Later optional jobs
        # cannot be launched before this package's independent local audit.
        if rel.parts[0]=='cells' and model+'_r1' not in rel.parts:continue
        selected[p.relative_to(root).as_posix()]=p
    for p in (study/'CPU_tmp').glob('*'):
        if p.is_file() and p.suffix in {'.log','.jsonl'} and not p.name.startswith('postprocessing_'):
            selected[p.relative_to(root).as_posix()]=p
    freeze=read(study/'development_freeze_v4/freeze.json')
    for r in freeze['files']:
        p=root/r['path'];assert sha(p)==r['sha256'];selected[r['path']]=p
    for name in ['tsc_template_task_development_analysis_v2.py','tsc_template_task_package_development_v5.py','tsc_template_task_postprocess_development_v4.py']:
        selected['scripts/'+name]=root/'scripts'/name
    inventory=[dict(path=k,bytes=p.stat().st_size,sha256=sha(p)) for k,p in sorted(selected.items())]
    write(out/'inventory_v5.json',dict(members=inventory,files=len(inventory)))
    archive=out/'task_template_development_raw_v5.tar.gz'
    with tarfile.open(archive,'x:gz') as tar:
        for name,p in sorted(selected.items()):tar.add(p,arcname=name,recursive=False)
    with tarfile.open(archive,'r:gz') as tar:
        expected={r['path']:r for r in inventory};assert len(tar.getmembers())==len(expected)
        for m in tar.getmembers():assert m.isfile() and hashlib.sha256(tar.extractfile(m).read()).hexdigest()==expected[m.name]['sha256']
    parts=[]
    with archive.open('rb') as f:
        i=0
        for data in iter(lambda:f.read(32<<20),b''):
            p=out/(archive.name+f'.part{i:03d}')
            with p.open('xb') as t:t.write(data)
            parts.append(dict(path=p.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()));i+=1
    receipt=dict(archive=archive.name,sha256=sha(archive),bytes=archive.stat().st_size,regular_members=len(inventory),
        parts=parts,inventory_sha256=sha(out/'inventory_v5.json'),roundtrip_all_members_verified=True,model=model,generations=52,
        startup_failure_with_zero_outputs_preserved=True,no_model_or_runtime_copied=True,source_sha256=sha(Path(__file__)))
    write(out/'package_receipt_v5.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--model',required=True)
    a=p.parse_args();main(a.root.resolve(),a.model)
