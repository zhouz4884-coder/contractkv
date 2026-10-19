"""Wait only on the current v2 worker; CPU audit/package once, never rerun GPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def state(p, x):
    temp = p.with_suffix('.tmp')
    temp.write_text(json.dumps(x, indent=2) + '\n')
    temp.replace(p)


def main(root):
    study = root / 'results/tsc_effective_reuse_recovery_20261019/clean_renderer_development_v1'
    status = study / 'postprocessing_state_v1.json'
    assert not status.exists()
    current = dict(status='WAITING_FOR_EXISTING_V2_WORKER', pid=os.getpid(), steps=[], new_GPU_requests=0)
    state(status, current)
    try:
        deadline = time.monotonic() + 6 * 3600
        while not (study / 'worker_exit_v1.json').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Existing worker wait expired; nothing was restarted')
            time.sleep(10)
        assert read(study / 'worker_exit_v1.json')['returncode'] == 0, 'Retain GPU failure and attribute before new work'
        validate_preflight(root / 'results/tsc_revision_mechanism_controls_20261018')
        for row in read(study / 'freeze_v1.json')['files']:
            assert sha(root / row['path']) == row['sha256'], row['path']
        python = '/home/user/miniconda3/envs/contractkv-cu128/bin/python'
        commands = [
            ('analysis', [python, '-B', str(root / 'scripts/tsc_effective_renderer_analysis_v1.py'), '--root', str(root), '--output', str(study / 'analysis_v1')]),
            ('package', [python, '-B', str(root / 'scripts/tsc_effective_renderer_package_v1.py'), '--root', str(root)])]
        for label, command in commands:
            current['status'] = 'RUNNING_CPU_' + label.upper()
            state(status, current)
            started = time.time()
            with (study / ('CPU_tmp/renderer_' + label + '_v1.log')).open('xb') as log:
                done = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
            current['steps'].append(dict(stage=label, returncode=done.returncode, started_epoch_s=started,
                ended_epoch_s=time.time(), source_sha256=sha(Path(command[2]))))
            state(status, current)
            assert done.returncode == 0, 'CPU delivery failure retained: ' + label
        current.update(status='RENDERER_CPU_COMPLETE_PENDING_LOCAL_RECOMPUTE_AND_FINAL_DECISION', pid=None)
        state(status, current)
        with (study / 'postprocessing_exit_v1.json').open('x') as f:
            json.dump(dict(returncode=0, new_GPU_requests=0), f)
    except BaseException as error:
        current.update(status='FAILURE_PRESERVED', pid=None, error_type=type(error).__name__, error_message=str(error))
        state(status, current)
        with (study / 'postprocessing_exit_v1.json').open('x') as f:
            json.dump(dict(returncode=1, error_type=type(error).__name__, error_message=str(error), new_GPU_requests=0), f)
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    main(p.parse_args().root.resolve())
