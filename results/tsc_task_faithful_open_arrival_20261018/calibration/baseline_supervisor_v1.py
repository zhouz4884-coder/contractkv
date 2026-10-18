import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_task_faithful_open_arrival_20261018'
COMMAND=['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/tsc_revision_final_raw_worker_v1.py', '--root', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv', '--phase', 'baseline', '--freeze-sha256', 'f9a2b64a28952f9fa5f9929699ab60416dbbdd030f4348731d6444753af64b92']
assert not (STUDY/'calibration/baseline_launch_v1.json').exists()
assert not (STUDY/'calibration/baseline_execution_state_v1.json').exists()
with (STUDY/'calibration/baseline_worker_v1.log').open('xb') as log:
    process=subprocess.Popen(COMMAND,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    with (STUDY/'calibration/baseline_launch_v1.json').open('x') as f:
        json.dump(dict(supervisor_pid=os.getpid(),worker_pid=process.pid,command=COMMAND,started_epoch_s=time.time(),Raw_only=True),f,indent=2)
    status=process.wait()
with (STUDY/'calibration/baseline_exit_v1.json').open('x') as f:
    json.dump(dict(returncode=status,ended_epoch_s=time.time()),f,indent=2)
raise SystemExit(status)
