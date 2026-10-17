"""Seal diagnostic raw events and runtime evidence after all servers exit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--artifact-version', choices=('v1','v2'), default='v1')
    args = p.parse_args()
    root = args.root
    version = args.artifact_version
    archive, manifest = root/f'probe_archive_{version}.zip', root/f'probe_archive_manifest_{version}.json'
    assert not archive.exists() and not manifest.exists()
    assert 'RESIDENCY_DIAGNOSTIC3_COMPLETE' in (root/'probe_launcher_v1.log').read_text()
    compute = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory',
                                       '--format=csv,noheader,nounits'], text=True)
    assert not compute.strip(), compute
    freeze = json.loads((root/'probe_freeze_v1.json').read_text())
    for item in freeze['files']:
        assert sha(Path(item['path'])) == item['sha256'], item['path']
    backend = Path('third_party/vllm-contractkv-tsc-r2-margin/vllm/v1/core')
    for item in freeze['remote_native_read_only_hook_sources']:
        assert sha(backend/item['file']) == item['sha256'], item['file']
    integrity = {'all_probe_frozen_source_bytes_match': True, 'all_extra_native_sources_match': True,
                 'GPU_compute_empty_after_cleanup': True,
                 'gpu_snapshot': subprocess.check_output(['nvidia-smi','--query-gpu=index,name,uuid,memory.used',
                                                         '--format=csv'], text=True),
                 'no_manuscript_or_original_backend_mutation': True}
    integrity_path = root/f'probe_post_run_integrity_{version}.json'
    assert not integrity_path.exists()
    integrity_path.write_bytes((json.dumps(integrity, indent=2)+'\n').encode())
    files = []
    for alias in ('llama', 'mistral', 'qwen'):
        base = root/'probe_cells_v1'/alias
        rows = [json.loads(x) for x in (base/'responses.jsonl').open() if x.strip()]
        assert rows[-1]['event'] == 'diagnostic_completed'
        assert rows[-1]['completed_requests'] == rows[-1]['businesses'] == 46
        files.extend(base/name for name in ('responses.jsonl','backend_trace.jsonl','metrics.jsonl',
                                            'runtime_manifest.json','server.log'))
    files.extend(root/name for name in ('probe_plan_v1.json','probe_freeze_v1.json',
        'probe_pre_forward_publication_v1.json','probe_pre_forward_integrity_v1.json',
        'remote_import_preflight_v1.json','preflight_hook_events_v1.jsonl',
        'probe_launcher_v1.log'))
    files.append(integrity_path)
    members = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in files:
            name = f.relative_to(root).as_posix()
            z.write(f, name)
            members.append({'name':name,'bytes':f.stat().st_size,'sha256':sha(f)})
    result = {'archive':archive.name,'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,
              'members':members,'model_weights_not_included':True,
              'new_sources':0,'actual_business_requests':138,'diagnostic_only_no_performance_claim':True,
              'base_primary_freeze_sha256':freeze['base_primary_freeze_sha256'],
              'packaging_script_sha256':sha(Path(__file__))}
    manifest.write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print(json.dumps({'archive_sha256':result['archive_sha256'],'bytes':result['archive_bytes'],'members':len(members)}))


if __name__ == '__main__':
    main()
