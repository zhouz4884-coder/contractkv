"""New source-disjoint test cohort before second-stage policy selection."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import read,source,family


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(path,rows):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        for row in rows: stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
    return sha(path)


def main():
    p=argparse.ArgumentParser()
    for key in ('pool','protocol','development','previous-heldout','known-config','output'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--prior-exclude',type=Path,action='append',default=[])
    p.add_argument('--exclude',type=Path,action='append',default=[]); a=p.parse_args()
    config=json.loads(a.protocol.read_text(encoding='utf-8'))
    for path,expected in [(a.pool,config['source_pool_sha256']),(a.development,config['reuse_development_sha256']),(a.previous_heldout,config['previous_heldout_sha256'])]:
        if sha(path)!=expected: raise ValueError('Input changed: '+str(path))
    names=('development_sessions_v1.jsonl','heldout_sealed_sessions_v1.jsonl','input_commitment_v1.json')
    if any((a.output/name).exists() for name in names): raise RuntimeError('Preserve existing cohort freeze')
    prior={source(r) for path in a.prior_exclude for r in read(path)}
    if len(prior)!=config['prior_excluded_source_groups']: raise ValueError('Original exclusion set count changed')
    excluded=prior|{source(r) for path in a.exclude for r in read(path)}
    if len(excluded)!=config['all_previous_excluded_source_groups']: raise ValueError('Previous cohort exclusion count changed')
    pool=read(a.pool); available={}
    for row in sorted(pool,key=lambda r:hashlib.sha256((str(config['seed'])+':'+source(r)).encode()).hexdigest()):
        if source(row) not in excluded: available.setdefault(source(row),row)
    heldout=[]
    for fam in config['families']:
        selected=[r for r in available.values() if family(r)==fam][:config['heldout_sessions_per_family']]
        if len(selected)!=config['heldout_sessions_per_family']: raise ValueError('Insufficient new source groups: '+fam)
        for row in selected:
            key=source(row); sid='r2-heldout-'+hashlib.sha256(key.encode()).hexdigest()[:16]
            heldout.append({**row,'phase19b_session_id':sid,'revision_session_id':sid,'revision_family':fam,'revision_source_group':key})
    development=read(a.development); previous={r['revision_session_id']:r for r in read(a.previous_heldout)}
    known=json.loads(a.known_config.read_text(encoding='utf-8'))['cases']
    development += [previous[c['source_session']] for c in known]
    dev_groups={source(r) for r in development}; test_groups={source(r) for r in heldout}
    if len(dev_groups)!=12 or len(test_groups)!=50 or dev_groups&test_groups or test_groups&excluded:
        raise ValueError('Cohort identity or disjointness failure')
    a.output.mkdir(parents=True,exist_ok=True)
    cohorts={}
    for name,rows in [('development',development),('heldout_sealed',heldout)]:
        path=a.output/(name+'_sessions_v1.jsonl')
        cohorts[name]={'file':path.name,'sha256':emit(path,rows),'sessions':len(rows),
                       'source_groups':[source(r) for r in rows],'families':dict(Counter(family(r) for r in rows))}
    record={'schema_version':'tsc-r2.input-commitment.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'protocol_sha256':sha(a.protocol),'source_pool_sha256':sha(a.pool),'prior_excluded_source_groups':len(prior),
            'excluded_source_groups':len(excluded),'excluded_source_set_sha256':hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),
            'exclusion_files':[{'file':str(path),'sha256':sha(path)} for path in a.prior_exclude+a.exclude],
            'development_contains_two_selected_prior_failures':True,'development_is_not_heldout':True,
            'new_heldout_selection_uses_outcomes':False,'new_heldout_disjoint_from_all_excluded_and_development':True,
            'new_heldout_frozen_before_policy_selection':True,'cohorts':cohorts}
    with (a.output/'input_commitment_v1.json').open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in {'cohorts','exclusion_files'}}))
    print(json.dumps({name:{k:v for k,v in data.items() if k!='source_groups'} for name,data in cohorts.items()}))


if __name__=='__main__': main()
