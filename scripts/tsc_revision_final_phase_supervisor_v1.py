"""Exclusive, non-restarting execution of already published frozen phases."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_raw_worker_v1 import STUDY,PY,DISK,read,write,sha,resource_snapshot,foreign_pids


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--kind',choices=['profiles','formal'],required=True);parser.add_argument('--freeze-sha256',required=True)
    parser.add_argument('--derived-profile-plan-sha256');parser.add_argument('--publication',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();study=root/STUDY
    assert sys.platform=='linux' and root.is_relative_to(DISK)
    publication=read(args.publication)
    assert publication['local_commit_sha']==publication['remote_commit_sha']
    assert len(publication['remote_commit_sha'])==40 and publication['remote_SHA_verified'] is True
    assert publication['freeze_sha256']==args.freeze_sha256
    if args.kind=='profiles':
        assert sha(study/'raw_calibration_freeze_v1.json')==args.freeze_sha256
        assert sha(study/'calibration/derived_profile_plan_v1.json')==args.derived_profile_plan_sha256
        assert publication['derived_profile_plan_sha256']==args.derived_profile_plan_sha256
        assert read(study/'calibration/baseline_exit_v1.json')['returncode']==0
        for job in read(study/'calibration/derived_profile_plan_v1.json')['profile_jobs']:
            assert sha(study/job['arrival'])==job['arrival_sha256']
        phases=['profiles'];relative='calibration'
    else:
        assert sha(study/'formal_freeze_v1.json')==args.freeze_sha256
        assert read(study/'calibration/profiles_exit_v1.json')['returncode']==0
        phases=['qwen','cross','gate'];relative='formal'
    for phase in phases:
        for kind in ('launch','execution_state','exit'):
            assert not (study/relative/f'{phase}_{kind}_v1.json').exists(),'Do not relaunch an attempted phase'
    snapshot=resource_snapshot();assert not foreign_pids(snapshot),'Wait for exclusive GPUs'
    supervisor=study/relative/f'{args.kind}_supervisor_launch_v1.json';assert not supervisor.exists()
    write(supervisor,dict(supervisor_pid=os.getpid(),kind=args.kind,phases=phases,started_epoch_s=time.time(),
        source_sha256=sha(Path(__file__)),publication_path=str(args.publication.relative_to(root)),publication_sha256=sha(args.publication),
        initial_GPU_resources=snapshot,never_restart_failed_or_completed_phase=True))
    for phase in phases:
        if args.kind=='profiles':
            command=[PY,'-B',str(root/'scripts/tsc_revision_final_raw_worker_v1.py'),'--root',str(root),
                '--phase','profiles','--freeze-sha256',args.freeze_sha256,'--derived-profile-plan-sha256',args.derived_profile_plan_sha256]
        else:
            command=[PY,'-B',str(root/'scripts/tsc_revision_final_serving_worker_v1.py'),'--root',str(root),
                '--phase',phase,'--freeze-sha256',args.freeze_sha256]
        with (study/relative/f'{phase}_worker_v1.log').open('xb') as handle:
            process=subprocess.Popen(command,cwd=root,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT)
            write(study/relative/f'{phase}_launch_v1.json',dict(supervisor_pid=os.getpid(),worker_pid=process.pid,
                command=command,started_epoch_s=time.time(),freeze_sha256=args.freeze_sha256))
            status=process.wait()
        write(study/relative/f'{phase}_exit_v1.json',dict(returncode=status,ended_epoch_s=time.time()))
        if status:raise SystemExit(status)
    write(study/relative/f'{args.kind}_supervisor_exit_v1.json',dict(returncode=0,ended_epoch_s=time.time(),phases=phases))


if __name__=='__main__':main()
