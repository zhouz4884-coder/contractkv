"""Read-only final source, evidence and GPU ownership audit for phase two."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess


def sha(path):
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.output.exists():
        raise ValueError('Preserve the previous closure observation')
    failures, scopes, studies = [], [], []
    completed = (
        'diagnosis_v1', 'warm_reuse_v1', 'batch_reuse_v1',
        'margin_smoke_v1', 'profile_v1', 'development_pilot_v1',
        'long_format_v2', 'long_native_v3', 'long_extent_v4', 'validation_v1',
    )
    for phase, names in (('tsc_revision_r2', completed),
                         ('tsc_revision_r3', ('validation_v1',))):
        for name in names:
            base = root / 'results' / phase / name
            freeze_path = base / 'freeze.json'
            frozen = json.loads(freeze_path.read_text(encoding='utf-8'))
            checks = []
            for item in frozen['files']:
                actual = sha(root / item['path'])
                snapshot = sha(base / 'source_snapshot' / item['path'])
                match = actual == snapshot == item['sha256']
                checks.append(dict(item, current_sha256=actual,
                                   snapshot_sha256=snapshot, matches=match))
                if not match:
                    failures.append(f'{phase}/{name}: {item["path"]}')
            dispatch_checks = []
            dispatch_path = base / 'execution_dispatch_freeze_v1.json'
            if dispatch_path.exists():
                dispatch = json.loads(dispatch_path.read_text(encoding='utf-8'))
                if dispatch['primary_freeze_sha256'] != sha(freeze_path):
                    failures.append(f'{phase}/{name}: dispatch parent')
                for item in dispatch['files']:
                    actual = sha(root / item['path'])
                    snapshot = sha(base / item['snapshot'])
                    match = actual == snapshot == item['sha256']
                    dispatch_checks.append(dict(item, current_sha256=actual,
                                                snapshot_sha256=snapshot, matches=match))
                    if not match:
                        failures.append(f'{phase}/{name}: dispatch {item["path"]}')
            scopes.append({'scope': f'{phase}/{name}', 'freeze_sha256': sha(freeze_path),
                           'files_checked': len(checks), 'files': checks,
                           'dispatch_files': dispatch_checks})
            archive_path = base / 'raw_evidence_archive_manifest_v1.json'
            closure_path = base / 'closure_v1.json'
            if not archive_path.is_file() or not closure_path.is_file():
                failures.append(f'{phase}/{name}: missing evidence/closure')
            else:
                manifest = json.loads(archive_path.read_text(encoding='utf-8'))
                studies.append({'study': f'{phase}/{name}',
                                'archive_manifest_sha256': sha(archive_path),
                                'archive_sha256': manifest['archive_sha256'],
                                'closure_sha256': sha(closure_path)})

    original_checks = []
    for name in ('validation', 'long_horizon', 'known_counterexamples'):
        base = root / 'results/tsc_revision_r1r' / name
        frozen = json.loads((base / 'freeze_v1.json').read_text(encoding='utf-8'))
        for item in frozen['files']:
            match = sha(root / item['path']) == sha(base / 'source_snapshot' / item['path']) == item['sha256']
            original_checks.append({'scope': name, 'path': item['path'], 'matches': match})
            if not match:
                failures.append(f'original/{name}: {item["path"]}')

    backend = json.loads((root / 'configs/tsc_revision_r2_backend_commitment_v1.json').read_text(encoding='utf-8'))
    native_checks = []
    for item in backend['native_extensions']:
        hashes = {key: sha(root / 'third_party' / backend[key] / item['relative_path'])
                  for key in ('base', 'new_backend')}
        match = all(value == item['sha256'] for value in hashes.values())
        native_checks.append(dict(item, actual_hashes=hashes, matches=match))
        if not match:
            failures.append('native: ' + item['relative_path'])

    registry = json.loads((root / 'results/tsc_revision_r2/model_registry_v1.json').read_text(encoding='utf-8'))
    model_checks = []
    for model in registry['models']:
        for item in model['files']:
            path = Path(model['model_path']) / item['file']
            stat = path.stat() if path.is_file() else None
            weight = item['file'].endswith('.safetensors')
            actual_hash = None if weight else sha(path)
            match = (stat is not None and stat.st_size == item['bytes'] and
                     stat.st_mtime_ns == item['mtime_ns'] and
                     (weight or actual_hash == item['sha256']))
            model_checks.append({'model': model['key'], 'file': item['file'],
                                 'bytes_and_mtime_match': stat is not None and stat.st_size == item['bytes'] and stat.st_mtime_ns == item['mtime_ns'],
                                 'hash_recomputed_at_closure': not weight,
                                 'metadata_sha256': actual_hash, 'matches': match})
            if not match:
                failures.append('model: ' + model['key'] + '/' + item['file'])

    owned = set()
    pattern = re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    log_count = 0
    for phase in ('tsc_revision_r2', 'tsc_revision_r3'):
        for log in (root / 'logs' / phase).glob('*_server.log'):
            log_count += 1
            with log.open(encoding='utf-8', errors='replace') as stream:
                for line in stream:
                    match = pattern.search(line)
                    if match:
                        owned.add(int(match.group(1)))
    query = subprocess.run(['nvidia-smi', '--query-compute-apps=pid',
                            '--format=csv,noheader,nounits'], capture_output=True, text=True)
    resident = {int(line.strip()) for line in query.stdout.splitlines() if line.strip().isdigit()}
    if query.returncode or owned & resident:
        failures.append('GPU ownership cleanup/query')
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,name,uuid,memory.used,memory.total',
                          '--format=csv'], capture_output=True, text=True, check=True)
    result = {'schema_version': 'tsc.phase2.remote-closure.v1',
              'timestamp': datetime.now(timezone.utc).isoformat(), 'hostname': socket.gethostname(),
              'completed_studies': studies, 'completed_study_count': len(studies),
              'freeze_scopes': scopes, 'phase2_frozen_file_checks': sum(x['files_checked'] for x in scopes),
              'additional_dispatch_checks': sum(len(x['dispatch_files']) for x in scopes),
              'original_frozen_checks': original_checks, 'native_checks': native_checks,
              'model_checks': model_checks,
              'weight_hash_boundary': 'Full shard hashes were registered before experiments; closure rechecks weight bytes/mtime and hashes model metadata, not all weight contents.',
              'server_logs_scanned': log_count, 'owned_resident_gpu_pids': sorted(owned & resident),
              'other_resident_gpu_pids_untouched': sorted(resident - owned), 'gpu_snapshot': gpu.stdout,
              'no_processes_stopped_by_this_audit': True, 'failures': failures,
              'closure_complete': not failures,
              'scope': 'Point-in-time source/snapshot/evidence/ownership checks. Scientific outcome and local transport verification remain separate.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('closure_complete', 'completed_study_count',
                      'phase2_frozen_file_checks', 'additional_dispatch_checks',
                      'owned_resident_gpu_pids', 'failures')}))
    return 0 if not failures else 2


if __name__ == '__main__':
    raise SystemExit(main())
