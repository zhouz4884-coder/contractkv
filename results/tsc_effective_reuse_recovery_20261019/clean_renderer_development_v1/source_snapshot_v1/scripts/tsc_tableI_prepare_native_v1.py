"""Restore RECORD-verified native sources in an isolated overlay, not in-place."""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import shutil
import urllib.request


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--overlay', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--registry', type=Path, required=True)
    a = p.parse_args()
    assert not a.overlay.exists() and not a.output.exists()
    d = importlib.metadata.distribution('vllm')
    assert d.version == '0.10.2'
    sources = [f for f in d.files if str(f).endswith('.py') and f.hash and f.hash.mode == 'sha256']
    bad = [f for f in sources if base64.urlsafe_b64encode(
        hashlib.sha256(d.locate_file(f).read_bytes()).digest()).decode().rstrip('=') != f.hash.value]
    assert {str(f) for f in bad} <= {'vllm/engine/llm_engine.py', 'vllm/v1/core/sched/scheduler.py'}
    native = d.locate_file('vllm').resolve()
    shutil.copytree(native, a.overlay/'vllm',
                    copy_function=lambda src, dst: os.symlink(os.path.abspath(src), dst),
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    restored = []
    for f in bad:
        url = 'https://raw.githubusercontent.com/vllm-project/vllm/v0.10.2/' + str(f)
        req = urllib.request.Request(url, headers={'User-Agent': 'ContractKV-provenance-audit'})
        data = urllib.request.urlopen(req, timeout=45).read()
        assert base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=') == f.hash.value, str(f)
        dest = a.overlay/str(f)
        assert dest.is_symlink()
        dest.unlink()
        dest.write_bytes(data)
        restored.append({'file': str(f), 'source_URL': url, 'sha256': sha(dest)})
    assert all(base64.urlsafe_b64encode(hashlib.sha256((a.overlay/str(f)).read_bytes()).digest()).decode().rstrip('=') == f.hash.value for f in sources)
    registry = json.loads(a.registry.read_text())
    model = next(m for m in registry['models'] if m['model'] == 'Qwen3-8B')
    checked = []
    for f in model['files']:
        path = Path(model['model_path'])/f['file']
        assert path.stat().st_size == f['bytes'] and sha(path) == f['sha256'], str(path)
        checked.append(f)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    result = {'vllm_version': d.version, 'registered_native_python_files_checked': len(sources),
        'original_environment_RECORD_mismatches': [str(f) for f in bad],
        'overlay_registered_python_files_all_match_RECORD': True,
        'restored_source_files': restored, 'overlay_path': str(a.overlay),
        'original_environment_modified': False, 'model': model['model'],
        'model_files_all_sha256_match': True, 'model_files': checked,
        'versions': {k: importlib.metadata.version(k) for k in ['torch','vllm','transformers']},
        'new_model_forwards': 0}
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['model_files']}), flush=True)


if __name__ == '__main__':
    main()
