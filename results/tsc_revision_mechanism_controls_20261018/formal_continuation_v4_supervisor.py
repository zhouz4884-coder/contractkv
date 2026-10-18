"""Durable seven-cell continuation after the fixed-port prelaunch failure."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime,timezone

ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_revision_mechanism_controls_20261018'


def write(name,value):
    with (STUDY/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')


with (STUDY/'formal_continuation_v4_supervisor.lock').open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan=json.loads((STUDY/'formal_continuation_v4_launch_plan_v1.json').read_text())
    published=json.loads((STUDY/'formal_continuation_v4_preregistration_confirmed_v1.json').read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['supervisor_sha256']
    assert len(published['verified_remote_main'])==40 and published['receipt_sha256']==plan['receipt_sha256']
    assert not (STUDY/'formal_continuation_v4_launch_v1.json').exists(),'Never dispatch the frozen nine cells twice'
    before=json.loads((STUDY/'execution_state_v1.json').read_text())
    assert before['status']=='FAILURE_PRESERVED' and len(before['completed_cells'])==2
    cache=STUDY/'formal_continuation_v4_driver_cache';tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    for k in ('TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR'):env.pop(k,None)
    env.update(CUDA_VISIBLE_DEVICES='',TMPDIR=str(tmp),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),
        TRANSFORMERS_CACHE=str(cache/'hf/transformers'),XDG_CACHE_HOME=str(cache/'xdg'),TORCH_HOME=str(cache/'torch'),
        TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),
        PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    with (STUDY/'formal_continuation_v4_worker.log').open('xb') as log:
        worker=subprocess.Popen(plan['command'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write('formal_continuation_v4_launch_v1.json',dict(utc=datetime.now(timezone.utc).isoformat(),
            supervisor_pid=os.getpid(),worker_pid=worker.pid,command=plan['command'],
            verified_remote_main=published['verified_remote_main'],original_freeze_v3_unchanged=True))
        rc=worker.wait()
        write('formal_continuation_v4_exit_v1.json',dict(utc=datetime.now(timezone.utc).isoformat(),worker_pid=worker.pid,returncode=rc))
