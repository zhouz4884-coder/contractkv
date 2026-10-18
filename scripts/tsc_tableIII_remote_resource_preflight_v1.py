from pathlib import Path
import importlib.util,json
spec=importlib.util.spec_from_file_location('vault',r'C:\Users\LENOVO\.codex\local-tools\contractkv_ssh_credential.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
c=mod.ssh_client()
code=r'''
from pathlib import Path
import json,subprocess,hashlib
r=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
out={'host':subprocess.check_output(['hostname'],text=True).strip(),'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu','--format=csv,noheader'],text=True),'processes':subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'],text=True),'files':{}}
for rel in ['third_party/vllm-contractkv/vllm/entrypoints/openai/api_server.py','third_party/vllm-contractkv-phase19c/vllm/entrypoints/openai/api_server.py','third_party/vllm-contractkv/vllm/v1/core/sched/scheduler.py','third_party/vllm-contractkv-phase19c/vllm/v1/core/sched/scheduler.py','results/end_to_end/phase19b_untouched_sessions_v0.jsonl','results/mistral/heldout_sealed_sessions_v0.jsonl','results/scale_up/qwen3_14b_tp2_v0/frozen_sessions_v0.jsonl','results/scale_up/qwen3_14b_tp2_v0/policy_transfer_manifest_v0.json','results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl','results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json']:
 p=r/rel
 if p.exists():
  b=p.read_bytes();out['files'][rel]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'ephemeral_shadow_marker':b'CONTRACTKV_EPHEMERAL' in b,'verify_route':b'/v1/contractkv/verify' in b}
 else:out['files'][rel]={'missing':True}
for model in ['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct','Qwen3-14B']:
 p=r.parent.parent/'models'/model
 out[model]={'model_path':str(p),'exists':p.exists(),'shards':len(list(p.glob('*.safetensors')))}
print(json.dumps(out))
'''
i,o,e=c.exec_command('/home/user/miniconda3/envs/contractkv-cu128/bin/python -',timeout=60)
i.write(code);i.channel.shutdown_write();data=o.read();err=e.read().decode('utf-8','replace');assert o.channel.recv_exit_status()==0,err
target=Path('results/tsc_revision_remaining_audit_20261018/legacy_replay_preflight_v1.json');target.write_bytes(data)
d=json.loads(data);print(json.dumps(d,indent=2));c.close()
