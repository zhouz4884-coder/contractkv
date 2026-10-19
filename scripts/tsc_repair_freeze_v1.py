"""Freeze the bounded transport repair after CPU validation, before model output."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_repair_authorized_worker_v1 import adapted_cell
from scripts.contractkv_authorized_requests import REGISTRAR_ADAPTER_PROOF

STUDY=Path('results/tsc_authorization_task_repair_20261019')
PARENT=Path('results/tsc_revision_mechanism_controls_20261018')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')


def main(root):
    study=root/STUDY
    assert not (study/'freeze_v1.json').exists()
    cases=read(study/'inputs_v1/cases_by_model_v1.json')
    selection=read(study/'selection_plan_v1.json')
    prep=read(study/'inputs_v1/preparation_receipt_v1.json')
    assert prep['selected_sources']==6 and prep['selection_plan_sha256']==sha(study/'selection_plan_v1.json')
    for row in prep['files']:assert sha(root/row['path'])==row['sha256']
    for model,value in cases.items():
        assert len(value['real_cases'])==6
        assert len({c['source_group'] for c in value['real_cases']})==6
        if model!='Qwen3-8B':assert all(c['level']=='L0' for c in value['real_cases'] if c['family']=='RepoBench')
    cmd=[sys.executable,'-B','-m','pytest','-q','tests/test_tsc_repair_authorized_client.py',
         'tests/test_contractkv_authorized_cache_identity.py','tests/test_tsc_revision_r2_admission.py']
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    with (study/'final_CPU_controls_v1.log').open('x',encoding='utf-8') as f:f.write(result.stdout)
    assert result.returncode==0,result.stdout
    write(study/'final_CPU_controls_v1.json',dict(returncode=0,command=cmd,result=result.stdout,
        new_GPU_requests=0,CPU_mock_transport_not_efficacy_evidence=True,
        registrar_adapter_proof=REGISTRAR_ADAPTER_PROOF))
    snapshot=study/'source_snapshot';assert not snapshot.exists()
    shutil.copytree(root/PARENT/'source_snapshot',snapshot)
    new_sources=['scripts/contractkv_cache_identity.py','scripts/contractkv_authorized_requests.py',
        'scripts/tsc_repair_authorized_client_v1.py','scripts/tsc_repair_authorized_worker_v1.py',
        'scripts/tsc_revision_r3_output_contract.py','scripts/tsc_revision_incomplete_reference_fix_v5.py']
    for rel in new_sources:
        target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==(root/rel).read_bytes()
        else:shutil.copyfile(root/rel,target)
    protocol={**selection, 'schema_version':'contractkv.authorized-cache-repair-formal.v1',
        'selected_source_groups':prep['selected_source_groups'],
        'per_cell_business_requests':92,'total_formal_business_requests':828,
        'per_cell_qualification_decisions':15,'maximum_GPU_verification_RPCs':135,
        'per_cell_stale_identity_denials':7,'source_cases_SHA256':sha(study/'inputs_v1/cases_by_model_v1.json'),
        'legacy_control':'Same real request builder with Raw salt omitted and compiled policy:namespace salt. Existing SingleShot plus v5 INCOMPLETE fix; output guard and inheritedL0 retained.',
        'repair':'Only auth cache identity: trusted HMAC scope on all business and verification wire calls; current epoch revalidated each dispatch.',
        'physical_proof':'Actual engine-native lookup_before/return, block hash chains, cached block entries, verification publication and output IDs. No engine restart or cache flush within a cell.',
        'clock':'Full serial micro-workflow includes online preparation/binding/Raw/generation/verification/failure and waits. Offline source packing/tokenization and server startup excluded identically and separately reported. The extra synthetic negative verification is not a real-task speedup control.',
        'uncertainty':'All source/model/repeat/request results retained; limited-source descriptive measurements. No open-arrival or population Goodput CI claim, no pooling synthetic tasks with true task quality.',
        'phase_order':'Legacy then authorized within each source, explicit cold/warm/native states; cross-phase prior residency prevents interpreting wall differences as a clean causal speedup. Structural authorization properties are primary.',
        'hypotheses':['same authorized group retains hit','cross-domain first native lookup uses distinct hash chain and no cross-group hit','new epoch does not inherit old hash chain; stale request rejected before backend','rejected verifier candidate adds no compiled published state','new real task scores/outputs and all costs are auditable'],
        'trust':'Internal trusted orchestrator only; salts do not detect trusted semantic mislabels, authenticate external callers, clear old blocks, or provide full process/timing isolation.'}
    write(study/'protocol_v1.json',protocol)
    files=[]
    paths=[p for p in snapshot.rglob('*') if p.is_file()]
    paths += [study/'protocol_v1.json',study/'selection_plan_v1.json',study/'inputs_v1/preparation_receipt_v1.json',study/'final_CPU_controls_v1.json']
    paths += [p for p in (study/'inputs_v1').iterdir() if p.is_file() and p.name!='preparation_receipt_v1.json']
    paths += [root/p for p in new_sources]+[root/'scripts/tsc_repair_freeze_v1.py',root/'scripts/tsc_revision_mechanism_worker_v3.py',root/'scripts/tsc_tableIII_fullcost_worker_v3.py']
    paths=list(dict.fromkeys(paths))
    for path in sorted(paths):files.append(dict(path=path.relative_to(root).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
    write(study/'freeze_v1.json',dict(schema_version='contractkv.authorization-repair-freeze.v1',files=files,
        parent_runtime_receipt_sha256=sha(root/PARENT/'preflight_v3/receipt_v1.json'),
        parent_full_model_SHA_registry=read(root/PARENT/'preflight_v3/model_asset_registry_v1.json')['origin_sha256'],
        worker_adapter_proof=adapted_cell()[1],registrar_adapter_proof=REGISTRAR_ADAPTER_PROOF,
        source_snapshot_files=len([p for p in snapshot.rglob('*') if p.is_file()]),
        unchanged_behavioral_and_PSTP_thresholds=True,new_GPU_requests_before_freeze=0))
    print(json.dumps(dict(freeze_sha256=sha(study/'freeze_v1.json'),files=len(files),formal_cells=9,total_business=828,CPU_controls=result.stdout.strip())))


if __name__=='__main__':main(Path.cwd())
