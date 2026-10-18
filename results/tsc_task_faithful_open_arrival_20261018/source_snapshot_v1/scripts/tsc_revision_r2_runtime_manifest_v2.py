"""Extend the frozen runtime recorder with pre-run full checkpoint identities."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    for key in ('root','model','sessions','freeze','output','registry'): p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cell',required=True); p.add_argument('--gpu',required=True); a=p.parse_args()
    registry=json.loads(a.registry.read_text(encoding='utf-8'))
    if not registry['execution_complete']: raise ValueError('Incomplete checkpoint registry')
    model=next(r for r in registry['models'] if Path(r['model_path']).resolve()==a.model.resolve())
    metadata_count=weights_count=0
    for item in model['files']:
        path=a.model/item['file']; stat=path.stat()
        if stat.st_size!=item['bytes'] or stat.st_mtime_ns!=item['mtime_ns']: raise ValueError('Registered model file metadata changed')
        if path.suffix=='.safetensors': weights_count+=1
        else:
            if sha(path)!=item['sha256']: raise ValueError('Tokenizer/config/index bytes changed')
            metadata_count+=1
    command=[sys.executable,str(Path(__file__).with_name('tsc_revision_r2_runtime_manifest.py'))]
    for key in ('root','model','sessions','freeze','output','cell','gpu'):
        command+=['--'+key,str(getattr(a,key))]
    subprocess.run(command,check=True)
    record=json.loads(a.output.read_text(encoding='utf-8')); record['schema_version']='tsc-r2.runtime-cell.v2'
    record['model_registry_sha256']=sha(a.registry); record['model_artifact_identity_sha256']=model['artifact_identity_sha256']
    record['registry_point_in_time_full_weight_hashes_present']=True
    record['python_version']=sys.version;record['platform']=platform.platform()
    record['installed_distribution_versions']={d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}
    record['numerical_environment']={key:os.environ.get(key) for key in (
        'CUBLAS_WORKSPACE_CONFIG','NVIDIA_TF32_OVERRIDE','TORCH_ALLOW_TF32_CUBLAS_OVERRIDE',
        'CUDA_LAUNCH_BLOCKING','PYTORCH_CUDA_ALLOC_CONF','OMP_NUM_THREADS')}
    record['per_cell_registry_consistency']={'metadata_files_sha256_rechecked':metadata_count,
                                             'weight_shards_size_and_mtime_rechecked':weights_count,
                                             'full_weight_hashes_from_pre_run_registry_not_rehashed_per_cell':True}
    a.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'model':model['model'],'registered_weight_shards':weights_count,'metadata_hashes_rechecked':metadata_count}))


if __name__=='__main__': main()
