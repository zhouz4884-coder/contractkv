"""Freeze repair development and sealed validation without outcome selection."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from scripts.tsc_revision_build_inputs import read,source,family,emit


def main():
    p=argparse.ArgumentParser(); p.add_argument("--pool",type=Path,required=True); p.add_argument("--protocol",type=Path,required=True)
    p.add_argument("--exclude",type=Path,action="append",default=[]); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); protocol=json.loads(a.protocol.read_text()); excluded={source(r) for f in a.exclude for r in read(f)}
    ordered=sorted(read(a.pool),key=lambda r:hashlib.sha256((str(protocol['seed'])+':'+source(r)).encode()).hexdigest())
    unique={}; [unique.setdefault(source(r),r) for r in ordered if source(r) not in excluded]
    used=set(excluded); commitments={}; a.output.mkdir(parents=True,exist_ok=True)
    for cohort,per_family in (("development",protocol["development_sessions_per_family"]),("heldout_sealed",protocol["heldout_sessions_per_family"])):
        rows=[]
        for fam in protocol["families"]:
            selected=[r for key,r in unique.items() if key not in used and family(r)==fam][:per_family]
            if len(selected)!=per_family: raise RuntimeError("Insufficient disjoint source groups: "+fam)
            for row in selected:
                key=source(row); used.add(key); sid="r1r-"+cohort+"-"+hashlib.sha256(key.encode()).hexdigest()[:16]
                rows.append({**row,"phase19b_session_id":sid,"revision_session_id":sid,"revision_family":fam,"revision_source_group":key})
        path=a.output/(cohort+"_sessions_v1.jsonl")
        commitments[cohort]={"file":path.name,"sha256":emit(path,rows),"sessions":len(rows),"source_groups":[source(r) for r in rows],
                             "families":dict(Counter(family(r) for r in rows))}
    result={"schema_version":"tsc-r1r.input-commitment.v1","protocol_sha256":hashlib.sha256(a.protocol.read_bytes()).hexdigest(),
            "source_pool_sha256":hashlib.sha256(a.pool.read_bytes()).hexdigest(),"excluded_source_groups":len(excluded),
            "selection_uses_outcomes":False,"cohorts_disjoint":True,"cohorts":commitments}
    (a.output/"input_commitment_v1.json").write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=="__main__": main()
