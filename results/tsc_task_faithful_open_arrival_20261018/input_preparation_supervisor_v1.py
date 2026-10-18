import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_task_faithful_open_arrival_20261018'
assert not (STUDY/'input_preparation_launch_v1.json').exists()
command=['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',str(ROOT/'scripts/tsc_revision_final_prepare_sources_v1.py'),'--root',str(ROOT)]
with (STUDY/'input_preparation_worker_v1.log').open('xb') as log:
    process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    with (STUDY/'input_preparation_launch_v1.json').open('x') as f:
        json.dump(dict(supervisor_pid=os.getpid(),worker_pid=process.pid,command=command,started_epoch_s=time.time(),CPU_only=True),f,indent=2)
    status=process.wait()
with (STUDY/'input_preparation_exit_v1.json').open('x') as f:
    json.dump(dict(returncode=status,ended_epoch_s=time.time(),CPU_only=True),f,indent=2)
raise SystemExit(status)
