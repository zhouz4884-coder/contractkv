ROOT_PATH='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv'
COMMAND=['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/tsc_tableIII_fullcost_worker_v2.py', '--root', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv', '--mode', 'execute', '--attempt', '2', '--repair-record', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/tsc_tableIII_fullcost_replay_20261018/infrastructure_repair_v2.json', '--preflight-receipt-sha256', 'e19c393236c1eb75d29c9c9f1440d5c595b88751350e4274033f6eee5a5a8acf']
from pathlib import Path
import os,json,subprocess
from datetime import datetime,timezone
root=Path(ROOT_PATH);s=root/'results/tsc_tableIII_fullcost_replay_20261018'
env=os.environ.copy();cache=s/'formal_attempt2_driver_cache';tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
for name in ['TORCHINDUCTOR_CACHE_DIR','TORCH_COMPILE_CACHE_DIR']:env.pop(name,None)
env.update(TMPDIR=str(tmp),XDG_CACHE_HOME=str(cache/'xdg'),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),CUDA_CACHE_PATH=str(cache/'cuda'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
with (s/'formal_attempt2_worker.log').open('xb') as log:
 p=subprocess.Popen(COMMAND,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 record={'time_utc':datetime.now(timezone.utc).isoformat(),'pid':p.pid,'supervisor_pid':os.getpid(),'command':COMMAND,'mode':'execute','model_result_status':'not yet observed','cache_root':str(cache),'CUDA_CACHE_PATH':env['CUDA_CACHE_PATH'],'explicit_inductor_cache_removed_for_cell_TMPDIR_isolation':True}
 (s/'formal_attempt2_launch.json').write_text(json.dumps(record,indent=2))
 code=p.wait();record.update(returncode=code,finished_at_utc=datetime.now(timezone.utc).isoformat());(s/'formal_attempt2_exit.json').write_text(json.dumps(record,indent=2))
