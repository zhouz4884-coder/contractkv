"""Offline verification/restoration of the final package; never runs experiments."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def safe_name(name, basename=False):
    path = PurePosixPath(name)
    assert name and '\\' not in name and ':' not in name
    assert not path.is_absolute() and '..' not in path.parts and '.' not in path.parts
    assert path.as_posix() == name
    if basename:
        assert len(path.parts) == 1
    else:
        assert path.parts[0] in {'scripts', 'configs', 'docs', 'results'}
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
    assert not any(p.split('.')[0].upper() in reserved or p.endswith((' ', '.')) for p in path.parts)
    return path


def main(workspace, package, archive, restore, output):
    workspace = workspace.resolve()
    package, archive, restore, output = [p.resolve() for p in (package, archive, restore, output)]
    for path in (archive, restore, output):
        assert path.is_relative_to(workspace) and path != workspace
    assert not restore.exists() and not output.exists(), 'Keep every previous attempt intact'
    receipt_path = package / 'package_receipt_v1.json'
    inventory_path = package / 'raw_member_inventory_v1.json'
    receipt = read(receipt_path)
    assert sha(inventory_path) == receipt['member_inventory_sha256']
    inventory = read(inventory_path)
    declared = inventory['members']
    records = {row['path']: row for row in declared}
    assert len(records) == len(declared) == receipt['regular_members'] == inventory['files']
    for name in records:
        safe_name(name)
    parts = receipt['parts']
    assert parts and len({p['path'] for p in parts}) == len(parts)
    total = 0
    for item in parts:
        safe_name(item['path'], basename=True)
        path = package / item['path']
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
        total += item['bytes']
    assert total == receipt['bytes']
    required = sum(r['bytes'] for r in records.values()) + (0 if archive.exists() else total)
    assert shutil.disk_usage(workspace).free > required + (128 << 20), 'Insufficient free disk; preserve all existing data'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with archive.open('xb') as destination:
            for item in parts:
                with (package / item['path']).open('rb') as source:
                    shutil.copyfileobj(source, destination, length=8 << 20)
    assert archive.stat().st_size == total and sha(archive) == receipt['sha256']
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        assert len(members) == len(records)
        assert len({m.name for m in members}) == len(members)
        assert {m.name for m in members} == set(records)
        for member in members:
            safe_name(member.name)
            assert member.isfile() and member.size == records[member.name]['bytes']
        restore.mkdir(parents=True)
        for member in members:
            target = restore.joinpath(*PurePosixPath(member.name).parts)
            assert target.resolve().is_relative_to(restore)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            value = hashlib.sha256()
            size = 0
            with target.open('xb') as destination:
                for block in iter(lambda: source.read(8 << 20), b''):
                    value.update(block)
                    size += len(block)
                    destination.write(block)
            assert size == records[member.name]['bytes']
            assert value.hexdigest() == records[member.name]['sha256'], member.name
            assert sha(target) == value.hexdigest(), 'Restored filesystem bytes differ'
    study = restore / 'results/tsc_task_faithful_open_arrival_20261018'
    dependencies = {}
    for name in ('raw_calibration_freeze_v1.json', 'formal_freeze_v1.json'):
        for item in read(study / name)['files']:
            safe_name(item['path'])
            target = restore.joinpath(*PurePosixPath(item['path']).parts)
            assert target.is_file() and sha(target) == item['sha256']
            if item['path'] in dependencies:
                assert dependencies[item['path']] == item['sha256']
            dependencies[item['path']] = item['sha256']
    assert inventory['all_frozen_root_dependencies_included'] and receipt['all_frozen_root_dependencies_included']
    assert len(dependencies) == receipt['frozen_root_dependencies'] == inventory['frozen_root_dependencies']
    assert read(study / 'formal_pre_forward_publication_v1.json')['freeze_sha256'] == sha(study / 'formal_freeze_v1.json')
    result = dict(status='PASS', archive_sha256=receipt['sha256'], archive_bytes=total,
                  verified_parts=len(parts), verified_and_restored_regular_members=len(records),
                  original_frozen_root_dependencies_verified=len(dependencies), restore_root=str(restore),
                  package_receipt_sha256=sha(receipt_path), inventory_sha256=sha(inventory_path),
                  path_traversal_links_and_overwrite_rejected=True, original_evidence_unchanged=True,
                  new_GPU_requests=0, scientific_recomputation_still_required=True,
                  source_sha256=sha(Path(__file__)))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('workspace', 'package', 'archive', 'restore', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    main(args.workspace, args.package, args.archive, args.restore, args.output)
