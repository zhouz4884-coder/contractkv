"""Supervise one bounded budget condition; never resume/relaunch a cell."""
import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_mechanism_budget256_20261018'
COMMAND=['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/tsc_revision_budget256_worker_v2.py', '--root', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv', '--mode', 'execute', '--freeze-sha256', '0d4c2ec5c4aa88fc4426e7f0d16838a77eab7680aed258d144ece406a643c378', '--check-receipt-sha256', 'afb4e6683af120941c199f668ceb4b1436d322fbd4c077c3dc09cea8014fdd9c']
for name in ['formal_budget_v2_launch_v1.json','formal_budget_v2_exit_v1.json','execution_state_v1.json']:
    assert not (STUDY/name).exists(), 'A budget execution already exists; monitor it instead'
parent=ROOT/'results/tsc_revision_mechanism_controls_20261018'
assert json.loads((parent/'formal_continuation_v5_exit_v1.json').read_text())['returncode']==0
assert (parent/'raw_evidence_archive_manifest_v1.json').exists()
with (STUDY/'formal_budget_v2_worker.log').open('xb') as log:
    process=subprocess.Popen(COMMAND,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    launch=dict(supervisor_pid=os.getpid(),worker_pid=process.pid,command=COMMAND,started_epoch_s=time.time(),preserve_original_64_token_matrix=True)
    with (STUDY/'formal_budget_v2_launch_v1.json').open('x') as f:json.dump(launch,f,indent=2);f.write('\n')
    returncode=process.wait()
with (STUDY/'formal_budget_v2_exit_v1.json').open('x') as f:json.dump(dict(returncode=returncode,ended_epoch_s=time.time()),f,indent=2);f.write('\n')
raise SystemExit(returncode)
