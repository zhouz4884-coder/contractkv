"""Single-use phase launcher; no automatic restart of a scientific cell."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import os

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(a):
    root=a.root.resolve();study=root/'results/tsc_template_task_serving_20261019'
    assert sha(study/'development_preflight_receipt_v2.json')==a.receipt_sha256
    freeze=study/'development_freeze_v2/freeze.json'
    assert not (study/f'development_launch_{a.mode}_v2.json').exists()
    command=['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',str(root/'scripts/tsc_template_task_development_worker_v2.py'),
        '--root',str(root),'--mode',a.mode,'--freeze-sha256',sha(freeze),'--receipt-sha256',a.receipt_sha256]
    started=time.time()
    with (study/f'CPU_tmp/development_{a.mode}_v2.log').open('xb') as log:
        p=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        record=dict(launcher_pid=os.getpid(),worker_pid=p.pid,command=command,published_commit=a.published_commit,started_epoch_s=started,launcher_source_sha256=sha(Path(__file__)))
        with (study/f'development_launch_{a.mode}_v2.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
        code=p.wait()
    with (study/f'development_exit_{a.mode}_v2.json').open('x') as f:
        json.dump(dict(returncode=code,worker_pid=p.pid,started_epoch_s=started,ended_epoch_s=time.time(),automatic_retries=False),f,indent=2);f.write('\n')
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--mode',choices=['qwen','others'],required=True)
    p.add_argument('--receipt-sha256',required=True);p.add_argument('--published-commit',required=True);raise SystemExit(main(p.parse_args()))
