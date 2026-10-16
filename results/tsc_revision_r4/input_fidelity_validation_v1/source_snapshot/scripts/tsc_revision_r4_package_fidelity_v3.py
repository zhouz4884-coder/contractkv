"""Archive the isolated input-fidelity study without editing the R4 packager."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--study', choices=('input_fidelity_development_head_v3',
                                          'input_fidelity_development_faithful_v3'), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / 'results/tsc_revision_r4' / args.study
    audit = json.loads((base / 'analysis/completion_audit_v1.json').read_text())
    if not audit['execution_complete'] or audit['complete_cells'] != 2:
        raise ValueError('Complete both paired cells and independent primary audit first')
    archive = base / (args.study + '_raw_evidence_v1.tar.gz')
    if archive.exists() or (base / 'closure_v1.json').exists():
        raise ValueError('Preserve archive attempts')
    freeze = json.loads((base / 'freeze.json').read_text())
    for item in freeze['files']:
        if sha(root / item['path']) != item['sha256'] or sha(base / 'source_snapshot' / item['path']) != item['sha256']:
            raise ValueError('Frozen source drift: ' + item['path'])
    condition = freeze['protocol']['task_fidelity_condition']
    logs = list((root / 'logs/tsc_revision_r4').glob(f'fidelity_development_v3_{condition}_*_server.log'))
    logs += [root / 'logs/tsc_revision_r4/input_fidelity_development_launcher_snapshot_v3.sh',
             root / 'logs/tsc_revision_r4/input_fidelity_development_v3.log']
    owned = set()
    pattern = re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    for path in logs:
        if path.is_file():
            for line in path.open(errors='replace'):
                found = pattern.search(line)
                if found:
                    owned.add(int(found.group(1)))
    resident = {int(value) for value in subprocess.check_output(
        ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).split() if value.isdigit()}
    if owned & resident:
        raise ValueError('Owned GPU workers remain resident')
    closure = {'timestamp_UTC': datetime.now(timezone.utc).isoformat(),
               'frozen_current_and_snapshot_files': len(freeze['files']),
               'owned_resident_gpu_pids': sorted(owned & resident),
               'other_resident_gpu_pids_untouched': sorted(resident - owned),
               'no_process_stopped_by_packager': True,
               'execution_complete_scientific_success_separate': True}
    (base / 'closure_v1.json').write_text(json.dumps(closure, indent=2) + '\n')
    files = [path for path in base.rglob('*') if path.is_file() and
             not path.name.endswith(('.pid', '.partial', '.tar.gz')) and '.tar.gz.part' not in path.name and
             not path.name.startswith('raw_evidence_')]
    files += [path for path in logs if path.is_file()]
    files += [root / 'results/tsc_revision_r4/input_fidelity_development_prerun_publication_v3.json',
              root / 'third_party/licenses/vllm-Apache-2.0.txt', root / 'third_party/licenses/README.md']
    inventory = [{'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                 for path in sorted(set(files))]
    with (base / 'raw_evidence_inventory_v1.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('path', 'bytes', 'sha256'))
        writer.writeheader(); writer.writerows(inventory)
    with tarfile.open(archive, 'w:gz', compresslevel=6) as stream:
        for item in inventory:
            stream.add(root / item['path'], arcname=item['path'], recursive=False)
    manifest = {'schema_version': 'tsc-r4.task-fidelity-study-archive.v1', 'study': args.study,
                'archive': archive.name, 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
                'member_files': len(inventory), 'cases': audit['cases'],
                'experimental_execution_complete_scientific_success_separate': True,
                'actual_prompt_output_ids_requests_metrics_runtime_source_and_analysis_included': True}
    (base / 'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
