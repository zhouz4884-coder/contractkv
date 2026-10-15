"""Check the prospectively frozen client/runtime and record a validation cell."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    for name in ('root','model','sessions','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cell',required=True); a=p.parse_args()
    freeze=json.loads((a.root/'results/tsc_revision_r1r/validation/freeze_v1.json').read_text())
    for item in freeze['files']:
        if sha(a.root/item['path'])!=item['sha256']: raise RuntimeError('Frozen source changed: '+item['path'])
    index=a.model/'model.safetensors.index.json'
    shards=sorted(set(json.loads(index.read_text())['weight_map'].values()))
    if not all((a.model/s).is_file() and (a.model/s).stat().st_size>0 for s in shards): raise RuntimeError('Missing shard')
    record={'schema_version':'tsc-r1r.validation-cell.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'cell':a.cell,'freeze_sha256':sha(a.root/'results/tsc_revision_r1r/validation/freeze_v1.json'),
            'sessions_sha256':sha(a.sessions),'model_path':str(a.model),
            'model_files':[{'file':f,'sha256':sha(a.model/f)} for f in ('config.json','tokenizer_config.json','model.safetensors.index.json')],
            'shards':[{'file':s,'bytes':(a.model/s).stat().st_size} for s in shards],
            'packages':{k:importlib.metadata.version(k) for k in ('torch','vllm','transformers','triton','numpy')},
            'environment':{k:os.environ.get(k) for k in ('PYTHONPATH','CONTRACTKV_POLICY_HASH','CONTRACTKV_SHADOW_CHUNK_TOKENS','CONTRACTKV_SHADOW_ROUND_TOKENS')},
            'gpu_snapshot':subprocess.run(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.used,driver_version','--format=csv'],capture_output=True,text=True,check=True).stdout}
    a.output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__': main()
