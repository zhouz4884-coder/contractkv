"""Durable supervisor for the five explicitly frozen unfinished cells."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime,timezone

ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'
PYTHON='/home/user/miniconda3/envs/contractkv-cu128/bin/python'


def write(name,data):
    with (STUDY/name).open('x') as f:json.dump(data,f,indent=2);f.write('\n')


with (STUDY/'formal_continuation4_supervisor.lock').open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan=json.loads((STUDY/'formal_continuation4_launch_plan_v1.json').read_text())
    published=json.loads((STUDY/'formal_continuation4_preregistration_confirmed_v1.json').read_text())
    assert plan['supervisor_sha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert published['receipt_sha256']==plan['receipt_sha256']
    assert published['verified_remote_main'] and len(published['verified_remote_main'])==40
    assert not (STUDY/'formal_continuation4_launch_v1.json').exists(),'Never launch this continuation twice'
    cache=STUDY/'formal_continuation4_driver_cache';tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    for k in ['TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR']:env.pop(k,None)
    env.update(CUDA_VISIBLE_DEVICES='',TMPDIR=str(tmp),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),
        TRANSFORMERS_CACHE=str(cache/'hf/transformers'),XDG_CACHE_HOME=str(cache/'xdg'),TORCH_HOME=str(cache/'torch'),
        TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),
        PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    with (STUDY/'formal_continuation4_worker.log').open('xb') as log:
        worker=subprocess.Popen(plan['command'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write('formal_continuation4_launch_v1.json',dict(utc=datetime.now(timezone.utc).isoformat(),
            supervisor_pid=os.getpid(),worker_pid=worker.pid,command=plan['command'],verified_remote_main=published['verified_remote_main']))
        rc=worker.wait()
        write('formal_continuation4_exit_v1.json',dict(utc=datetime.now(timezone.utc).isoformat(),worker_pid=worker.pid,returncode=rc))
