"""Read-only recovery of existing CPU audit inputs; no model/server invocation."""
from pathlib import Path
import gzip, hashlib, importlib.util, json, re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tsc_revision_remaining_audit_20261018'
REMOTE='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/'

def main():
    helper=Path(r'C:\Users\LENOVO\.codex\local-tools\contractkv_ssh_credential.py')
    spec=importlib.util.spec_from_file_location('ckvault',helper)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    client=mod.ssh_client();sftp=client.open_sftp()
    inventory=json.loads((OUT/'remote_inventory_v1.json').read_text(encoding='utf-8'))
    paths=[]
    for entries in inventory.values():
        for e in entries:
            p=e['path']
            ruler=(re.search(r'(common_ruler/(qwen|mistral)|ruler_extended)/repeat[123]/(raw-order|contractkv-full)\.jsonl$',p) is not None)
            locality=(re.search(r'locality_cells/qwen_g25_r[123]_(D0-native-apc|D2-template-contractkv)_fp8/(raw|summary)\.jsonl$',p) is not None)
            llama=('llama_broad_generalization_r3/repeat' in p and p.endswith('contract_metrics.jsonl')) or ('logs/llama_broad_generalization_r3/r' in p and p.endswith('contract_server.log'))
            if ruler or locality or llama:paths.append((p,'locality_projection' if locality and p.endswith('/raw.jsonl') else 'verbatim_gzip'))
    paths.append(('results/submission_supplement/ruler_extended_sessions_v0.jsonl','verbatim_gzip'))
    manifest=[]
    for p,mode in sorted(set(paths)):
        target=OUT/'inputs'/(p+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        before=sftp.stat(REMOTE+p)
        with sftp.open(REMOTE+p,'rb') as f:data=f.read()
        after=sftp.stat(REMOTE+p)
        assert (before.st_size,before.st_mtime)==(after.st_size,after.st_mtime)
        assert len(data)==before.st_size
        projected=data
        if mode=='locality_projection':
            keys=['service_template_id','session_id','ttft_ms','new_prefill_tokens']
            projected=(''.join(json.dumps({k:r[k] for k in keys},ensure_ascii=True)+'\n' for r in (json.loads(line) for line in data.splitlines() if line.strip()))).encode()
        compressed=gzip.compress(projected,mtime=0)
        if target.exists():assert target.read_bytes()==compressed
        else:target.write_bytes(compressed)
        manifest.append({'remote_path':p,'remote_bytes':len(data),'remote_mtime':before.st_mtime,
                         'remote_sha256':hashlib.sha256(data).hexdigest(),'mode':mode,
                         'local_path':target.relative_to(ROOT).as_posix(),'gzip_sha256':hashlib.sha256(compressed).hexdigest(),
                         'decompressed_sha256':hashlib.sha256(projected).hexdigest()})
        print(p,flush=True)
    (OUT/'retrieval_manifest_v1.json').write_text(json.dumps({'new_GPU_requests':0,'files':manifest},indent=2)+'\n',encoding='utf-8')
    sftp.close();client.close()
    print('Recovered',len(manifest),'existing files/projections')

if __name__=='__main__':main()
