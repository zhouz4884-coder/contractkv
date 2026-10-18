"""Actual real-source layout effects, guard decisions, publication and post-route IDs."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root):
    study=root/'results/tsc_real_repobench_mechanism_20261018';output=study/'analysis_v1';assert not output.exists()
    state=read(study/'execution_state_v1.json');assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==3
    assert read(study/'formal_execution_v1_exit.json')['returncode']==0
    plan=read(study/'protocol_v1.json');cases={x['case_id']:x for x in plan['behavior_cases']};assert len(cases)==6
    base=root/'results/tsc_revision_mechanism_controls_20261018'
    scorer=base/'source_snapshot/scripts/phase20a_official_quality.py'
    spec=importlib.util.spec_from_file_location('frozen_RepoBench_scorer',scorer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    score=lambda response,case:module.standard_score(case['dataset'],case['task'],response['output_text'],case['answer'])[0] if response['success'] else 0.
    shapes={(x['model'],x['source_group'],x['condition']):x for x in rows(study/'inputs_v1/CPU_prompt_shapes_v1.jsonl') if x['tenant']==x['turn']==0}
    runtime={x['path']:x['sha256'] for x in read(base/'preflight_v3/runtime_inventory_v1.json')['files']}
    output_rows=[];models=[]
    for rel in state['completed_cells']:
        cell=study/rel;complete=read(cell/'completion_v1.json');assert complete['status']=='complete' and complete['counts']['business']==24
        for x in complete['files']:assert sha(cell/x['path'])==x['sha256']
        rr=rows(cell/'responses.jsonl');trace=rows(cell/'backend_trace.jsonl');launch=read(cell/'launch_v1.json')
        model=Path(launch['server'][launch['server'].index('--model')+1]).name;policy=launch['environment']['CONTRACTKV_POLICY_HASH']
        assert policy==sha(study/'freeze_v1.json')
        for name in ['vllm.v1.core.block_pool','vllm.v1.core.kv_cache_manager']:
            loaded=[x for x in trace if x['event']=='diagnostic_hook_installed' and x['module']==name]
            assert loaded and all(x['source_sha256']==runtime[name[5:].replace('.','/')+'.py'] for x in loaded)
        qualified={x['case_id']:x for x in rr if x['event']=='qualification'};assert len(qualified)==6
        events=[x for x in rr if x['event']=='behavior_case_complete'];assert len(events)==6
        business=[x for x in rr if x['event']=='business'];assert len(business)==24
        check=read(cell/'actual_prompt_shape_check_v1.json');assert check['checked_successful_actual_requests']+check['failed_transport_requests']==24
        local=[]
        for event in events:
            cid=event['case_id'];case=cases[cid];four=[x for x in business if x['case_id']==cid];assert len(four)==4
            by={x['condition']:x for x in four};raw=by['raw_witness'];again=by['raw_repeat'];candidate=by['unchecked_same_candidate']
            post=next(x for x in four if x['condition'].startswith('post_decision_'))
            for b in four:
                assert score(b['response'],case)==b['score']
                if b['response']['success']:
                    condition='candidate' if b['compiled_input'] and case['diagnostic_layout_level']=='L3' else 'raw'
                    expected=shapes[model,case['source_group'],condition]
                    assert b['response']['prompt_ids_sha256']==expected['prompt_ids_sha256']
            q=qualified[cid];decision=q['result'];issued=decision['certificate_issued'] is True
            published=[x for x in trace if x['event']=='verification_cache_blocks_return' and x['backend_cache_salt']==policy+':'+q['namespace']]
            indeterminate=decision.get('verification_status')=='indeterminate_request_failure'
            if issued:
                assert len(published)==1 and published[0]['requested_tokens']==decision['committed_tokens']>0
                assert decision['committed_tokens']%16==0 and decision['committed_tokens']<=q['plan']['stable_prefix_end_token']
            elif not indeterminate:assert not published
            guard=[x for x in rr if x['event']=='qualification_detail' and x['case_id']==cid and x.get('row_type')=='output_contract_check']
            assert len(guard)==1 and guard[0]['contract']=='one_python_statement'
            ud=event['unchecked_difference'];pd=event['routed_difference'];rd=event['raw_repeat']
            for result,x,y in [(ud,raw['response'],candidate['response']),(pd,raw['response'],post['response']),(rd,raw['response'],again['response'])]:
                if result['available']:
                    assert result['output_ids_equal']==(x['output_token_ids']==y['output_token_ids'])
                    assert result['finish_equal']==(x['finish_reason']==y['finish_reason'])
            hit=None
            if post['response']['success']:
                rid=post['response']['request_id'];lookups=[x for x in trace if x['event']=='lookup_before' and (x['request_id']==rid or x['request_id'].startswith(rid+'-'))]
                assert len(lookups)==1
                returns=[x for x in trace if x['event']=='lookup_return' and x['request_id']==lookups[0]['request_id']];assert len(returns)==1;hit=returns[0]['hit_tokens']
            row=dict(model=model,case_id=cid,source_group=case['source_group'],layout=case['diagnostic_layout_level'],
                raw_score=raw['score'],unchecked_score=candidate['score'],post_score=post['score'],
                raw_repeat_changed=not rd['output_ids_equal'] if rd['available'] else None,
                unchecked_ID_or_finish_changed=(not ud['output_ids_equal'] or not ud['finish_equal']) if ud['available'] else None,
                post_ID_or_finish_changed=(not pd['output_ids_equal'] or not pd['finish_equal']) if pd['available'] else None,
                unchecked_score_up=candidate['score']-raw['score']>.03,unchecked_score_down=candidate['score']-raw['score']<-.03,
                post_score_up=post['score']-raw['score']>.03,post_score_down=post['score']-raw['score']<-.03,
                issued=issued,indeterminate=indeterminate,output_contract_passed=guard[0]['check']['passed'],
                failure_reason=decision.get('failure_reason',''),actual_RPC_attempts=len(decision['attempts']),
                full_qualification_ms=decision['complete_verification_ms'],actual_published_tokens=sum(x['requested_tokens'] for x in published),
                post_native_hit_tokens=hit,raw_finish=raw['response']['finish_reason'],unchecked_finish=candidate['response']['finish_reason'],
                raw_tokens=len(raw['response']['output_token_ids']),unchecked_tokens=len(candidate['response']['output_token_ids']),
                raw_business_ms=raw['response']['latency_ms'],post_business_ms=post['response']['latency_ms'])
            output_rows.append(row);local.append(row)
        strata=[]
        for level in ['L0','L3']:
            subset=[x for x in local if x['layout']==level]
            strata.append(dict(layout=level,candidates=len(subset),admitted=sum(x['issued'] for x in subset),
                observed_unchecked_changes=sum(x['unchecked_ID_or_finish_changed'] is True for x in subset),
                raw_repeat_changes=sum(x['raw_repeat_changed'] is True for x in subset),
                observed_score_up=sum(x['unchecked_score_up'] for x in subset),observed_score_down=sum(x['unchecked_score_down'] for x in subset),
                changed_admitted=sum(x['issued'] and x['unchecked_ID_or_finish_changed'] is True for x in subset),
                admitted_post_changes=sum(x['issued'] and x['post_ID_or_finish_changed'] is True for x in subset),
                guard_rejected=sum(not x['output_contract_passed'] for x in subset),
                RPC_attempts=sum(x['actual_RPC_attempts'] for x in subset),
                rejected_published_tokens=sum(x['actual_published_tokens'] for x in subset if not x['issued'] and not x['indeterminate'])))
        models.append(dict(model=model,strata=strata,diagnostic_client_wall_s=rr[-1]['diagnostic_client_wall_s']))
    assert len(output_rows)==18
    output.mkdir()
    with (output/'case_results_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(output_rows[0]));w.writeheader();w.writerows(output_rows)
    report=dict(status='complete',sources=3,model_cells=3,model_candidate_assessments=18,business_generations=72,models=models,
        actual_RPC_attempts=sum(x['actual_RPC_attempts'] for x in output_rows),all_shape_hashes_and_original_scores_checked=True,
        no_production_inherited_family_eligibility_change=True,raw_repeat_and_identity_controls_not_discarded=True,
        scorer='Frozen SequenceMatcher-based RepoBench similarity, not program execution correctness',
        limitations=['Private diagnostic with one fresh process per model, not a three-repeat production-coverage result.',
            'Identity L0 qualification is a control, not compiled production L0 or an acceleration result.',
            'The existing one_python_statement syntax guard may reject legitimate fragmentary next-line completions.',
            'Observed changes, task-score harm, early guard rejection and actual GPU rejection are separate.'])
    with (output/'summary_v1.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    with (output/'analysis_source.py').open('xb') as f:f.write(Path(__file__).read_bytes())
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
