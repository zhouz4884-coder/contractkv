"""Package completed raw evidence, excluding caches/weights; no experiment rerun."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

STUDY='results/tsc_task_faithful_open_arrival_20261018'
PART_BYTES=64*1024*1024


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(8<<20),b''):value.update(block)
    return value.hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    with path.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2);handle.write('\n')


def main(root):
    study=root/STUDY;out=study/'evidence_package_v1';assert not out.exists()
    for phase in ('baseline','profiles'):
        assert read(study/'calibration'/f'{phase}_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
        assert read(study/'calibration'/f'{phase}_exit_v1.json')['returncode']==0
    for phase in ('qwen','cross','gate'):
        assert read(study/'formal'/f'{phase}_execution_state_v1.json')['status']=='COMPLETE_PENDING_ANALYSIS'
        assert read(study/'formal'/f'{phase}_exit_v1.json')['returncode']==0
    assert read(study/'calibration_analysis_v1/summary_v1.json')['complete_cells']==7
    formal=read(study/'formal_analysis_v1/summary_v1.json');assert formal['complete_cells']==30
    sensitivity=read(study/'formal_goodput_source_sensitivity_v1.json')
    assert sensitivity['seed']==202610182002 and sensitivity['draws']==10000 and len(sensitivity['results'])==5
    integrity=read(study/'post_execution_integrity_v1.json')
    assert integrity['all_checked_frozen_sources_and_runtime_match'] and integrity['execution_cells']==37
    assert formal['measured_business_requests']==10800
    assert all(read(p/'completion_v1.json')['status']=='complete' for p in (study/'formal/cells').iterdir())
    selected=[]
    for path in study.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        rel=path.relative_to(study)
        if any(part in {'cache','tmp','CPU_tmp','.source_import_tmp','__pycache__','evidence_package_v1'} for part in rel.parts):continue
        if path.suffix.lower() not in {'.json','.jsonl','.py','.csv','.log','.md','.txt','.sh'} and rel.parts[0]!='preformal_infrastructure_versions_v1':continue
        selected.append(path)
    selected += sorted((root/'scripts').glob('tsc_revision_final_*.py'))
    cpu=root/'results/tsc_final_existing_evidence_CPU_20261018'
    assert read(cpu/'raw_order_v1/summary_v1.json')['requests']==3750
    for path in cpu.rglob('*'):
        if path.is_file() and not path.is_symlink() and (path.suffix.lower() in {'.json','.jsonl','.csv','.md','.py','.jinja2'} or path.name=='LICENSE'):
            selected.append(path)
    selected += [root/'docs/tsc_revision_final_strengthening_objective_20261018.md',
        root/'docs/tsc_revision_final_serving_calibration_design_20261018_zh.md',root/'docs/tsc_revision_GPU_execution_decisions_20261018_zh.md']
    selected=sorted(set(selected))
    records=[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in selected]
    out.mkdir();inventory=out/'raw_member_inventory_v1.json';write(inventory,dict(members=records,files=len(records),
        model_weights_and_runtime_caches_excluded=True,parent_model_runtime_proof='Original core preflight_v3 receipt and separately archived core raw evidence'))
    archive=out/'faithful_serving_raw_evidence_v1.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
        for row,path in zip(records,selected):
            assert sha(path)==row['sha256'] and path.stat().st_size==row['bytes'],'Input changed during package'
            info=tarfile.TarInfo(row['path']);info.size=row['bytes'];info.mtime=0;info.mode=0o644
            with path.open('rb') as handle:tar.addfile(info,handle)
    observed={}
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            assert member.isfile() and member.name not in observed and not member.name.startswith('/') and '..' not in Path(member.name).parts
            handle=tar.extractfile(member);value=hashlib.sha256();size=0
            for block in iter(lambda:handle.read(8<<20),b''):value.update(block);size+=len(block)
            observed[member.name]=dict(bytes=size,sha256=value.hexdigest())
    assert observed=={row['path']:dict(bytes=row['bytes'],sha256=row['sha256']) for row in records}
    parts=[]
    with archive.open('rb') as source:
        number=0
        while True:
            data=source.read(PART_BYTES)
            if not data:break
            path=out/f'{archive.name}.part{number:03d}'
            with path.open('xb') as handle:handle.write(data)
            parts.append(dict(path=path.name,bytes=len(data),sha256=sha(path)));number+=1
    write(out/'package_receipt_v1.json',dict(archive=archive.name,sha256=sha(archive),bytes=archive.stat().st_size,
        regular_members=len(records),member_inventory_sha256=sha(inventory),parts=parts,
        round_trip_member_bytes_verified=True,all_old_results_preserved=True))
    print(json.dumps(read(out/'package_receipt_v1.json')))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();main(args.root.resolve())
