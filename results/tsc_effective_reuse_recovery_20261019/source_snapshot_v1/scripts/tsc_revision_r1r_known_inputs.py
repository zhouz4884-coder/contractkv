"""Freeze all known native-budget compiled failure units; diagnostic only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root
    target=root/'results/tsc_revision_r1r/known_counterexamples/inputs'; target.mkdir(parents=True,exist_ok=True)
    if (target/'commitment_v1.json').exists(): raise RuntimeError('Preserve frozen diagnostic inputs')
    path=root/'results/tsc_revision_r1/material_quality_drop_cases_v1.csv'
    with path.open(encoding='utf-8') as stream: cases=list(csv.DictReader(stream))
    units=sorted({(r['model'],r['session_id']) for r in cases if r['request_class']=='admitted_compiled' and r['budget_override']=='0'})
    samples={r['revision_session_id']:r for r in [json.loads(line) for line in (root/'configs/tsc_revision_free_generation_sessions_v1.jsonl').read_text(encoding='utf-8').splitlines()]}
    files=[]
    for model in ('qwen','mistral','llama'):
        selected=[samples[sid] for name,sid in units if name==model]
        output=target/(model+'_sessions_v1.jsonl')
        output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected),encoding='utf-8')
        files.append({'model':model,'file':output.name,'sessions':len(selected),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                      'source_groups':[r['revision_source_group'] for r in selected]})
    record={'schema_version':'tsc-r1r.known-failures-input.v1','selection_uses_known_failures':True,'new_heldout_evidence':False,
            'known_model_source_units':len(units),'expected_policy_cells':9,'expected_future_generations':108,
            'policies':['raw-order','legacy-unbound','query-prefix'],'fresh_server_processes':3,
            'measurement':'Same declared task inputs; policies share one fresh server per model; no performance claim; no assertion of original batch-shape identity',
            'selection_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':files}
    (target/'commitment_v1.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))


if __name__=='__main__': main()
