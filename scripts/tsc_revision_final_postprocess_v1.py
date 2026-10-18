"""One-shot, CPU-only execution of existing frozen analyses after GPU completion."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

STUDY = 'results/tsc_task_faithful_open_arrival_20261018'
DISK = Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')
PY = '/home/user/miniconda3/envs/contractkv-cu128/bin/python'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value, exclusive=False):
    if exclusive:
        with path.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
            handle.write('\n')
    else:
        temp = path.with_suffix(path.suffix + '.tmp')
        with temp.open('w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
            handle.write('\n')
        temp.replace(path)


def process_matches(pid, command):
    path = Path('/proc') / str(pid) / 'cmdline'
    actual = path.read_bytes().split(b'\0') if path.exists() else []
    return [p.decode(errors='replace') for p in actual if p] == command


def readiness(study):
    live = []
    complete = []
    for phase in ('qwen', 'cross', 'gate'):
        launch = read(study / 'formal' / f'{phase}_launch_v1.json')
        state = read(study / 'formal' / f'{phase}_execution_state_v1.json')
        if process_matches(launch['worker_pid'], launch['command']):
            live.append(dict(phase=phase, PID=launch['worker_pid']))
        exit_path = study / 'formal' / f'{phase}_exit_v1.json'
        if exit_path.exists():
            assert read(exit_path)['returncode'] == 0, f'{phase} GPU phase failed; do not retry'
            assert state['status'] == 'COMPLETE_PENDING_ANALYSIS' and state['worker_pid'] is None
            complete.append(phase)
    master = read(study / 'formal/formal_supervisor_launch_v1.json')
    master_path = Path('/proc') / str(master['supervisor_pid']) / 'cmdline'
    actual = master_path.read_bytes().split(b'\0') if master_path.exists() else []
    expected_script = str(study.parents[1] / 'scripts/tsc_revision_final_phase_supervisor_v1.py').encode()
    master_live = expected_script in actual and b'formal' in actual
    terminal = study / 'formal/formal_supervisor_exit_v1.json'
    if terminal.exists():
        assert read(terminal)['returncode'] == 0
    ready = len(complete) == 3 and not live and not master_live and terminal.exists()
    assert ready or live or master_live, 'No live owned process and no complete formal exit; inspect, never restart'
    return dict(ready=ready, live_workers=live, completed_phases=complete,
                owned_master_live=master_live, recorded_master_PID=master['supervisor_pid'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--publication', type=Path)
    parser.add_argument('--mode', choices=['check', 'run'], required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    assert sys.platform == 'linux' and root.is_relative_to(DISK)
    assert Path(sys.executable).resolve() == Path(PY).resolve()
    study = root / STUDY
    plan_path = study / 'postprocessing_plan_v1.json'
    assert sha(plan_path) == args.plan_sha256
    plan = read(plan_path)
    assert sha(Path(__file__)) == plan['entry_sha256']
    for item in plan['inputs']:
        assert sha(root / item['path']) == item['sha256'], item['path']
    status = readiness(study)
    if args.mode == 'check':
        print(json.dumps(dict(status, mode='read_only_check', GPU_requests=0)))
        return 0 if status['ready'] else 75
    publication = read(args.publication)
    assert publication['local_commit_sha'] == publication['remote_commit_sha']
    assert len(publication['remote_commit_sha']) == 40 and publication['remote_SHA_verified'] is True
    assert publication['postprocessing_plan_sha256'] == args.plan_sha256
    out = study / 'postprocessing_v1'
    out.mkdir()  # Existing attempt, including a failed attempt, must never be overwritten.
    state = dict(status='WAITING_FOR_FROZEN_GPU', PID=os.getpid(), started_epoch_s=time.time(),
                 entry_sha256=sha(Path(__file__)), plan_sha256=args.plan_sha256,
                 publication_sha256=sha(args.publication), GPU_requests=0, stages=[])
    state_path = out / 'execution_state_v1.json'
    write(state_path, state)
    try:
        while not status['ready']:
            state['observed_GPU_status'] = status
            state['last_observation_epoch_s'] = time.time()
            write(state_path, state)
            time.sleep(45)
            status = readiness(study)
        state['status'] = 'RUNNING_EXISTING_FROZEN_CPU_ANALYSES'
        state['GPU_completed_epoch_s'] = time.time()
        write(state_path, state)
        for step in plan['steps']:
            target = root / step['output']
            assert not target.exists(), f'Preserve existing analysis output: {target}'
            command = [PY, '-B', str(root / step['entry']), '--root', str(root)] + step['arguments']
            command += ['--output', str(target)]
            record = dict(name=step['name'], command=command, started_epoch_s=time.time())
            with (out / f"{step['name']}.log").open('xb') as log:
                result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT)
            record.update(returncode=result.returncode, ended_epoch_s=time.time())
            state['stages'].append(record)
            write(state_path, state)
            assert result.returncode == 0, f"{step['name']} failed; preserve logs and output, do not retry"
            assert target.exists()
        state.update(status='CPU_ANALYSES_COMPLETE_PENDING_SYNC_PACKAGE_AND_INDEPENDENT_RECOMPUTE',
                     PID=None, ended_epoch_s=time.time())
        write(state_path, state)
        write(out / 'exit_v1.json', dict(returncode=0, ended_epoch_s=time.time()), exclusive=True)
        return 0
    except BaseException as error:
        state.update(status='FAILED_PRESERVE_EVIDENCE', PID=None, ended_epoch_s=time.time(),
                     error_type=type(error).__name__, error_message=str(error))
        write(state_path, state)
        write(out / 'exit_v1.json', dict(returncode=1, ended_epoch_s=time.time()), exclusive=True)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
