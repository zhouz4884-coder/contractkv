"""One-shot CPU-only package launch with a recoverable PID and excluded log."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--package-source-sha256', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    assert sys.platform == 'linux'
    assert root.is_relative_to(Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9'))
    study = root / 'results/tsc_task_faithful_open_arrival_20261018'
    state = json.loads((study / 'postprocessing_v1/execution_state_v1.json').read_text())
    assert state['status'] == 'CPU_ANALYSES_COMPLETE_PENDING_SYNC_PACKAGE_AND_INDEPENDENT_RECOMPUTE'
    assert all(s['returncode'] == 0 for s in state['stages']) and len(state['stages']) == 3
    assert not (study / 'evidence_package_v1').exists(), 'Never restart or overwrite a package attempt'
    package = root / 'scripts/tsc_revision_final_serving_package_v1.py'
    assert sha(package) == args.package_source_sha256
    control = study / 'CPU_tmp/package_control_v1'
    control.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-B', str(package), '--root', str(root)]
    receipt = dict(PID=os.getpid(), command=command, started_epoch_s=time.time(),
                   dispatcher_sha256=sha(Path(__file__)), package_source_sha256=sha(package),
                   log_path=str(control / 'package.log'), new_GPU_requests=0,
                   keep_live_control_logs_outside_immutable_raw_inventory=True)
    with (control / 'launch_v1.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    with (control / 'package.log').open('xb') as handle:
        os.dup2(handle.fileno(), 1)
        os.dup2(handle.fileno(), 2)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(control), TMP=str(control), TEMP=str(control))
    os.nice(19)
    os.execv(sys.executable, command)


if __name__ == '__main__':
    main()
