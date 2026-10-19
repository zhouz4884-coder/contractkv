"""Receipt-gated single-use long-running serving phase launcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(a):
    root=a.root.resolve();study=root/'results/tsc_template_task_serving_20261019'
    receipt=study/(a.phase+'_preflight_receipt_v1.json');assert sha(receipt)==a.receipt_sha256
    assert not (study/(a.phase+'_launch_v1.json')).exists() and not (study/(a.phase+'_execution_state_v1.json')).exists()
    command=['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',str(root/'scripts/tsc_template_task_serving_worker_v1.py'),
        '--root',str(root),'--phase',a.phase,'--mode','execute','--freeze-sha256',sha(study/(a.phase+'_freeze_v1/freeze.json')),'--receipt-sha256',a.receipt_sha256]
    started=time.time()
    with (study/('CPU_tmp/'+a.phase+'_worker_v1.log')).open('xb') as log:
        process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        with (study/(a.phase+'_launch_v1.json')).open('x') as f:json.dump(dict(launcher_pid=os.getpid(),worker_pid=process.pid,command=command,published_commit=a.published_commit,started_epoch_s=started,launcher_sha256=sha(Path(__file__))),f,indent=2);f.write('\n')
        ret=process.wait()
    with (study/(a.phase+'_exit_v1.json')).open('x') as f:json.dump(dict(returncode=ret,worker_pid=process.pid,started_epoch_s=started,ended_epoch_s=time.time(),automatic_retries=False),f,indent=2);f.write('\n')
    return ret
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--phase',choices=['calibration','formal'],required=True)
    p.add_argument('--receipt-sha256',required=True);p.add_argument('--published-commit',required=True);raise SystemExit(main(p.parse_args()))
