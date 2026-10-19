"""Archive the completed, explicitly selected known-case followup separately."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root.resolve()
    base=root/'results/tsc_revision_r1r/known_counterexamples'
    audit=json.loads((base/'completion_audit_v1.json').read_text())
    if not audit['execution_complete']: raise RuntimeError('Incomplete known-case evidence')
    subprocess.run([sys.executable,str(root/'scripts/tsc_revision_r1r_known_summary_audit_v2.py'),'--root',str(base)],check=True)
    extra=json.loads((base/'additional_audit_v2/completion_audit_v2.json').read_text())
    if not extra['execution_complete']: raise RuntimeError('Known-case identity and metric audit failed')
    output=base/'known_raw_evidence_v1.tar.gz'
    if output.exists(): raise RuntimeError('Preserve immutable known-case archive')
    files=[p for p in base.rglob('*') if p.is_file() and not p.name.endswith(('.pid','.partial')) and not p.name.startswith('raw_evidence_')]
    logs=root/'logs/tsc_revision_r1r'
    files += list(logs.glob('known-*_server.log'))
    files += [logs/'known_counterexamples_v1.log',logs/'known_counterexamples_snapshot_v1.sh']
    files += [root/'third_party/licenses/vllm-Apache-2.0.txt',root/'third_party/licenses/README.md']
    files=sorted(set(files))
    inventory=[{'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':sha(path)} for path in files]
    with (base/'raw_evidence_inventory_v1.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=('path','bytes','sha256')); writer.writeheader(); writer.writerows(inventory)
    with tarfile.open(output,'w:gz',compresslevel=6) as archive:
        for path in files: archive.add(path,arcname=path.relative_to(root),recursive=False)
    result={'schema_version':'tsc-r1r.known-case-archive.v1','archive':output.name,'archive_sha256':sha(output),
            'archive_bytes':output.stat().st_size,'member_files':len(files),'policy_cells':9,'future_generations':108,
            'additional_identity_and_actual_metric_audit_passed':extra['execution_complete'],
            'selected_known_failure_diagnostic_not_heldout':True,'no_performance_claim':True}
    (base/'raw_evidence_archive_manifest_v1.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
