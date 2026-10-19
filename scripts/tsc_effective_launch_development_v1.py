"""Single-use launcher/exit receipt for the already frozen development worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main(args):
    root = args.root.resolve()
    study = root / 'results/tsc_effective_reuse_recovery_20261019'
    receipt = study / 'development_preflight_receipt_v1.json'
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == args.receipt_sha256
    assert not (study / 'development_worker_launch_v1.json').exists()
    assert not (study / 'development_execution_state_v1.json').exists()
    command = ['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B',
        str(root / 'scripts/tsc_effective_development_worker_v1.py'), '--root', str(root), '--mode', 'execute',
        '--freeze-sha256', 'b27e6528b57b6e0f4f41a43f3484c5d1bc67c70e00662a041b0e6ae3f62bbe41',
        '--receipt-sha256', args.receipt_sha256]
    started = time.time()
    with (study / 'CPU_tmp/development_worker_v1.log').open('xb') as log:
        process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        launch = dict(launcher_pid=os.getpid(), worker_pid=process.pid, command=command,
                      published_preflight_commit=args.published_commit, started_epoch_s=started)
        with (study / 'development_worker_launch_v1.json').open('x') as f:
            json.dump(launch, f, indent=2)
            f.write('\n')
        code = process.wait()
    with (study / 'development_worker_exit_v1.json').open('x') as f:
        json.dump(dict(returncode=code, worker_pid=process.pid, started_epoch_s=started,
                       ended_epoch_s=time.time(), no_automatic_retries=True), f, indent=2)
        f.write('\n')
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--receipt-sha256', required=True)
    parser.add_argument('--published-commit', required=True)
    raise SystemExit(main(parser.parse_args()))
