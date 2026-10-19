"""Independent CPU accounting for the frozen metadata-only development control."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score

STUDY=Path('results/tsc_effective_reuse_recovery_20261019/clean_renderer_development_v1')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(p):
    with p.open(encoding='utf-8') as f:return [json.loads(s) for s in f if s.strip()]
def write(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')

def main(root,output):
    study=root/STUDY;state=read(study/'execution_state_v1.json')
    assert state['status']=='COMPLETE_PENDING_RENDERER_DECISION' and len(state['completed_cells'])==3
    freeze=read(study/'freeze_v1.json')
    for r in freeze['files']:assert sha(root/r['path'])==r['sha256'],r['path']
    assert not output.exists();output.mkdir(parents=True)
    sources={r['revision_source_group']:r for r in lines(study/'repo_development_inputs_v1.jsonl')}
    witnesses,candidates,comparisons,choices,native=[],[],[],[],[]
    publication_total=0
    for relative in state['completed_cells']:
        cell=study/relative
        for r in read(cell/'nested_completion_inventory_v1.json')['files']:assert sha(cell/r['path'])==r['sha256'],r['path']
        data=lines(cell/'responses.jsonl');assert data[-1]['event']=='renderer_development_cell_complete'
        model=data[0]['model'];lookups={};hits={};pubs=[];used=set()
        with (cell/'backend_trace.jsonl').open(encoding='utf-8') as f:
            for text in f:
                r=json.loads(text)
                if r['event']=='lookup_before':lookups.setdefault(r['request_id'],r)
                elif r['event']=='lookup_return' and r['request_id'] in lookups:hits.setdefault(r['request_id'],r)
                elif r['event']=='verification_cache_blocks_return':pubs.append(r)
        def actual(response):
            rid=response['request_id'];matches=[r for k,r in lookups.items() if k==rid or k.startswith(rid+'-')]
            assert matches,rid
            before=min(matches,key=lambda r:r['seq']);after=hits[before['request_id']]
            assert before['prompt_tokens']==len(response['prompt_token_ids']) and after['seq']>before['seq']
            assert before['backend_cache_salt'].startswith('ckv-auth-v1:')
            native.append(dict(model=model,request_id=rid,prompt_tokens=before['prompt_tokens'],actual_hit_tokens=after['hit_tokens'],
                               authorized_salt_sha256=hashlib.sha256(before['backend_cache_salt'].encode()).hexdigest()))
            return before,after
        raw={}
        for r in data:
            if r['event']!='development_Raw_witness':continue
            source=sources[r['source_group']];a,b=r['raw'],r['repeat'];first,_=actual(a);again,_=actual(b)
            assert first['backend_cache_salt']==again['backend_cache_salt']
            score=standard_score(source['dataset'],source['task'],a['output_text'],source.get('answer',''))[0]
            assert score==r['task_score']
            row=dict(model=model,renderer=r['renderer'],source_group=r['source_group'],Raw_score=score,
                Raw_tokens=len(a['output_token_ids']),Raw_finish_reason=str(a['finish_reason']),
                Raw_repeat_equal=(a['output_token_ids'],a['finish_reason'])==(b['output_token_ids'],b['finish_reason']),
                Raw_scope_shareable=r['scope_check']['shareable_query_scope'],Raw_syntax_passed=r['syntax_check']['passed'],
                CODE_PREFIX_heading_echo='[CODE_PREFIX:' in a['output_text'])
            witnesses.append(row);raw[r['renderer'],r['source_group']]=r
        for r in data:
            if r['event']!='candidate_feasibility':continue
            ref=raw[r['renderer'],r['source_group']]['raw'];before,after=actual(r['observed'])
            refsalt=next(n['authorized_salt_sha256'] for n in native if n['request_id']==ref['request_id'])
            payload=next((q['payload'] for q in r['verification_rows'] if q['row_type']=='verification_request'),None)
            pub=[p for p in pubs if payload and (p['request_id']==payload['request_id'] or p['request_id'].startswith(payload['request_id']+'-'))]
            issued=bool(r['result']['certificate_issued'])
            if issued:
                assert len(pub)==1 and pub[0]['requested_tokens']==r['result']['committed_tokens']
                assert pub[0]['backend_cache_salt']==payload['cache_salt']==before['backend_cache_salt']
                assert hashlib.sha256(before['backend_cache_salt'].encode()).hexdigest()==refsalt
                assert r['behavior_equal'];used.add(pub[0]['request_id'])
            else:
                assert not pub and int(r['result'].get('committed_tokens',0))==0
                assert hashlib.sha256(before['backend_cache_salt'].encode()).hexdigest()!=refsalt
            source=sources[r['source_group']]
            observed_score=standard_score(source['dataset'],source['task'],r['observed']['output_text'],source.get('answer',''))[0]
            candidates.append(dict(model=model,renderer=r['renderer'],source_group=r['source_group'],level=r['level'],accepted=issued,
                reason=r['result']['failure_reason'] or 'PASS',RPCs=len(r['result']['attempts']),
                behavior_equal=r['behavior_equal'],Raw_repeat_equal=r['Raw_repeat_ID_and_finish_equal'],
                usable=r['usable_development_evidence'],stable_full_blocks=r['plan']['stable_full_blocks'],
                actual_native_hit_tokens=after['hit_tokens'],observed_score=observed_score,
                complete_probe_elapsed_ms=r['complete_probe_elapsed_ms']))
        assert {p['request_id'] for p in pubs}==used,'Unaccounted shared candidate publication'
        publication_total+=len(pubs)
        for source in sources:
            a,b=raw['current',source],raw['clean',source]
            comparisons.append(dict(model=model,source_group=source,current_Raw_score=a['task_score'],clean_Raw_score=b['task_score'],
                delta=b['task_score']-a['task_score'],current_IDs_equal_clean=(a['raw']['output_token_ids'],a['raw']['finish_reason'])==(b['raw']['output_token_ids'],b['raw']['finish_reason'])))
    assert len(native)==60 and len(candidates)==36 and len(witnesses)==12
    for model in sorted({r['model'] for r in candidates}):
        for renderer in ('current','clean'):
            allowed=[]
            for level in ('L1','L2','L3'):
                part=[r for r in candidates if (r['model'],r['renderer'],r['level'])==(model,renderer,level)]
                assert len(part)==2
                if all(r['usable'] for r in part):allowed.append(level)
            choices.append(dict(model=model,renderer=renderer,strict_two_source_eligible_levels=allowed,
                                feasibility_does_not_establish_economic_qualification=True))
    groups=[]
    for renderer in ('current','clean'):
        part=[r for r in candidates if r['renderer']==renderer];rr=[r for r in witnesses if r['renderer']==renderer]
        groups.append(dict(renderer=renderer,candidates=len(part),PASS=sum(r['accepted'] for r in part),usable=sum(r['usable'] for r in part),
            RPCs=sum(r['RPCs'] for r in part),reasons=dict(Counter(r['reason'] for r in part)),
            Raw_syntax_PASS=sum(r['Raw_syntax_passed'] for r in rr),Raw_scope_shareable=sum(r['Raw_scope_shareable'] for r in rr),
            Raw_CODE_PREFIX_echo=sum(r['CODE_PREFIX_heading_echo'] for r in rr),Raw_score_mean=sum(r['Raw_score'] for r in rr)/len(rr)))
    summary=dict(status='CPU_RENDERER_ACCOUNTING_COMPLETE',cells=3,business=60,candidate_decisions=36,groups=groups,
        choices=choices,Raw_comparisons=comparisons,actual_shared_publications=publication_total,
        rejected_candidate_new_shared_publications=0,no_formal_validation_outputs_used=True,new_GPU_requests=0,
        source_sha256=sha(Path(__file__)),boundary='One development fresh-server per model; two previously observed repositories; current/clean share an engine with separate authorization identities. No causal serving speedup or independent generalization claim.')
    for name,rr in [('Raw_witnesses',witnesses),('candidates',candidates),('actual_native',native)]:
        with (output/(name+'_v1.csv')).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    write(output/'summary_v1.json',summary)
    print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
