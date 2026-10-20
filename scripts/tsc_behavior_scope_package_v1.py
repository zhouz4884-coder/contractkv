"""Hash and archive completed raw evidence without caches/models/runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
STUDY=Path('results/tsc_behavior_scope_repair_20261020')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main(root,label):
    study=root/STUDY;names=set()
    for phase in ['development','validation']:
        freeze=study/(phase+'_freeze_v4/freeze.json')
        if not freeze.exists():continue
        state=json.loads((study/(phase+'_execution_state_v4.json')).read_text())
        assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS'
        assert json.loads((study/(phase+'_exit_v4.json')).read_text())['returncode']==0
        names.add(freeze.relative_to(root).as_posix())
        for r in json.loads(freeze.read_text())['files']:
            p=root/r['path'];assert sha(p)==r['sha256'];names.add(r['path'])
    for directory,dirs,files in os.walk(study,topdown=True,followlinks=False):
        dirs[:]=[x for x in dirs if x not in ['source_snapshot','cache','tmp'] and not x.startswith(('development_freeze_','validation_freeze_','evidence_'))]
        for name in files:
            p=Path(directory)/name
            if p.is_file() and not p.is_symlink() and p.suffix in ['.json','.jsonl','.log']:names.add(p.relative_to(root).as_posix())
    assert names
    inventory=[dict(path=n,bytes=(root/n).stat().st_size,sha256=sha(root/n)) for n in sorted(names)]
    out=study/('evidence_'+label+'_v1');out.mkdir()
    with (out/'inventory_v1.json').open('x') as f:json.dump(inventory,f,indent=2);f.write('\n')
    archive=out/(label+'_raw_evidence_v1.tar.gz')
    with tarfile.open(archive,'x:gz',compresslevel=6) as tar:
        for item in inventory:tar.add(root/item['path'],arcname=item['path'],recursive=False)
    # Independent archive readback of every original member.
    with tarfile.open(archive,'r:gz') as tar:
        assert len(tar.getmembers())==len(inventory)
        for item,member in zip(inventory,tar.getmembers()):
            assert member.name==item['path'] and member.isfile()
            assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==item['sha256']
    receipt=dict(status='PASS',archive=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),
                 members=len(inventory),inventory_sha256=sha(out/'inventory_v1.json'),archive_readback_all_members=True,
                 excludes_models_caches_and_runtime=True,source_sha256=sha(Path(__file__)))
    with (out/'receipt_v1.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--label',choices=['development','all'],required=True)
    a=p.parse_args();main(a.root.resolve(),a.label)
