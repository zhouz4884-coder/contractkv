"""Freeze isolated orchestration before measurement; package no model weights."""
from pathlib import Path
import hashlib,importlib.util,json,zipfile

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    protocol=json.loads((STUDY/'protocol_v1.json').read_text(encoding='utf-8'))
    freeze=json.loads((STUDY/'freeze_v1.json').read_text(encoding='utf-8'))
    for r in protocol['archived_source_files']+protocol['input_files']+freeze['files']:
        assert sha(ROOT/r['path'])==r['sha256'],r['path']
    new_paths=[ROOT/'scripts/tsc_tableIII_fullcost_worker_v1.py',ROOT/'scripts/tsc_tableIII_orchestration_CPU_check_v1.py',
        ROOT/'scripts/tsc_tableIII_build_launch_bundle_v1.py',STUDY/'orchestration_CPU_check_v1.json',
        ROOT/'scripts/tsc_tableIII_deploy_launch_bundle_v1.py',STUDY/'LAUNCH_STATUS_20261018.md',
        STUDY/'analysis_plan_v1.json',STUDY/'prior_model_registry_v1.json']
    addendum={'schema_version':'contractkv.original-sample-launch-addendum.v1','before_GPU_measurement':True,
        'original_protocol_sha256':sha(STUDY/'protocol_v1.json'),'original_timing_freeze_sha256':sha(STUDY/'freeze_v1.json'),
        'changes':'Add isolated fresh-server orchestration, original timeout arguments, model/runtime preflight receipt gate, final backend drain accounting, and fixed analysis plan. Archived inputs and timing driver remain unchanged.',
        'new_GPU_measurements':0,'no_new_candidate_margin_scoring_or_source_selection':True,
        'backend_historical_byte_identity_established':False,
        'preflight_gate':'CPU preflight stops with a hashed receipt. Retrieve and archive it before execute; execute requires its exact SHA and revalidates files/model metadata/runtime inventory.',
        'failure_policy':'Preserve failed/partial pairs; after documented infrastructure repair use a separate attempt. Reuse only entire valid pairs, in chronological order, never by performance.',
        'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in new_paths]}
    path=STUDY/'launch_addendum_v1.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf-8'))==addendum
    else:path.write_text(json.dumps(addendum,indent=2)+'\n',encoding='utf-8')
    files={ROOT/r['path'] for r in protocol['archived_source_files']+protocol['input_files']+freeze['files']}
    files.update(new_paths+[path,STUDY/'freeze_v1.json',STUDY/'RUNBOOK_zh.md'])
    spec=importlib.util.spec_from_file_location('vault',Path.home()/'.codex/local-tools/contractkv_ssh_credential.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);needle=m.get().encode()
    for p in files:assert needle not in p.read_bytes(),'Credential detected in source bundle'
    manifest={'schema_version':'contractkv.original-sample-launch-bundle.v1','new_GPU_measurements':0,
        'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]}
    target=STUDY/'launch_bundle_manifest_v1.json'
    if target.exists():assert json.loads(target.read_text(encoding='utf-8'))==manifest
    else:target.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    files.add(target);out=ROOT/'.artifacts/tableIII_launch_bundle_v1.zip'
    if out.exists():raise FileExistsError(out)
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(out) as z:
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes()
    print(json.dumps({'bundle':str(out),'files':len(files),'bytes':out.stat().st_size,'sha256':sha(out),'model_inference_calls':0}))

if __name__=='__main__':main()
