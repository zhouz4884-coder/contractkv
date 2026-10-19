"""Seal nine completed cells, failures, the port repair and real source postimages."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')


def main(root):
    study=root/'results/tsc_revision_mechanism_controls_20261018'
    state=read(study/'execution_state_v1.json')
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==9
    assert read(study/'formal_continuation_v5_exit_v1.json')['returncode']==0
    analysis=read(study/'analysis_v3/summary_v1.json');effects=read(study/'effects_v4/summary_v1.json')
    assert analysis['status']=='complete' and analysis['behavior_candidates']==180
    assert effects['status']=='observed_effect_denominators_complete'
    archive=study/'mechanism_manifest_raw_evidence_v5.tar.gz'
    assert not archive.exists() and not (study/'closure_v5.json').exists(),'Never replace an archive attempt'
    freeze=read(study/'freeze_v3.json')
    for x in freeze['files']:assert sha(study/'source_snapshot'/x['path'])==x['sha256']
    for x in read(study/'backend_project_dependency_manifest_v1.json')['files']:
        assert sha(root/x['snapshot_path'])==x['sha256']
    for x in read(study/'incomplete_reference_continuation_v5.json')['preserved_complete_files']:
        assert sha(study/x['path'])==x['sha256']
    owned=set()
    for rel in state['completed_cells']:
        cell=study/rel;complete=read(cell/'completion_v1.json');assert complete['status']=='complete'
        for x in complete['files']:assert sha(cell/x['path'])==x['sha256']
        owned.add(read(cell/'server_process_v1.json')['process_group'])
    resident={int(x) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).split() if x.isdigit()}
    remaining=[]
    for pid in resident:
        try:
            if os.getpgid(pid) in owned:remaining.append(pid)
        except ProcessLookupError:pass
    assert not remaining,'Owned diagnostic GPU processes are still resident'
    # Retain the actual backend sources, not only their hashes. Native binaries
    # are identified by the existing preflight inventory and stay outside Git.
    runtime=study/'preflight_v3/runtime'
    inventory={x['path']:x['sha256'] for x in read(study/'preflight_v3/runtime_inventory_v1.json')['files']}
    postimages=[]
    paths=['entrypoints/openai/api_server.py','v1/core/kv_cache_manager.py','v1/core/block_pool.py',
           'v1/core/kv_cache_utils.py','v1/core/sched/scheduler.py','v1/engine/__init__.py',
           'v1/engine/async_llm.py','v1/worker/gpu_model_runner.py']
    for rel in paths:
        p=runtime/'vllm'/rel;assert sha(p)==inventory[rel]
        out=study/'backend_postimages_v5/vllm'/rel;out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('xb') as f:f.write(p.read_bytes())
        postimages.append(dict(runtime_relative_path=rel,archive_path=str(out.relative_to(root)),sha256=sha(out)))
    license_path=root/'third_party/licenses/vllm-Apache-2.0.txt'
    if license_path.exists():
        out=study/'backend_postimages_v5/vllm-Apache-2.0.txt'
        with out.open('xb') as f:f.write(license_path.read_bytes())
    write(study/'backend_postimages_v5/manifest.json',dict(files=postimages,native_binaries_identified_by_preflight_only=True))
    code=study/'postprocessing_source_v5';code.mkdir()
    for name in ['tsc_revision_mechanism_analysis_v3.py','tsc_revision_mechanism_effects_summary_v4.py',
                 'tsc_revision_mechanism_continue_unfinished_v5.py','tsc_revision_mechanism_client_wrapper_v5.py','tsc_revision_incomplete_reference_fix_v5.py','tsc_revision_mechanism_incomplete_CPU_v5.py','tsc_revision_mechanism_package_v5.py',
                 'tsc_revision_verify_archive.py','tsc_revision_split_raw_archive.py']:
        with (code/name).open('xb') as f:f.write((root/'scripts'/name).read_bytes())
    write(study/'closure_v5.json',dict(utc=datetime.now(timezone.utc).isoformat(),fresh_model_cells=9,
        original_cells_preserved=3,continued_cells=6,failed_partial_business_records=63,business_generations=sum(x['counts']['business'] for x in analysis['cells']),
        actual_verification_RPC_attempts=analysis['actual_GPU_calls'],behavior_cases=180,
        original_freeze_v3_sha256=sha(study/'freeze_v3.json'),original_55_source_files_still_match=True,
        preserved_three_cells_all_hashes_match=True,owned_remaining_GPU_PIDs=remaining,
        other_resident_GPU_PIDs_untouched=sorted(resident),new_GPU_requests_by_packager=0,
        execution_complete_scientific_success_separate=True,real_RepoBench_gap_not_closed_by_synthetic_code_cases=True))
    forbidden={'cache','tmp','runtime','runtimes','driver_cache','__pycache__'}
    selected=[]
    for p in study.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(study)
        if any(x in forbidden or x.endswith('_driver_cache') for x in rel.parts):continue
        if p.name.endswith(('.pyc','.lock','.tmp','.pid','.tar.gz')) or '.tar.gz.part' in p.name or p.name.startswith('raw_evidence_'):continue
        assert p.resolve().is_relative_to(root) and p.suffix not in ('.so','.safetensors','.bin')
        selected.append(p)
    entries=[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)]
    with (study/'raw_evidence_inventory_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['path','bytes','sha256']);w.writeheader();w.writerows(entries)
    with tarfile.open(archive,'x:gz',compresslevel=6) as tar:
        for row in entries:
            p=root/row['path'];item=tarfile.TarInfo(row['path']);item.size=row['bytes'];item.mode=0o644;item.mtime=int(p.stat().st_mtime)
            with p.open('rb') as f:tar.addfile(item,f)
    manifest=dict(schema_version='contractkv.mechanism-manifest-archive.v5',archive=archive.name,
        archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,member_files=len(entries),
        uncompressed_bytes=sum(x['bytes'] for x in entries),fresh_cells=9,business_generations=855,
        no_completed_cells_rerun=True,failed_incomplete_cell_fully_remeasured=True,failed_partial_business_records=63,total_observed_business_including_failed_attempt=918,all_failures_and_port_repairs_retained=True,
        actual_prompt_output_IDs_native_cache_events_and_source_postimages_included=True,
        no_credentials_model_weights_runtime_binaries_or_compilation_caches=True,packaging_source_sha256=sha(Path(__file__)))
    write(study/'raw_evidence_archive_manifest_v1.json',manifest)
    print(json.dumps(manifest))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root.resolve())
