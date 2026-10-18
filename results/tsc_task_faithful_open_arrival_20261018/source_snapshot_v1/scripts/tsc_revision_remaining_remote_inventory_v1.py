from pathlib import Path
import importlib.util, json

helper = Path(r'C:\Users\LENOVO\.codex\local-tools\contractkv_ssh_credential.py')
spec = importlib.util.spec_from_file_location('ckvault', helper)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
client = mod.ssh_client()
code = r'''
from pathlib import Path
import json
root=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv')
out={}
for rel in ['results/submission_supplement','results/tsc_service','results/cross_model/llama_broad_generalization_r3','logs/llama_broad_generalization_r3']:
 p=root/rel
 matches=[]
 if p.exists():
  for f in p.rglob('*'):
   if not f.is_file(): continue
   s=f.relative_to(root).as_posix()
   if ('locality_cells' in s and 'qwen_g25_' not in s): continue
   if ('ruler' in s or 'same_path' in s or 'same-path' in s or 'd0d1d2' in s or 'qwen_g25_' in s or 'llama_broad_generalization_r3' in s):
    matches.append({'path':s,'bytes':f.stat().st_size})
 out[rel]=matches
print(json.dumps(out))
'''
stdin, stdout, stderr = client.exec_command('/home/user/miniconda3/envs/contractkv-cu128/bin/python -', timeout=60)
stdin.write(code); stdin.channel.shutdown_write()
payload=stdout.read(); err=stderr.read().decode('utf-8','replace')
assert stdout.channel.recv_exit_status()==0, err
target=Path('results/tsc_revision_remaining_audit_20261018')
target.mkdir(parents=True,exist_ok=True)
(target/'remote_inventory_v1.json').write_bytes(payload)
data=json.loads(payload)
print(json.dumps({k:len(v) for k,v in data.items()}))
for vals in data.values():
 for v in vals:
  if 'raw.jsonl' in v['path'] or 'same' in v['path'] or 'ruler' in v['path'] and v['path'].endswith('jsonl'):
   print(v['path'],v['bytes'])
client.close()
