"""Deploy frozen source bytes and perform a read-only resource check only."""
from pathlib import Path
import hashlib,importlib.util,json

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'
REMOTE='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv'

def main():
    spec=importlib.util.spec_from_file_location('vault',Path.home()/'.codex/local-tools/contractkv_ssh_credential.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);c=m.ssh_client();s=c.open_sftp()
    bundle=ROOT/'.artifacts/tableIII_launch_bundle_v1.zip';digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
    remote_bundle=REMOTE+'/.artifacts/tableIII_launch_bundle_v1.zip'
    try:s.mkdir(REMOTE+'/.artifacts')
    except OSError:pass
    try:
        with s.open(remote_bundle,'rb') as f:existing=f.read()
        assert hashlib.sha256(existing).hexdigest()==digest,'A different deployment bundle already exists; do not overwrite it'
    except FileNotFoundError:s.put(str(bundle),remote_bundle)
    state=json.loads((STUDY/'execution_state_v1.json').read_text(encoding='utf-8'))
    code='ROOT='+repr(REMOTE)+'\nBUNDLE='+repr(remote_bundle)+'\nEXPECTED='+repr(digest)+'\nINITIAL='+repr(state)+'\n'+r'''
from pathlib import Path
import hashlib,json,subprocess,zipfile
root=Path(ROOT).resolve();bundle=Path(BUNDLE)
assert root.is_relative_to(Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9'))
assert hashlib.sha256(bundle.read_bytes()).hexdigest()==EXPECTED
with zipfile.ZipFile(bundle) as z:
    manifest=json.loads(z.read('results/tsc_tableIII_fullcost_replay_20261018/launch_bundle_manifest_v1.json'))
    expected={r['path']:r for r in manifest['files']}
    for name in z.namelist():
        p=(root/name).resolve();assert p.is_relative_to(root)
        data=z.read(name)
        if name in expected:assert hashlib.sha256(data).hexdigest()==expected[name]['sha256']
        p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists():assert p.read_bytes()==data, 'Existing source differs: '+name
        else:
            with p.open('xb') as f:f.write(data)
study=root/'results/tsc_tableIII_fullcost_replay_20261018';state=study/'execution_state_v1.json'
if not state.exists():
    with state.open('x',encoding='utf-8') as f:f.write(json.dumps(INITIAL,indent=2)+'\n')
result=subprocess.run(['/home/user/miniconda3/envs/contractkv-cu128/bin/python','-B',str(root/'scripts/tsc_tableIII_fullcost_worker_v1.py'),'--root',str(root),'--mode','check'],cwd=root,capture_output=True,text=True)
assert result.returncode in (0,75),(result.returncode,result.stderr)
print(json.dumps({'source_files_verified':len(expected),'bundle_sha256':EXPECTED,'read_only_check_returncode':result.returncode,'check_stdout':result.stdout,'check_stderr':result.stderr,'model_inference_started_by_deployment':False}))
'''
    i,o,e=c.exec_command('/home/user/miniconda3/envs/contractkv-cu128/bin/python -',timeout=60)
    i.write(code);i.channel.shutdown_write();data=o.read();err=e.read().decode('utf-8','replace')
    assert o.channel.recv_exit_status()==0,err
    record=json.loads(data)
    (STUDY/'deployment_receipt_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record));s.close();c.close()

if __name__=='__main__':main()
