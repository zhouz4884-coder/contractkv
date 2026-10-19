"""Audit all three policies with the original risk branch or the fixed cost inputs."""
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r4_live_summary as summary
from scripts import tsc_revision_r4_cost_study_audit_cell_v1 as audit_module
from scripts.tsc_revision_r4_cost_adapter_v1 import installed_cost_features,load_profile,PROFILE_SHA256
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter


def audit_cell(directory,expected,freeze_sha,catalog):
    metadata=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
    root=directory.parents[1]
    config=json.loads((root/'freeze.json').read_text(encoding='utf-8'))['protocol']
    execution=json.loads((directory/'input_adapter_execution_v1.json').read_text(encoding='utf-8'))
    if execution['result']!='completed' or execution['policy']!=metadata['policy']:
        raise ValueError('Missing or incomplete declared controller execution')
    if execution['cost_profile_sha256']!=PROFILE_SHA256 or execution['cost_adapter_applied']!=(metadata['policy']=='cost-adapted'):
        raise ValueError('Cost method/profile binding mismatch')
    if execution['client_source_sha256']!=hashlib.sha256(Path('scripts/tsc_revision_r4_cost_study_live_v1.py').read_bytes()).hexdigest():
        raise ValueError('Cost study client source changed')
    if metadata['policy']!='cost-adapted':
        return audit_module.audit_cell(directory,expected,freeze_sha,catalog)
    profile=load_profile(root/'source_snapshot'/config['cost_profile'])
    models={row['model'] for row in summary.read(directory/'raw.jsonl') if row['row_type'] in ('warm','future')}
    if len(models)!=1:raise ValueError('A serving cell must contain exactly one model identity')
    model=next(iter(models))
    families=catalog['models'][model][metadata['study']]
    def resolve(calibration):
        found=[family for family,value in families.items() if value is calibration]
        if len(found)!=1:raise ValueError('Ambiguous model/family calibration identity')
        return found[0]
    with installed_cost_features(profile,model,resolve,audit_module):
        return audit_module.audit_cell(directory,expected,freeze_sha,catalog)


def main():
    previous=summary.audit_cell
    summary.audit_cell=audit_cell
    try:
        with installed_adapter():
            return summary.main()
    finally:
        summary.audit_cell=previous


if __name__=='__main__':
    raise SystemExit(main())
