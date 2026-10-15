"""Package completed R1R evidence; archived data and source bytes are immutable."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root.resolve()
    evidence=root/'results/tsc_revision_r1r'
    primary=json.loads((evidence/'validation/summary/completion_audit_v1.json').read_text())
    long=json.loads((evidence/'long_horizon/summary/completion_audit_v1.json').read_text())
    if not primary['experimental_execution_complete'] or not long['execution_complete']: raise RuntimeError('Incomplete serving audit')
    for script in ('tsc_revision_r1r_failure_diagnostics.py','tsc_revision_r1r_witness_decisions.py','tsc_revision_r1r_cost_decomposition.py','tsc_revision_r1r_gpu_diagnostics.py'):
        subprocess.run([sys.executable,str(root/'scripts'/script),'--root',str(evidence/'validation'),
                        '--output',str(evidence/'validation/summary')],check=True)
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_output_horizon.py'),'--root',str(evidence/'validation'),
                    '--legacy-root',str(root/'results/tsc_revision_r1'),'--output',str(evidence/'validation/summary')],check=True)
    files=[]
    for path in evidence.rglob('*'):
        if not path.is_file() or path.name.endswith('.partial') or path.name.endswith('.pid'): continue
        if 'known_counterexamples' in path.relative_to(evidence).parts: continue
        if path.name.startswith('r1r_raw_evidence_v1.tar.gz') or path.name.startswith('raw_evidence_'): continue
        if any(s in path.parts for s in ('quarantine','cache')): continue
        if path.suffix in ('.json','.jsonl','.csv','.py','.sh','.sha256','.patch'): files.append(path)
    logs=root/'logs/tsc_revision_r1r'
    for path in logs.glob('*'):
        if path.name.startswith('known'): continue
        if path.name.startswith(('final','post_analysis')) and path.suffix=='.log': continue
        if path.suffix in ('.log','.sh'): files.append(path)
    files += [root/'third_party/licenses/vllm-Apache-2.0.txt',root/'third_party/licenses/README.md']
    selected=sorted(set(files))
    inventory=[{'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':sha(path)} for path in selected]
    with (evidence/'raw_evidence_inventory_v1.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','bytes','sha256')); writer.writeheader(); writer.writerows(inventory)
    archive=evidence/'r1r_raw_evidence_v1.tar.gz'
    if archive.exists(): raise RuntimeError('Preserve existing evidence archive')
    with tarfile.open(archive,'w:gz',compresslevel=6) as output:
        for path in selected: output.add(path,arcname=path.relative_to(root),recursive=False)
    record={'schema_version':'tsc-r1r.raw-archive.v1','archive':archive.name,'archive_sha256':sha(archive),
            'archive_bytes':archive.stat().st_size,'member_files':len(inventory),
            'formal_cells':45,'formal_future_generations':28350,'controlled_long_cells':9,'controlled_long_generations':135,
            'includes_development_records':True,'includes_actual_output_ids_and_metrics':True,
            'includes_exact_runtime_source_snapshot':True,'includes_server_logs':True,
            'excluded':['private SSH helpers','credential files','weights','caches','quarantines','known-counterexample followup: separate artifact'],
            'scope':'Experimental execution complete; scientific outcomes are reported separately'}
    (evidence/'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))


if __name__=='__main__': main()
