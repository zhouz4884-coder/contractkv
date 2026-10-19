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
    study = root / 'results/tsc_effective_reuse_recovery_20261019/clean_renderer_development_v1'
    receipt = study / 'preflight_receipt_v1.json'
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == args.receipt_sha256
    assert not (study / 'worker_launch_v1.json').exists()
    assert not (study / 'execution_state_v1.json').exists()
    command = ['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B',
        str(root / 'scripts/tsc_effective_renderer_worker_v1.py'), '--root', str(root), '--mode', 'execute',
        '--freeze-sha256', 'b9084ee9348aa2d9b2f6176266454c5fe0a8a67a0059092501e3882da86f8a4d',
        '--receipt-sha256', args.receipt_sha256]
    started = time.time()
    with (study / 'CPU_tmp/renderer_worker_v1.log').open('xb') as log:
        process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        launch = dict(launcher_pid=os.getpid(), worker_pid=process.pid, command=command,
                      published_preflight_commit=args.published_commit, started_epoch_s=started)
        with (study / 'worker_launch_v1.json').open('x') as f:
            json.dump(launch, f, indent=2)
            f.write('\n')
        code = process.wait()
    with (study / 'worker_exit_v1.json').open('x') as f:
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
