"""One-shot launcher; never retries, resumes, or rewrites completed cells."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')


def main(args):
    root=args.root.resolve();study=root/'results/tsc_authorization_task_repair_20261019'
    assert sha(study/'repair_preflight_receipt_v2.json')==args.preflight_receipt_sha256
    publication=json.loads((study/'pre_forward_publication_v2.json').read_text(encoding='utf-8'))
    assert publication['preflight_receipt_sha256']==args.preflight_receipt_sha256
    assert publication['freeze_sha256']==sha(study/'freeze_v2.json')
    assert not (study/'execution_state_v2.json').exists()
    command=['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',
             str(root/'scripts/tsc_repair_authorized_worker_v2.py'),'--root',str(root),
             '--mode','execute','--freeze-sha256',sha(study/'freeze_v2.json'),
             '--preflight-receipt-sha256',args.preflight_receipt_sha256]
    started=time.time()
    with (study/'worker_v2.log').open('xb') as log:
        worker=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(study/'worker_launch_v2.json',dict(launcher_pid=os.getpid(),worker_pid=worker.pid,
              command=command,started_epoch_s=started,source_sha256=sha(Path(__file__)),automatic_retries=False))
        code=worker.wait()
    write(study/'worker_exit_v2.json',dict(returncode=code,started_epoch_s=started,ended_epoch_s=time.time(),
          worker_pid=worker.pid,new_automatically_retried_cells=0))
    return code


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--preflight-receipt-sha256',required=True)
    raise SystemExit(main(p.parse_args()))
