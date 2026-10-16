"""Fresh source-disjoint validation before the second admission amendment."""
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
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    base=root/'results/tsc_revision_r3/inputs';base.mkdir(parents=True,exist_ok=True)
    if (base/'input_commitment_v1.json').exists():raise RuntimeError('Preserve new input freeze')
    old=json.loads((root/'results/tsc_revision_r2/inputs/input_commitment_v1.json').read_text())
    excluded=set();files=[]
    for record in old['exclusion_files']:
        path=root/record['file']
        if sha(path)!=record['sha256']:raise ValueError('Prior exclusion source changed')
        excluded.update(source(r) for r in read(path));files.append(record)
    previous=root/'results/tsc_revision_r2/inputs/heldout_sealed_sessions_v1.jsonl'
    if sha(previous)!='4617b7b05bf2ff10521bdef28c385a414cc05ae718bc747bfeea5eaa8fd65725':raise ValueError('Preserve previous50')
    excluded.update(source(r) for r in read(previous));files.append({'file':previous.relative_to(root).as_posix(),'sha256':sha(previous)})
    if len(excluded)!=412:raise ValueError('Expected412 previously used source groups')
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    if sha(pool)!=old['source_pool_sha256']:raise ValueError('Source pool changed')
    available={};seed=10672130
    for row in sorted(read(pool),key=lambda r:hashlib.sha256((str(seed)+':'+source(r)).encode()).hexdigest()):
        if source(row) not in excluded:available.setdefault(source(row),row)
    selected=[]
    for fam in ('RULER','HotpotQA','NarrativeQA','Qasper','RepoBench'):
        candidates=[r for r in available.values() if family(r)==fam][:10]
        if len(candidates)!=10:raise ValueError('Insufficient unused sources '+fam)
        for r in candidates:
            group=source(r);sid='r3-heldout-'+hashlib.sha256(group.encode()).hexdigest()[:16]
            selected.append({**r,'phase19b_session_id':sid,'revision_session_id':sid,'revision_family':fam,'revision_source_group':group})
    fan=[];counts=Counter()
    for r in selected:
        if counts[r['revision_family']]<2:fan.append(r);counts[r['revision_family']]+=1
    cohorts={}
    for filename,rows in [('heldout_sealed_sessions_v1.jsonl',selected),('heldout_fanout_v1.jsonl',fan)]:
        path=base/filename
        with path.open('x',encoding='utf-8',newline='\n') as out:
            for r in rows:out.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
        cohorts[filename]={'sha256':sha(path),'sources':len(rows),'source_groups':[source(r) for r in rows]}
    record={'schema_version':'tsc-r3.fresh-input-commitment.v1','timestamp':datetime.now(timezone.utc).isoformat(),
      'seed':seed,'excluded_sources':412,'exclusion_files':files,'source_pool_sha256':sha(pool),
      'excluded_set_sha256':hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),'cohorts':cohorts,
      'selection_uses_model_outputs_or_scores':False,'frozen_before_new_admission_policy_forward_requests':True,
      'previous50_now_observed_development_and_not_relabelled_as_unseen':True}
    (base/'input_commitment_v1.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ('exclusion_files','cohorts')}));print(json.dumps(cohorts))

if __name__=='__main__':main()
