"""Archive completed measured data and traceable sources; exclude credentials."""
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableI_remeasurement_20261018'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8<<20),b''):h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--zip',type=Path,required=True)
    a=parser.parse_args();assert not a.zip.exists()
    primary=json.loads((STUDY/'analysis_v1/summary_v1.json').read_text(encoding='utf-8'))
    integrity=json.loads((STUDY/'analysis_v1/independent_integrity_v1.json').read_text(encoding='utf-8'))
    clusters=json.loads((STUDY/'analysis_v1/context_cluster_stats_v1.json').read_text(encoding='utf-8'))
    assert primary['execution_complete'] and primary['all_requests']==3750 and primary['future_requests']==3375
    assert integrity['status']=='PASS' and clusters['point_estimates_unchanged']
    freeze=json.loads((STUDY/'freeze.json').read_text())
    for r in freeze['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    for repeat in range(1,4):
        cell=STUDY/'cells'/f'raw_native_r{repeat}'
        record=json.loads((cell/'completion_v1.json').read_text())
        assert record['execution_complete'] and record['completed_requests']==1250
        assert sha(cell/'raw.jsonl.gz')==record['raw_sha256']
    files={p for p in STUDY.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='artifact_manifest_v1.json'}
    files.update(ROOT/r['path'] for r in freeze['files'])
    files.update((ROOT/'scripts').glob('tsc_tableI_*v1.py'))
    files.add(ROOT/'scripts/run_tsc_tableI_survey_v1.sh')
    files.update([ROOT/'docs/tsc_TableI_independent_measurement_completed_20261018_zh.md',
                  ROOT/'docs/tsc_TableI_upstream_and_remeasurement_20261018_zh.md',
                  ROOT/'results/tsc_revision_evidence_closure_20261017/tableI_lineage/lineage_audit.json',
                  ROOT/'results/tsc_revision_evidence_closure_20261017/tableI_lineage/first_table_insertion.tex'])
    aux=json.loads((STUDY/'auxiliary_existing_six_source_v1.json').read_text())
    files.add(ROOT/aux['original_aggregate_file'])
    files.update(ROOT/r['file'] for r in aux['underlying_ledger_files'])
    assert all(p.is_file() for p in files)
    # The vault is local; its content never becomes an artifact or command arg.
    spec=importlib.util.spec_from_file_location('local_credential',Path.home()/'.codex/local-tools/contractkv_ssh_credential.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    needle=module.get().encode()
    for path in files:
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rb') as stream:
            tail=b''
            for block in iter(lambda:stream.read(1<<20),b''):
                part=tail+block
                assert needle not in part,'Credential present in candidate artifact'
                tail=part[-len(needle):]
    manifest={'schema':'contractkv.tableI.completed-archive.v1',
              'preregistration_commit':'40e16ba06af8caef23fbf6a458480655ef881d7d',
              'all_source_requests':3750,'all_future_requests':3375,'registered_records':125,
              'exact_original_context_clusters':114,'all_recorded_outputs_retained':True,
              'original_TableI_numeric_lineage_recovered':False,
              'native_GPU_measurement_complete':True,'independent_integrity_pass':True,
              'original_ID_intervals_and_context_addendum_both_retained':True,
              'frozen_primary_files_unchanged':True,'credential_absence_check_passed':True,
              'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]}
    target=STUDY/'artifact_manifest_v1.json';assert not target.exists()
    target.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');files.add(target)
    prefix='ContractKV_TableI_20261018/'
    versions=json.loads((STUDY/'post_run_versions_v1.json').read_text())['packages']
    requirements=('transformers=='+versions['transformers']+'\ntokenizers=='+versions['tokenizers']+'\n').encode()
    a.zip.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path,prefix+path.relative_to(ROOT).as_posix(),
                          compress_type=zipfile.ZIP_STORED if path.suffix=='.gz' else zipfile.ZIP_DEFLATED)
        archive.writestr(prefix+'README.md',(STUDY/'README.md').read_bytes())
        archive.writestr(prefix+'RESULTS_zh.md',(ROOT/'docs/tsc_TableI_independent_measurement_completed_20261018_zh.md').read_bytes())
        archive.writestr(prefix+'requirements-cpu.txt',requirements)
    with zipfile.ZipFile(a.zip) as archive:
        assert len(archive.namelist())==len(files)+3
        for r in manifest['files']:
            assert hashlib.sha256(archive.read(prefix+r['path'])).hexdigest()==r['sha256'],r['path']
    print(json.dumps({'zip':str(a.zip),'bytes':a.zip.stat().st_size,'sha256':sha(a.zip),
                      'source_files_verified':len(manifest['files']),'credential_not_included':True}))


if __name__=='__main__':main()
