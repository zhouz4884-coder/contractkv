"""Freeze phase-three sources disjoint from all 462 previously used sources."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import source,family,read


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);a=parser.parse_args();root=a.root.resolve()
    base=root/'results/tsc_revision_r4/inputs'
    if base.exists():raise RuntimeError('Preserve sealed phase-three input selection')
    parent=root/'results/tsc_revision_r3/inputs/input_commitment_v1.json'
    prior=json.loads(parent.read_text(encoding='utf-8'));files=list(prior['exclusion_files'])
    previous=root/'results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl'
    assert sha(previous)==prior['cohorts']['heldout_sealed_sessions_v1.jsonl']['sha256']
    files.append({'file':previous.relative_to(root).as_posix(),'sha256':sha(previous)})
    excluded=set()
    for record in files:
        path=root/record['file']
        if sha(path)!=record['sha256']:raise ValueError('Prior source bytes changed')
        excluded.update(source(r) for r in read(path))
    if len(excluded)!=462:raise ValueError('Expected exactly462 previous source groups')
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    if sha(pool)!=prior['source_pool_sha256']:raise ValueError('Source pool changed')
    available={};seed=10672131
    for row in sorted(read(pool),key=lambda r:hashlib.sha256((str(seed)+':'+source(r)).encode()).hexdigest()):
        if source(row) not in excluded:available.setdefault(source(row),row)
    selected=[];availability={}
    for fam in ('RULER','HotpotQA','NarrativeQA','Qasper','RepoBench'):
        candidates=[r for r in available.values() if family(r)==fam];availability[fam]=len(candidates)
        if len(candidates)<10:raise ValueError('Insufficient new source groups: '+fam)
        for r in candidates[:10]:
            group=source(r);sid='r4-heldout-'+hashlib.sha256(group.encode()).hexdigest()[:16]
            selected.append({**r,'phase19b_session_id':sid,'revision_session_id':sid,'revision_family':fam,'revision_source_group':group})
    fan=[];counts=Counter()
    for row in selected:
        if counts[row['revision_family']]<2:fan.append(row);counts[row['revision_family']]+=1
    base.mkdir(parents=True);cohorts={}
    for name,rows in [('heldout_sealed_sessions_v1.jsonl',selected),('heldout_fanout_v1.jsonl',fan)]:
        path=base/name
        with path.open('x',encoding='utf-8',newline='\n') as out:
            for row in rows:out.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        cohorts[name]={'sha256':sha(path),'sources':len(rows),'source_groups':[source(r) for r in rows]}
    record={'schema_version':'tsc-r4.phase3-input-commitment.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'phase':3,'seed':seed,'excluded_sources':462,'exclusion_files':files,
            'excluded_set_sha256':hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),
            'source_pool_sha256':sha(pool),'parent_commitment_sha256':sha(parent),
            'unused_sources_before_selection':availability,'cohorts':cohorts,
            'selection_uses_model_outputs_or_scores':False,'new_phase3_model_outcomes_used':False,
            'all_previous_R2_and_R3_outcomes_are_observed_development':True}
    (base/'input_commitment_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'excluded_sources':462,'seed':seed,'input50sha':cohorts['heldout_sealed_sessions_v1.jsonl']['sha256'],
                      'fan10sha':cohorts['heldout_fanout_v1.jsonl']['sha256'],'available':availability}))


if __name__=='__main__':main()
