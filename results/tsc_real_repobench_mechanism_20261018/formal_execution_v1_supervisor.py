import json,os,subprocess,time
from pathlib import Path
ROOT=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
STUDY=ROOT/'results/tsc_real_repobench_mechanism_20261018'
COMMAND=['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/tsc_revision_real_repo_worker_v1.py', '--root', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv', '--mode', 'execute', '--freeze-sha256', '2cc95d89e84875ebf132fabbac1eefbb2a69190fdd4d8daca46305e5df4427b3', '--check-receipt-sha256', 'fabb4bb5656943da395cc5ce171238ae825def27ced37eaaa486a41b479fa426']
for name in ['formal_execution_v1_launch.json','formal_execution_v1_exit.json','execution_state_v1.json']:
    assert not (STUDY/name).exists(), 'Monitor existing execution; never repeat a completed cell'
budget=ROOT/'results/tsc_mechanism_budget256_20261018'
assert json.loads((budget/'formal_budget_v2_exit_v1.json').read_text())['returncode']==0
with (STUDY/'formal_execution_v1_worker.log').open('xb') as log:
    process=subprocess.Popen(COMMAND,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    with (STUDY/'formal_execution_v1_launch.json').open('x') as f:
        json.dump(dict(supervisor_pid=os.getpid(),worker_pid=process.pid,command=COMMAND,started_epoch_s=time.time()),f,indent=2)
    status=process.wait()
with (STUDY/'formal_execution_v1_exit.json').open('x') as f:
    json.dump(dict(returncode=status,ended_epoch_s=time.time()),f,indent=2)
raise SystemExit(status)
