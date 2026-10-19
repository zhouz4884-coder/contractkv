"""Analyze actual equal-budget outputs, independently checking scores and commits."""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')


def main(root,study):
    output=study/'analysis_v1';assert not output.exists()
    state=read(study/'execution_state_v1.json')
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==3
    base=root/'results/tsc_revision_mechanism_controls_20261018'
    plan=read(study/'protocol_v1.json');cases={x['case_id']:x for x in plan['behavior_cases']}
    original=base/'source_snapshot/scripts/tsc_revision_mechanism_live_v3.py'
    tree=ast.parse(original.read_text(encoding='utf-8'))
    helper=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ['normalized','score','difference']]
    scope=dict(re=re);exec(compile(ast.Module(body=helper,type_ignores=[]),str(original)+'[postprocessing helpers]','exec'),scope)
    score=scope['score'];difference=scope['difference']
    shapes={(x['model'],x['case_id'],x['condition']):x for x in read(base/'preflight_v3/input_shapes_v1.json')['shapes']}
    runtime={x['path']:x['sha256'] for x in read(base/'preflight_v3/runtime_inventory_v1.json')['files']}
    result=[];cell_reports=[];baseline=[];inventory=[]
    parent_state=read(base/'execution_state_v1.json')
    for rel in state['completed_cells']:
        cell=study/rel;complete=read(cell/'completion_v1.json');assert complete['status']=='complete'
        for x in complete['files']:
            assert sha(cell/x['path'])==x['sha256']
            inventory.append(dict(path=(cell/x['path']).relative_to(root).as_posix(),sha256=x['sha256']))
        rr=rows(cell/'responses.jsonl');assert rr[-1]['event']=='diagnostic_cell_complete'
        business=[x for x in rr if x['event']=='business'];assert len(business)==80
        assert not any(x['event'].startswith('manifest_') for x in rr)
        events={x['case_id']:x for x in rr if x['event']=='behavior_case_complete'};assert len(events)==20
        quals={x['case_id']:x for x in rr if x['event']=='qualification'};assert len(quals)==20
        trace=rows(cell/'backend_trace.jsonl')
        for mod in ['vllm.v1.core.block_pool','vllm.v1.core.kv_cache_manager']:
            actual=[x for x in trace if x['event']=='diagnostic_hook_installed' and x['module']==mod]
            assert actual and all(x['source_sha256']==runtime[mod[5:].replace('.','/')+'.py'] for x in actual)
        launch=read(cell/'launch_v1.json');model=launch['server'][launch['server'].index('--model')+1].split('/')[-1]
        policy=launch['environment']['CONTRACTKV_POLICY_HASH'];assert policy==sha(study/'freeze_v2.json')
        local=[]
        for cid,event in events.items():
            four=[x for x in business if x['case_id']==cid];assert len(four)==4
            by={x['condition']:x for x in four}
            raw=by['raw_witness'];repeat=by['raw_repeat'];unchecked=by['unchecked_same_candidate']
            post=next(x for x in four if x['condition'].startswith('post_decision_'))
            for b in four:
                if b['response']['success']:
                    condition='candidate' if b['compiled_input'] else 'raw'
                    assert b['response']['prompt_ids_sha256']==shapes[model,cid,condition]['prompt_ids_sha256']
                    assert len(b['response']['output_token_ids'])<=256
                assert b['score']==score(b['response'],cases[cid]),'Primary frozen exact scorer differs'
            rd=difference(raw['response'],repeat['response']);ud=difference(raw['response'],unchecked['response']);pd=difference(raw['response'],post['response'])
            assert rd==event['raw_repeat'] and ud==event['unchecked_difference'] and pd==event['routed_difference']
            q=quals[cid];decision=q['result'];issued=decision['certificate_issued'] is True
            assert issued==event['certificate_issued']==post['compiled_input']
            published=[x for x in trace if x['event']=='verification_cache_blocks_return' and x['backend_cache_salt']==policy+':'+q['namespace']]
            indeterminate=decision.get('verification_status')=='indeterminate_request_failure'
            if issued:
                assert len(published)==1 and published[0]['requested_tokens']==decision['committed_tokens']>0
                assert decision['committed_tokens']%16==0 and decision['committed_tokens']<=q['plan']['stable_prefix_end_token']
            elif not indeterminate:assert not published
            rid=post['response']['request_id']
            lookups=[x for x in trace if x['event']=='lookup_before' and (x['request_id']==rid or x['request_id'].startswith(rid+'-'))]
            hit=None
            if post['response']['success']:
                assert len(lookups)==1
                returned=[x for x in trace if x['event']=='lookup_return' and x['request_id']==lookups[0]['request_id']]
                assert len(returned)==1;hit=returned[0]['hit_tokens']
            row=dict(model=model,cell=event['cell_id'],case_id=cid,family=event['family'],output_budget=256,
                raw_finish=raw['response'].get('finish_reason'),raw_tokens=len(raw['response'].get('output_token_ids',[])),
                unchecked_finish=unchecked['response'].get('finish_reason'),unchecked_tokens=len(unchecked['response'].get('output_token_ids',[])),
                post_finish=post['response'].get('finish_reason'),post_tokens=len(post['response'].get('output_token_ids',[])),
                raw_score=raw['score'],unchecked_score=unchecked['score'],post_score=post['score'],
                raw_repeat_changed=not rd['output_ids_equal'] if rd['available'] else None,
                unchecked_changed=not ud['output_ids_equal'] or not ud['finish_equal'] if ud['available'] else None,
                post_changed=not pd['output_ids_equal'] or not pd['finish_equal'] if pd['available'] else None,
                certificate_issued=issued,indeterminate=indeterminate,
                verification_status=decision.get('verification_status'),failure_reason=decision.get('failure_reason',''),
                actual_qualification_RPC_attempts=len(decision['attempts']),complete_qualification_ms=decision['complete_verification_ms'],
                actual_published_events=len(published),actual_committed_tokens=sum(x['requested_tokens'] for x in published),post_native_hit_tokens=hit,
                raw_ms=raw['response']['latency_ms'],unchecked_ms=unchecked['response']['latency_ms'],post_ms=post['response']['latency_ms'])
            result.append(row);local.append(row)
        cell_reports.append(dict(model=model,cell=rr[0]['cell_id'],client_wall_s=rr[-1]['diagnostic_client_wall_s'],
            raw_stopped=sum(x['raw_finish']=='stop' for x in local),raw_length_ended=sum(x['raw_finish']=='length' for x in local),
            raw_primary_exact_correct=sum(x['raw_score']>0 for x in local),candidates=20,certified=sum(x['certificate_issued'] for x in local),
            observed_unchecked_changes=sum(x['unchecked_changed'] is True for x in local),
            observed_unchecked_primary_drops=sum(x['unchecked_score']-x['raw_score']<-.03 for x in local),
            admitted_post_changes=sum(x['certificate_issued'] and x['post_changed'] is True for x in local),
            admitted_post_primary_drops=sum(x['certificate_issued'] and x['post_score']-x['raw_score']<-.03 for x in local),
            actual_qualification_RPC_attempts=sum(x['actual_qualification_RPC_attempts'] for x in local),
            rejected_published_tokens=sum(x['actual_committed_tokens'] for x in local if not x['certificate_issued'] and not x['indeterminate']),
            complete_qualification_ms_sum=sum(x['complete_qualification_ms'] for x in local)))
        # The first original repetition is selected a priori for each model,
        # independent of its outcome. Keep all other parent repeats available.
        first=[x for x in parent_state['completed_cells'] if x.startswith('cells/'+model+'_r1/')];assert len(first)==1
        br=rows(base/first[0]/'responses.jsonl')
        raw=[x for x in br if x['event']=='business' and x.get('condition')=='raw_witness' and x.get('case_id') in cases]
        assert len(raw)==20
        baseline.append(dict(model=model,condition='parent_64_tokens_first_frozen_repetition',cell=first[0],raw_stopped=sum(x['response']['finish_reason']=='stop' for x in raw),raw_length_ended=sum(x['response']['finish_reason']=='length' for x in raw),raw_primary_exact_correct=sum(x['score']>0 for x in raw),raw_witnesses=20))
    assert len(result)==60
    output.mkdir()
    with (output/'case_results_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    report=dict(status='complete',fresh_cells=3,business_generations=240,candidates=60,output_budget=256,
        models=cell_reports,parent_first_repetition=baseline,input_inventory=inventory,new_GPU_requests_by_analysis=0,
        no_service_performance_claim=True,one_repeat_per_model=True,exact_task_scorer_unchanged=True,
        limitations=['Budget sensitivity after observing truncation, not untouched held-out validation.',
                     'EOS completion and integer-only task correctness are distinct.',
                     'Trace-instrumented diagnostic wall is not serving throughput.',
                     'No automatic output-budget escalation; failures and format violations retained.'])
    write(output/'summary_v1.json',report)
    with (output/'analysis_source.py').open('xb') as f:f.write(Path(__file__).read_bytes())
    print(json.dumps(dict(status='complete',models=cell_reports),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--study',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.study.resolve())
