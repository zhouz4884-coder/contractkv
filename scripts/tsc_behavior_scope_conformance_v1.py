"""Independent post-hoc CPU audit; no admission/score/metric changes."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.contractkv_exact_behavior import digest as exact_digest
from scripts.phase17_live_common import digest
from scripts.tsc_behavior_scope_protocol_v2 import actual_prefix_errors

STUDY=Path('results/tsc_behavior_scope_repair_20261020')
UUIDS={'GPU-ef01d441-985f-50b3-6e64-5d4c3e2def3a','GPU-a696ce9a-7137-cf6f-b4d3-deb992a72f28'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(root,phase,output):
    study=root/STUDY;analysis=read(study/(phase+'_analysis_v5.json'));assert analysis['status']=='PASS'
    jobs=read(study/(phase+'_jobs_v4.json'))['jobs'];counts=Counter();cells=[];scope_rows=[]
    raw_variants=defaultdict(set);matched=[]
    for job in jobs:
        cell=study/'runs'/job['id']/'attempt1';rr=lines(cell/'responses.jsonl')
        business=[r for r in rr if r['row_type']=='business'];regs=[r for r in rr if r['row_type']=='registration']
        groups=defaultdict(set);principals=defaultdict(set);prefixes=defaultdict(set)
        for r in business:
            groups[r['source_group']].add(r['result']['actual_wire_cache_salt']);principals[r['source_group']].add(r['tenant'])
            counts['all_business']+=1;counts['finish_'+r['result']['finish_reason']]+=1
            if job['policy']=='Raw-authorized':raw_variants[job['model'],r['source_group'],r['result']['prompt_ids_sha256']].add((tuple(r['result']['output_token_ids']),r['result']['finish_reason']))
            if job['policy']=='Strict-exact' and r['compiled']:
                reg=next(x for x in regs if (x['source_group'],x['tenant'],x['turn'])==(r['source_group'],r['tenant'],r['turn']))
                cert=reg['certificate'];ids=r['result']['prompt_token_ids']
                assert not actual_prefix_errors(ids,cert)
                assert exact_digest(ids)==reg['behavior']['evidence']['candidate_prompt_sha256']
                assert exact_digest(r['result']['output_token_ids'])==reg['behavior']['evidence']['raw_output_sha256']
                assert r['result']['finish_reason']==reg['behavior']['evidence']['finish_reason']=='stop'
                counts['strict_compiled_actual_prefix_and_exact_scope_and_witness_match']+=1
                mutated=list(ids);mutated[0]=(mutated[0]+1)%100000
                assert 'actual_certified_prefix_hash_mismatch' in actual_prefix_errors(mutated,cert)
                counts['posthoc_actual_GPU_prefix_mutation_rejected_CPU_only']+=1
        assert all(len(v)==1 for v in groups.values()) and len({next(iter(v)) for v in groups.values()})==len(groups)
        assert all(v=={0,1} for v in principals.values())
        for reg in regs:
            cert=reg['certificate']
            if cert['certificate_issued']:
                assert cert['committed_tokens']>0 and cert['committed_tokens']%16==0
                prefixes[reg['source_group']].add(cert['stable_prefix_hash'])
                counts[job['policy']+'_PASS']+=1
                if job['policy']=='Strict-exact':
                    assert reg['reference_kind']=='RAW_QUERY';counts['strict_Raw_reference_kind']+=1
                    first=next(r for r in business if (r['source_group'],r['tenant'],r['turn'],r['access'])==(reg['source_group'],reg['tenant'],reg['turn'],0))
                    assert exact_digest(first['result']['prompt_token_ids'])==reg['behavior']['evidence']['raw_prompt_sha256']
                    scope_rows.append(dict(model=job['model'],repeat=job['repeat'],source=reg['source_group'],tenant=reg['tenant'],turn=reg['turn'],
                        actual_Raw_reference_prompt_ids_sha256=first['result']['prompt_ids_sha256'],
                        exact_behavior_Raw_prompt_sha256=reg['behavior']['evidence']['raw_prompt_sha256'],
                        physical_prefix_hash=cert['stable_prefix_hash'],committed_tokens=cert['committed_tokens']))
            else:
                assert not cert.get('committed_tokens',0);counts['rejected_registrations_zero_compiled_publication']+=1
        assert all(len(v)==1 for v in prefixes.values())
        private=[r['result']['actual_wire_cache_salt'] for r in rr if r['row_type']=='reference_generation']
        assert not set(private)&{next(iter(v)) for v in groups.values()}
        launch=read(cell/'launch_v1.json');lane=launch['environment']['CUDA_VISIBLE_DEVICES']
        assert lane==str(job['lane'])
        cells.append(dict(job=job['id'],business=len(business),groups=len(groups),tenants_per_group=2,
                          same_source_shares_one_group=True,private_reference_disjoint=True,actual_CUDA_VISIBLE_DEVICES=lane,
                          distinct_stable_prefixes_per_registered_source={k:len(v) for k,v in prefixes.items()}))
    snapshots=0
    for path in (study/'waves').glob('*_GPU_resources_v1.jsonl'):
        if phase=='development' and any('validation' in r['id'] for r in jobs):continue
        # A full all-phase archive may contain both phases; all snapshots must
        # preserve the same hardware/exclusivity invariants regardless.
        for row in lines(path):
            assert not row.get('foreign_GPU_PIDs') and not row.get('error_type')
            assert {d[1] for d in row['snapshot']['devices']}==UUIDS;snapshots+=1
    counts['resource_snapshots_checked']=snapshots
    result=dict(status='PASS',phase=phase,counts=dict(counts),cells=cells,strict_scope_records=scope_rows,
        Raw_exact_prompt_groups_with_output_variation=sum(len(v)>1 for v in raw_variants.values()),
        raw_variation_is_not_causal_exoneration=True,
        hash_encoding=dict(legacy_transport_and_physical_prefix='SHA256(json.dumps(sort_keys=True, ensure_ascii=False), UTF8)',
                           exact_behavior_identity='SHA256(json.dumps(sort_keys=True, ensure_ascii=False, separators=(comma,colon)), UTF8)'),
        boundary='Post-hoc CPU checks on actual GPU evidence. Prefix mutation controls are not extra GPU attacks. Finite witnesses are not universal generation guarantees.',
        source_sha256=sha(Path(__file__)))
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','phase':phase,'counts':dict(counts)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--phase',choices=['development','validation'],required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.phase,a.output)
