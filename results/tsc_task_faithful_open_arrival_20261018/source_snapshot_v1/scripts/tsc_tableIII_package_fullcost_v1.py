"""Archive complete measurements, failures and analysis, excluding runtime caches.

Archive entries are regular repository-relative files. The one reused complete
Raw directory is represented by a byte-identical transport view at its logical
pair path; no absolute symlink is emitted and no model experiment is repeated.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')


def main(root):
    base=root/'results/tsc_tableIII_fullcost_replay_20261018'
    state=json.loads((base/'execution_state_v1.json').read_text())
    assert state['status']=='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS' and state['formal_GPU_cells_completed']==24
    assert len(state['completed_pairs'])==12
    result=json.loads((base/'analysis_v3/summary_v1.json').read_text())
    assert result['status']=='complete' and result['future_pairs']==4725 and result['full_controllers']==525
    assert json.loads((base/'formal_continuation4_exit_v1.json').read_text())['returncode']==0
    archive=base/'tableIII_fullcost_raw_evidence_v1.tar.gz'
    assert not archive.exists() and not (base/'closure_v1.json').exists(),'Never replace a sealed artifact'
    addendum=json.loads((base/'execution_continuation_v4.json').read_text())
    for item in addendum['preserved_completed_files']:
        assert sha(base/item['path'])==item['sha256']
    owned_groups=set()
    for p in base.glob('cells/*/attempt*/*/server_process_v1.json'):
        owned_groups.add(json.loads(p.read_text())['process_group'])
    resident={int(x) for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid',
        '--format=csv,noheader,nounits'],text=True).split() if x.isdigit()}
    own_resident=[]
    for pid in resident:
        try:
            if os.getpgid(pid) in owned_groups:own_resident.append(pid)
        except ProcessLookupError:pass
    assert not own_resident,'Do not archive an active owned GPU cell'
    write(base/'closure_v1.json',dict(utc=datetime.now(timezone.utc).isoformat(),
        actual_unique_fresh_servers=24,future_pairs=4725,complete_controllers=525,
        nineteen_completed_cells_preserved_without_rerun=True,
        owned_resident_PIDs=own_resident,other_resident_PIDs_untouched=sorted(resident),
        execution_complete_scientific_success_separate=True,
        logical_reused_raw_transport_view='cells/qwen14_r1/attempt4/raw',
        original_reused_raw='cells/qwen14_r1/attempt3/raw',
        all_preserved_measurement_hashes_still_match=True))
    code=base/'postprocessing_source_v1';code.mkdir()
    for name in ['tsc_tableIII_fullcost_analysis_v3.py','tsc_tableIII_package_fullcost_v1.py',
                 'tsc_tableIII_continue_unfinished_cells_v4.py','tsc_revision_verify_archive.py',
                 'tsc_revision_split_raw_archive.py']:
        shutil.copyfile(root/'scripts'/name,code/name)
    forbidden={'cache','tmp','runtimes','runtime','__pycache__','driver_cache'}

    def retain(p):
        relative=p.relative_to(base)
        return (p.is_file() and not any(x in forbidden or x.endswith('_driver_cache') for x in relative.parts)
            and not p.name.endswith(('.pyc','.pid','.lock','.tmp','.tar.gz'))
            and '.tar.gz.part' not in p.name and not p.name.startswith('raw_evidence_'))

    selected={p for p in base.rglob('*') if retain(p)}
    # rglob deliberately does not walk a symlinked directory. Enumerate the
    # logical pair view explicitly and emit regular files, never a symlink.
    for pair in state['completed_pairs']:
        for policy in ('raw','contract'):
            selected.update(p for p in (base/pair/policy).rglob('*') if retain(p))
    for p in selected:
        assert p.resolve().is_relative_to(root)
        assert p.suffix not in ('.safetensors','.so','.bin'),p
    inventory=[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(selected)]
    with (base/'raw_evidence_inventory_v1.csv').open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['path','bytes','sha256']);writer.writeheader();writer.writerows(inventory)
    with tarfile.open(archive,'x:gz',compresslevel=6) as tar:
        for item in inventory:
            p=root/item['path'];info=tarfile.TarInfo(item['path']);info.size=item['bytes']
            info.mode=0o644;info.mtime=int(p.stat().st_mtime)
            with p.open('rb') as f:tar.addfile(info,f)
    manifest=dict(schema_version='contractkv.original-tableIII-fullcost-archive.v1',archive=archive.name,
        archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,member_files=len(inventory),
        uncompressed_bytes=sum(x['bytes'] for x in inventory),fresh_server_cells=24,future_pairs=4725,
        includes_all_preserved_failed_attempts_and_completed_measurements=True,
        legacy_per_request_output_IDs_and_lengths_unavailable=True,
        actual_native_generation_token_totals_and_histograms_included=True,
        no_model_weights_runtime_binaries_compilation_caches_or_credentials=True,
        reused_complete_Raw_emitted_as_regular_byte_identical_transport_view=True,
        actual_experimental_execution_complete_not_a_positive_result_claim=True,
        packaging_source_sha256=sha(Path(__file__)))
    write(base/'raw_evidence_archive_manifest_v1.json',manifest)
    print(json.dumps(manifest))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root.resolve())
