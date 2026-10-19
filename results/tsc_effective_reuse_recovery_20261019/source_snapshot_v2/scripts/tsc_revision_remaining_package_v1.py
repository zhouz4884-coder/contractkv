"""Package audited existing evidence and a clearly unexecuted replay protocol."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,zipfile

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'results/tsc_revision_remaining_audit_20261018'
REPLAY=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'

def main():
    files=set()
    for directory in [AUDIT,REPLAY]:
        files.update(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='artifact_manifest_v1.json')
    files.update((ROOT/'scripts').glob('tsc_revision_*remaining*v1.py'))
    files.update((ROOT/'scripts').glob('tsc_tableIII_*v1.py'))
    for rel in ['docs/tsc_revision_remaining_work_audit_20261018_zh.md',
        'scripts/summarize_submission_supplement.py','scripts/summarize_tsc_submission_closure.py',
        'results/tsc_revision_evidence_closure_20261017/tableIII_audit/matched_cost_per_repeat_v1.csv',
        'results/submission_supplement/common_ruler_cross_model_bootstrap_v0.json',
        'results/tsc_service/service_locality_confidence_intervals_v0.csv',
        'results/tsc_service/service_locality_aggregate_v0.csv',
        'results/tsc_closure/real_task_open_loop_summary_v1.json',
        'results/tsc_revision_evidence_closure_20261017/manifest_audit/client_binding_boundary_v1.json']:
        files.add(ROOT/rel)
    assert all(p.is_file() for p in files)
    # Inspect the local vault value in memory only; never copy it into artifacts.
    spec=importlib.util.spec_from_file_location('vault',Path.home()/'.codex/local-tools/contractkv_ssh_credential.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    needle=module.get().encode()
    for p in files:
        data=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
        assert needle not in data,'Credential detected in candidate artifact'
    report={'schema_version':'contractkv.remaining-evidence-package.v1','new_GPU_requests':0,'GPU_replay_completed':False,
        'replay_future_pairs_planned':4725,'replay_wait_condition':'User elected to wait until RevBatch releases both GPUs.',
        'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]}
    manifest=AUDIT/'artifact_manifest_v1.json'
    if manifest.exists():raise FileExistsError(manifest)
    manifest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');files.add(manifest)
    output=ROOT/'submission/ContractKV_remaining_evidence_and_cost_replay_20261018.zip'
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as z:
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes()
    print(json.dumps({'files':len(files),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'credential_scan':'PASS','GPU_measurements_in_package':0}))

if __name__=='__main__':main()
