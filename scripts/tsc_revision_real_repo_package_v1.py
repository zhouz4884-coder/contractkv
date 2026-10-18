"""Archive all three real-source private diagnostic cells."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')


def main(root):
    study=root/'results/tsc_real_repobench_mechanism_20261018';base=root/'results/tsc_revision_mechanism_controls_20261018'
    state=read(study/'execution_state_v1.json')
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==3
    assert read(study/'formal_execution_v1_exit.json')['returncode']==0
    assert read(study/'analysis_v1/summary_v1.json')['status']=='complete'
    for x in read(study/'freeze_v1.json')['source_files']:assert sha(root/x['path'])==x['sha256']
    business=[]
    for rel in state['completed_cells']:
        cell=study/rel;done=read(cell/'completion_v1.json');assert done['counts']['business']==24
        for x in done['files']:assert sha(cell/x['path'])==x['sha256']
        business.extend(json.loads(line) for line in (cell/'responses.jsonl').read_text().splitlines() if json.loads(line)['event']=='business')
    assert len(business)==72
    grouped={}
    for row in business:
        condition=row['condition'];value=grouped.setdefault(condition,dict(requests=0,success=0,stop=0,length=0,max_actual_output_tokens=0))
        response=row['response'];value['requests']+=1;value['success']+=response['success']
        value['stop']+=response['finish_reason']=='stop';value['length']+=response['finish_reason']=='length'
        value['max_actual_output_tokens']=max(value['max_actual_output_tokens'],len(response['output_token_ids']))
    write(study/'actual_termination_by_condition_v1.json',dict(conditions=grouped,all_business_requests=72,
        all_natural_stop=sum(x['stop'] for x in grouped.values()),maximum_output_budget=384))
    code=study/'postprocessing_source_v1';code.mkdir()
    names=[p.name for p in (root/'scripts').glob('tsc_revision_real_repo_*v1.py')]
    names+=['tsc_revision_incomplete_reference_fix_v5.py','tsc_revision_verify_archive.py','tsc_revision_split_raw_archive.py']
    for name in sorted(set(names)):
        with (code/name).open('xb') as f:f.write((root/'scripts'/name).read_bytes())
    write(study/'parent_core_archive_reference_v1.json',dict(parent_archive_sha256=read(base/'raw_evidence_archive_manifest_v1.json')['archive_sha256'],
        parent_preflight_receipt_sha256=sha(base/'preflight_v3/receipt_v1.json'),source_snapshot_and_backend_proofs_in_parent=True,
        no_model_runtime_or_tokenizer_copy_repeated=True))
    archive=study/'real_repo_raw_evidence_v1.tar.gz';assert not archive.exists()
    forbidden={'cache','tmp','launcher_tmp','launcher_cache','preflight_v3','__pycache__'}
    selected=[]
    for directory,dirs,files in os.walk(study,followlinks=False):
        dirs[:]=[x for x in dirs if x not in forbidden]
        for name in files:
            p=Path(directory)/name
            if name.endswith(('.pyc','.lock','.tar.gz')) or '.tar.gz.part' in name or name.startswith('raw_evidence_'):continue
            assert stat.S_ISREG(p.lstat().st_mode) and not p.is_symlink()
            selected.append(p)
    entries=[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)]
    with (study/'raw_evidence_inventory_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','bytes','sha256']);w.writeheader();w.writerows(entries)
    with tarfile.open(archive,'x:gz',compresslevel=6) as tar:
        for row in entries:
            path=root/row['path'];info=tarfile.TarInfo(row['path']);info.size=row['bytes'];info.mode=0o644;info.mtime=int(path.stat().st_mtime)
            with path.open('rb') as f:tar.addfile(info,f)
    report=dict(schema_version='contractkv.real-repo-archive.v1',archive=archive.name,archive_sha256=sha(archive),
        archive_bytes=archive.stat().st_size,member_files=len(entries),uncompressed_bytes=sum(x['bytes'] for x in entries),
        fresh_model_conditions=3,business_generations=72,production_inherited_family_eligibility_unchanged=True,
        no_automatic_budget_escalation=True,no_model_weights_binaries_or_credentials=True,source_sha256=sha(Path(__file__)))
    write(study/'raw_evidence_archive_manifest_v1.json',report);print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
