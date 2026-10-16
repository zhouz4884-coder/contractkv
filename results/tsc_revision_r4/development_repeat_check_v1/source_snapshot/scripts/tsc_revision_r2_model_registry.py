"""Point-in-time full checkpoint/tokenizer hashes before new calibration/validation."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    if a.output.exists(): raise RuntimeError('Preserve existing model registry')
    a.output.parent.mkdir(parents=True,exist_ok=True); lock=a.output.with_suffix('.partial')
    with lock.open('x') as stream:stream.write('Full hashes in progress; this is not a completion record\n')
    models=[]
    for key,name in [('qwen','Qwen3-8B'),('mistral','Mistral-7B-Instruct-v0.3'),('llama','Llama-3.1-8B-Instruct')]:
        base=a.models/name; index=base/'model.safetensors.index.json'
        shards=sorted(set(json.loads(index.read_text(encoding='utf-8'))['weight_map'].values()))
        historical=json.loads((a.root/f'results/tsc_revision_r1r/validation/cells/single-session_{key}_raw-order_r1/manifest.json').read_text(encoding='utf-8'))
        files=[]
        meta=('config.json','generation_config.json','tokenizer_config.json','tokenizer.json','tokenizer.model',
              'special_tokens_map.json','added_tokens.json','chat_template.jinja','model.safetensors.index.json')
        for filename in [x for x in meta if (base/x).is_file()]+shards:
            path=base/filename; stat=path.stat(); digest=sha(path)
            if path.stat().st_size!=stat.st_size or path.stat().st_mtime_ns!=stat.st_mtime_ns: raise RuntimeError('Model file changed while hashing')
            files.append({'file':filename,'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'sha256':digest})
            print(json.dumps({'model':name,'hashed_file':filename,'bytes':stat.st_size}),flush=True)
        byname={r['file']:r for r in files}
        if any(byname[r['file']]['sha256']!=r['sha256'] for r in historical['model_files']): raise RuntimeError('Historical model metadata mismatch')
        identity=[{k:r[k] for k in ('file','bytes','sha256')} for r in files]
        models.append({'model':name,'key':key,'model_path':str(base.resolve()),'files':files,
                       'artifact_identity_sha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
                       'historically_recorded_metadata_hashes_match':True,'historical_full_weight_hash_identity_not_claimed':True})
    record={'schema_version':'tsc-r2.full-model-registry.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'execution_complete':True,'models':models,'scope':'Point-in-time complete weight/tokenizer hashes; not proof of uninterrupted historical file identity.'}
    lock.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8'); lock.replace(a.output)
    print(json.dumps({'complete_models':len(models),'registry_sha256':sha(a.output)}),flush=True)


if __name__=='__main__': main()
