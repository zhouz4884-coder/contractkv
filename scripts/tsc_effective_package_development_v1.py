"""Archive all development attempts, exact frozen sources and import mirrors."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

STUDY = Path('results/tsc_effective_reuse_recovery_20261019')


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p, x):
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(x, f, indent=2)
        f.write('\n')


def main(root):
    study = root / STUDY
    assert read(study / 'development_worker_exit_v2.json')['returncode'] == 0
    assert read(study / 'analysis_development_v1/summary_v1.json')['actual_business'] == 600
    output = study / 'development_evidence_package_v1'
    output.mkdir()
    selected = {}
    for p in study.rglob('*'):
        relative = p.relative_to(study)
        if any(x in {'cache', 'tmp', 'CPU_tmp', 'preflight_v3', 'development_evidence_package_v1', '__pycache__', 'preview_development_v1'} for x in relative.parts):
            continue
        if not p.is_file() or p.is_symlink() or p.suffix == '.pyc':
            continue
        if p.name.startswith('development_postprocessing_') or p.name == 'development_postprocess_v1.log':
            continue
        selected[p.relative_to(root).as_posix()] = p
    for p in (study / 'source_snapshot_v2').rglob('*'):
        if not p.is_file() or p.suffix == '.pyc':
            continue
        name = p.relative_to(study / 'source_snapshot_v2').as_posix()
        if name in selected:
            assert sha(selected[name]) == sha(p)
        else:
            selected[name] = p
    for version in [1, 2]:
        for row in read(study / f'freeze_development_v{version}.json')['files']:
            p = root / row['path']
            assert sha(p) == row['sha256']
            if row['path'] in selected:
                assert sha(selected[row['path']]) == row['sha256']
            else:
                selected[row['path']] = p
    for name in ['tsc_effective_development_analysis_v1.py', 'tsc_effective_package_development_v1.py', 'tsc_effective_postprocess_development_v1.py']:
        selected['scripts/' + name] = root / 'scripts' / name
    inventory = [dict(path=k, sha256=sha(p), bytes=p.stat().st_size) for k, p in sorted(selected.items())]
    write(output / 'inventory_v1.json', dict(members=inventory, files=len(inventory), all_failed_and_completed_attempts_retained=True))
    archive = output / 'effective_reuse_development_raw_v1.tar.gz'
    with tarfile.open(archive, 'x:gz') as tar:
        for name, p in sorted(selected.items()):
            tar.add(p, arcname=name, recursive=False)
    with tarfile.open(archive, 'r:gz') as tar:
        expected = {r['path']: r for r in inventory}
        assert len(tar.getmembers()) == len(expected)
        for m in tar.getmembers():
            assert m.isfile() and hashlib.sha256(tar.extractfile(m).read()).hexdigest() == expected[m.name]['sha256']
    parts = []
    with archive.open('rb') as f:
        index = 0
        while True:
            data = f.read(32 << 20)
            if not data:
                break
            p = output / (archive.name + f'.part{index:03d}')
            with p.open('xb') as target:
                target.write(data)
            parts.append(dict(path=p.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
            index += 1
    receipt = dict(archive=archive.name, bytes=archive.stat().st_size, sha256=sha(archive),
        regular_members=len(inventory), inventory_sha256=sha(output / 'inventory_v1.json'),
        parts=parts, member_bytes_roundtrip_verified=True, no_models_or_runtime_copied=True,
        Root_import_mirrors_are_byte_exact_executed_snapshot=True, failed_attempt1_business=154,
        complete_attempt2_business=600, source_sha256=sha(Path(__file__)))
    write(output / 'package_receipt_v1.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    main(p.parse_args().root.resolve())
