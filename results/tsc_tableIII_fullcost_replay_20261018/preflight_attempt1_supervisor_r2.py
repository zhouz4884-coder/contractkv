from pathlib import Path
import os,json,subprocess,time
from datetime import datetime,timezone
root=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv');s=root/'results/tsc_tableIII_fullcost_replay_20261018'
env=os.environ.copy();cache=s/'preflight_volume_cache';tmp=cache/'tmp';tmp.mkdir(parents=True,exist_ok=True)
env.update(TMPDIR=str(tmp),XDG_CACHE_HOME=str(cache/'xdg'),HF_HOME=str(cache/'hf'),HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),TORCH_HOME=str(cache/'torch'),TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_'/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv'=str(cache/'vllm'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
cmd=['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',str(root/'scripts/tsc_tableIII_fullcost_worker_v1.py'),'--root',str(root),'--mode','preflight']
with (s/'preflight_attempt1_worker_r2.log').open('xb') as log:
 p=subprocess.Popen(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 record={'time_utc':datetime.now(timezone.utc).isoformat(),'pid':p.pid,'supervisor_pid':os.getpid(),'command':cmd,'mode':'preflight','model_inference_started':False}
 (s/'preflight_attempt1_launch_r2.json').write_text(json.dumps(record,indent=2)+'\n')
 code=p.wait();record.update(returncode=code,finished_at_utc=datetime.now(timezone.utc).isoformat());(s/'preflight_attempt1_exit_r2.json').write_text(json.dumps(record,indent=2)+'\n')
