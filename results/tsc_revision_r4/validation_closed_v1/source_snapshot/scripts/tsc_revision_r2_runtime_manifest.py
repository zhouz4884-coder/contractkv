"""Record exact second-stage backend, tokenizer, native ABI and gate settings."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    for key in ('root','model','sessions','freeze','output'): p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cell',required=True); p.add_argument('--gpu',required=True); a=p.parse_args()
    if a.output.exists(): raise RuntimeError('Preserve existing runtime manifest')
    root=a.root.resolve(); frozen=json.loads(a.freeze.read_text(encoding='utf-8'))
    for item in frozen['files']:
        if sha(root/item['path'])!=item['sha256'] or sha(a.freeze.parent/'source_snapshot'/item['path'])!=item['sha256']:
            raise ValueError('Frozen second-stage file changed: '+item['path'])
    backend=json.loads((root/'configs/tsc_revision_r2_backend_commitment_v1.json').read_text(encoding='utf-8'))
    backend_root=root/'third_party'/backend['new_backend']
    spec=importlib.util.find_spec('vllm')
    if spec is None or not Path(spec.origin).resolve().is_relative_to(backend_root.resolve()):
        raise ValueError('Wrong imported vLLM backend')
    for item in backend['source_files']:
        if sha(backend_root/item['file'])!=item['after_sha256']: raise ValueError('New backend source changed')
    for item in backend['project_dependencies']:
        if sha(root/item['path'])!=item['sha256']: raise ValueError('New backend helper changed')
    for item in backend['native_extensions']:
        if sha(backend_root/item['relative_path'])!=item['sha256']: raise ValueError('Native ABI mismatch')
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_validation_manifest.py'),'--root',str(root),
                    '--model',str(a.model),'--sessions',str(a.sessions),'--cell',a.cell,'--output',str(a.output)],check=True)
    record=json.loads(a.output.read_text(encoding='utf-8'))
    record['schema_version']='tsc-r2.runtime-cell.v1'
    record['inherited_r1r_source_guard_freeze_sha256']=record['freeze_sha256']
    record['freeze_sha256']=sha(a.freeze)
    record['backend_commitment_sha256']=sha(root/'configs/tsc_revision_r2_backend_commitment_v1.json')
    record['imported_vllm_source']=spec.origin; record['declared_gpu_lane']=a.gpu
    record['native_extensions']=backend['native_extensions']
    record['tokenizer_and_generation_files']=[{'file':name,'bytes':(a.model/name).stat().st_size,'sha256':sha(a.model/name)}
        for name in ('config.json','generation_config.json','tokenizer_config.json','tokenizer.json','tokenizer.model',
                     'special_tokens_map.json','added_tokens.json','chat_template.jinja') if (a.model/name).is_file()]
    import os
    record['gate_and_trace_environment']={key:os.environ.get(key) for key in (
        'CONTRACTKV_MIN_RAW_TOKEN_MARGIN','CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN','CONTRACTKV_MIN_CANDIDATE_MARGIN',
        'CONTRACTKV_MAX_DEGRADATION','CONTRACTKV_MIN_STOP_MARGIN','CONTRACTKV_R2_EXECUTION_TRACE','CONTRACTKV_R2_VERIFY_TRACE')}
    a.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cell':a.cell,'new_backend_source_verified':True,'native_hashes_verified':len(backend['native_extensions']),
                      'tokenizer_and_generation_files':len(record['tokenizer_and_generation_files'])}))


if __name__=='__main__': main()
