ROOT_PATH='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv'
COMMAND=['/home/user/miniconda3/envs/contractkv-cu128/bin/python', '-B', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/tsc_tableIII_fullcost_worker_v2.py', '--root', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv', '--mode', 'preflight', '--attempt', '2', '--repair-record', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/tsc_tableIII_fullcost_replay_20261018/infrastructure_repair_v2.json', '--reuse-model-registry', '/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/tsc_tableIII_fullcost_replay_20261018/launch_attempt1_preflight/model_registry_v1.json', '--reuse-model-registry-sha256', 'f498ce77473d08efd6672b8cc729f9d0b0d2d738ecd69911cdfae4def91e72eb']
PREFIX='preflight_attempt2'
from pathlib import Path
import os,json,subprocess
from datetime import datetime,timezone
root=Path(ROOT_PATH);s=root/'results/tsc_tableIII_fullcost_replay_20261018'
env=os.environ.copy();cache=s/'preflight_volume_cache';tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
env.update(TMPDIR=str(tmp),XDG_CACHE_HOME=str(cache/'xdg'),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
with (s/(PREFIX+'_worker.log')).open('xb') as log:
 p=subprocess.Popen(COMMAND,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 record={'time_utc':datetime.now(timezone.utc).isoformat(),'pid':p.pid,'supervisor_pid':os.getpid(),'command':COMMAND,'mode':'preflight','model_inference_started':False}
 (s/(PREFIX+'_launch.json')).write_text(json.dumps(record,indent=2))
 code=p.wait();record.update(returncode=code,finished_at_utc=datetime.now(timezone.utc).isoformat());(s/(PREFIX+'_exit.json')).write_text(json.dumps(record,indent=2))
