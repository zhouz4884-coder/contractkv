"""Index known source identities only; never open/select from the candidate pool."""
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import source


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root):
    old=root/'results/tsc_revision_r4/fidelity_complete_exclusion_audit_v1.json'
    audit=json.loads(old.read_text(encoding='utf-8'));known=set(audit['excluded_source_groups'])
    assert len(known)==audit['total_excluded_unique_sources']==567
    assert hashlib.sha256(json.dumps(sorted(known)).encode()).hexdigest()==audit['excluded_set_sha256']
    files=[dict(path=old.relative_to(root).as_posix(),sha256=sha(old),sources=567,new_unique=567)]
    extras=[
        'results/tsc_revision_r4/input_fidelity_validation_inputs_v1/original_selected_sessions_v1.jsonl',
        'results/tsc_revision_r4/cost_adaptation_validation_inputs_v1/original_selected_sessions_v1.jsonl',
        'results/tsc_revision_r4/input_fidelity_development_inputs_v3/development_faithful_sessions_v3.jsonl',
        'results/tsc_revision_r4/input_fidelity_development_inputs_v3/development_old_head_sessions_v3.jsonl',
        'results/tsc_tableI_remeasurement_20261018/inputs_v1/selected_original_sources_v1.jsonl']
    for rel in extras:
        p=root/rel;rr=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
        identities=set()
        for row in rr:
            if 'source_dataset' in row:
                identity=row['source_group']
                assert identity.startswith(row['source_dataset']+':'+row['source_task']+':')
            else:
                identity=source(row)
                if row.get('revision_source_group'):assert row['revision_source_group']==identity
            identities.add(identity)
        files.append(dict(path=rel,sha256=sha(p),rows=len(rr),sources=len(identities),new_unique=len(identities-known)))
        known.update(identities)
    out=root/'results/tsc_final_existing_evidence_CPU_20261018/final_known_source_exclusions_v1.json'
    result=dict(schema_version='contractkv.final-known-source-exclusions.v1',excluded_source_groups=sorted(known),
        total_excluded_unique_sources=len(known),files=files,
        excluded_set_sha256=hashlib.sha256(json.dumps(sorted(known)).encode()).hexdigest(),
        original_567_boundary_preserved=True,faithful_main_cost_validation_and_TableI_added=True,
        source_pool_opened=False,new_sources_selected=False,new_GPU_requests=0,source_sha256=sha(Path(__file__)))
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='excluded_source_groups'}))


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
