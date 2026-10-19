"""Join actual business IDs, strict decisions, publication and physical hits."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):return [json.loads(x) for x in p.open(encoding='utf-8') if x.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def output_csv(p,rr):
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)


def analyze(study,output):
    assert not output.exists();state=read(study/'execution_state_v1.json')
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==9
    plan=read(study/'protocol_v1.json');cases={x['case_id']:x for x in plan['behavior_cases']+plan['manifest_cases']}
    detail=[];manifest=[];registration=[];cell_summary=[];verification_rows=[];tokenizers={}
    shapes={(x['model'],x['case_id'],x['condition']):x for x in read(study/'preflight_v3/input_shapes_v1.json')['shapes']}
    runtime_files={x['path']:x['sha256'] for x in read(study/'preflight_v3/runtime_inventory_v1.json')['files']}
    for rel in state['completed_cells']:
        cell=study/rel;completion=read(cell/'completion_v1.json')
        for x in completion['files']:assert sha(cell/x['path'])==x['sha256'],str(cell/x['path'])
        rr=rows(cell/'responses.jsonl');traces=rows(cell/'backend_trace.jsonl')
        installed=[x for x in traces if x['event']=='diagnostic_hook_installed']
        for module in ('vllm.v1.core.block_pool','vllm.v1.core.kv_cache_manager'):
            source=module[len('vllm.'):].replace('.','/')+'.py'
            matches=[x for x in installed if x['module']==module]
            assert matches and all(x['source_sha256']==runtime_files[source] for x in matches),'Loaded core module differs from the frozen isolated runtime'
        vt=rows(cell/'verify_trace.jsonl') if (cell/'verify_trace.jsonl').exists() else []
        assert rr[-1]['event']=='diagnostic_cell_complete'
        assert len([r for r in rr if r['event']=='business'])==95
        businesses={r['response']['request_id']:r for r in rr if r['event']=='business'}
        launch=read(cell/'launch_v1.json');modelpath=Path(launch['server'][launch['server'].index('--model')+1]);modelname=modelpath.name
        for b in businesses.values():
            if b['response']['success']:
                expected=shapes[(modelname,b['case_id'],'candidate' if b['compiled_input'] else 'raw')]
                assert b['response']['prompt_ids_sha256']==expected['prompt_ids_sha256'],'Actual service prompt differs from frozen offline input'
        if modelpath.is_dir() and modelname not in tokenizers:
            from transformers import AutoTokenizer
            tokenizers[modelname]=AutoTokenizer.from_pretrained(str(modelpath),local_files_only=True)
        def native_observation(b):
            response=b['response'];rid=response['request_id']
            if not response['success']:return None,None,None
            matched=[x for x in lookups if x['request_id']==rid or x['request_id'].startswith(rid+'-')]
            assert len(matched)==1,'Actual business request does not have one native lookup'
            lookup=matched[0];hit=returns[lookup['request_id']]['hit_tokens']
            assert lookup['backend_cache_salt']==b['actual_wire_salt']
            marker=cases[b['case_id']].get('synthetic_marker');contains=None
            if marker and modelname in tokenizers:
                contains=marker in tokenizers[modelname].decode(response['prompt_token_ids'][:hit],skip_special_tokens=False)
            return lookup,hit,contains
        qualified={r['case_id']:r for r in rr if r['event']=='qualification'}
        lookups=[t for t in traces if t['event']=='lookup_before']
        returns={t['request_id']:t for t in traces if t['event']=='lookup_return'}
        commits=[t for t in traces if t['event']=='verification_cache_blocks_return']
        for q in qualified.values():
            decision=q['result'];attempts=decision['attempts'];salt=read(cell/'launch_v1.json')['environment']['CONTRACTKV_POLICY_HASH']+':'+q['namespace']
            published=[t for t in commits if t['backend_cache_salt']==salt]
            accepted=decision['certificate_issued'] is True
            indeterminate=decision.get('verification_status')=='indeterminate_request_failure'
            assert len(published)<=1
            if accepted:
                assert len(published)==1
                n=decision['committed_tokens'];assert published[0]['requested_tokens']==n and n>0 and n%16==0
                assert n<=q['plan']['stable_prefix_end_token']
                blockchain=published[0]['blocks'][0][:n//16]
                assert len(blockchain)==n//16 and all(b['hash'] is not None for b in blockchain)
            elif not indeterminate:assert not published,'Rejected/abstained candidate has an actual verification publication event'
            verifier_trace=[x for x in vt if any(x['request_id']==a.get('request_id') or
                x['request_id'].startswith(str(a.get('request_id'))+'-') for a in attempts)]
            # Some retained response structs do not echo the submitted RID;
            # use the logged request detail, never guessed numeric indices.
            request_details=[r for r in rr if r['event']=='qualification_detail' and r['case_id']==q['case_id'] and r.get('row_type')=='verification_request']
            if request_details:
                rid=request_details[0]['request_id']
                verifier_trace=[x for x in vt if x['request_id']==rid or x['request_id'].startswith(rid+'-')]
            verification_rows.append(dict(cell=rr[0]['cell_id'],model=rr[0]['model'],case_id=q['case_id'],
                issued=accepted,verification_calls=len(attempts),failure_reason=decision.get('failure_reason',''),
                indeterminate_response=indeterminate,
                full_qualification_ms=decision['complete_verification_ms'],published_events=len(published),
                committed_tokens=decision.get('committed_tokens',0),
                actual_backend_committed_tokens=sum(t['requested_tokens'] for t in published),
                termination_only_teacher_forced_failure=any(all(rank==1 for rank in x['candidate_ranks']) and x['terminal_stop_rank']!=1 for x in verifier_trace)))
        for r in rr:
            if r['event']!='behavior_case_complete':continue
            q=qualified[r['case_id']];case=cases[r['case_id']]
            actual=[x for x in businesses.values() if x['case_id']==r['case_id']]
            assert len(actual)==4
            bycondition={x['condition']:x for x in actual}
            post=next(x for x in actual if x['condition'].startswith('post_decision_'))
            raw=bycondition['raw_witness']['response'];again=bycondition['raw_repeat']['response']
            if raw['success'] and again['success']:assert raw['prompt_token_ids']==again['prompt_token_ids']
            if r['certificate_issued'] and post['response']['success']:
                assert post['response']['prompt_token_ids']==q['plan']['prompt_token_ids']
            if not r['certificate_issued'] and post['response']['success'] and raw['success']:
                assert post['response']['prompt_token_ids']==raw['prompt_token_ids'],'Fallback changed the actual raw prompt'
            detail.append(dict(cell=r['cell_id'],model=r['model'],case_id=r['case_id'],family=r['family'],
                declared_risk=r['declared_risk'],raw_repeat_stable=r['raw_repeat'].get('output_ids_equal'),
                unchecked_behavior_changed=(not r['unchecked_difference']['output_ids_equal']) if r['unchecked_difference']['available'] else None,
                unchecked_finish_changed=(not r['unchecked_difference']['finish_equal']) if r['unchecked_difference']['available'] else None,
                unchecked_score_up=r['unchecked_score']-r['raw_score']>0.03,
                unchecked_score_down=r['unchecked_score']-r['raw_score']< -0.03,
                certificate_issued=r['certificate_issued'],
                actual_post_route_ID_difference=(not r['routed_difference']['output_ids_equal']) if r['routed_difference']['available'] else None,
                actual_post_route_finish_difference=(not r['routed_difference']['finish_equal']) if r['routed_difference']['available'] else None,
                post_route_score_up=r['routed_score']-r['raw_score']>0.03,
                post_route_score_down=r['routed_score']-r['raw_score']< -0.03,
                raw_score=r['raw_score'],unchecked_score=r['unchecked_score'],post_route_score=r['routed_score'],
                all_four_business_success=all(x['response']['success'] for x in actual),
                first_unchecked_difference=r['unchecked_difference'].get('first_difference_index')))
        publication={r['namespace']:r for r in rr if r['event']=='manifest_publication'}
        for r in rr:
            if r['event']=='registration_control':
                ns=r['namespace'];salt=read(cell/'launch_v1.json')['environment']['CONTRACTKV_POLICY_HASH']+':'+ns
                assert not [t for t in commits if t['backend_cache_salt']==salt]
                b=businesses[r['actual_raw_request_id']];lookup,hit,contains=native_observation(b)
                registration.append(dict(cell=r['cell_id'],model=r['model'],control=r['control'],
                    registration_rejected=bool(r['errors']),verifier_dispatched=r['verifier_dispatched'],
                    certified_publication_events=0,actual_raw_request_id=r['actual_raw_request_id'],
                    raw_native_hit_tokens=hit,raw_native_hit_contains_synthetic_private_marker=contains,
                    actual_raw_salt=b['actual_wire_salt']))
            if r['event']!='manifest_request_complete':continue
            p=publication[r['namespace']];b=businesses[r['actual_business_request_id']]
            lookup,hit,contains=native_observation(b);published_chain_match=None
            q=qualified[p['case_id']];pub_salt=launch['environment']['CONTRACTKV_POLICY_HASH']+':'+r['namespace']
            actual_pub=[x for x in commits if x['backend_cache_salt']==pub_salt]
            actual_commit=sum(x['requested_tokens'] for x in actual_pub);actual_marker=None
            if actual_commit and modelname in tokenizers:
                actual_marker=cases[p['case_id']]['synthetic_marker'] in tokenizers[modelname].decode(q['plan']['prompt_token_ids'][:actual_commit],skip_special_tokens=False)
            elif not actual_commit:actual_marker=False
            if b['response']['success']:
                if r['compiled_route']:
                    n=p['committed_tokens'];pub=[x for x in commits if x['backend_cache_salt']==lookup['backend_cache_salt'] and x['seq']<lookup['seq']]
                    assert len(pub)==1
                    chain=[x['hash'] for x in pub[0]['blocks'][0][:n//16]]
                    published_chain_match=chain==lookup['backend_hashes'][:n//16];assert published_chain_match
            manifest.append(dict(cell=r['cell_id'],model=r['model'],case_id=r['case_id'],namespace=r['namespace'],
                trusted_semantic_mislabel=r['trusted_semantic_mislabel'],control=r['control'],
                behavior_certificate_issued=p['certificate_issued'],committed_tokens=p['committed_tokens'],
                synthetic_marker_in_committed_prefix=p['synthetic_marker_in_committed_prefix'],
                actual_backend_committed_tokens=actual_commit,actual_backend_published_synthetic_marker=actual_marker,
                compiled_route=r['compiled_route'],binding_errors=';'.join(r['binding_errors']),observation_scope_errors=';'.join(r['observation_scope_errors']),
                native_hit_tokens=hit,published_chain_matches_request=published_chain_match,
                native_hit_contains_synthetic_private_marker=contains,actual_wire_salt=b['actual_wire_salt'],
                full_committed_prefix_hit=(hit>=p['committed_tokens']) if r['compiled_route'] and hit is not None else None,
                actual_business_success=b['response']['success'],score=r['score']))
        cell_summary.append(dict(cell=rr[0]['cell_id'],model=rr[0]['model'],counts=rr[-1]['counts'],
            whole_diagnostic_client_wall_s=rr[-1]['diagnostic_client_wall_s'],service_performance_claim=False))
    assert len(detail)==180 and len(manifest)==72 and len(registration)==27 and len(verification_rows)==198
    output.mkdir(parents=True)
    for name,data in [('behavior_pairs_v1.csv',detail),('manifest_paths_v1.csv',manifest),
                      ('registration_paths_v1.csv',registration),('verification_cost_publication_v1.csv',verification_rows)]:output_csv(output/name,data)
    summary=[]
    for model in sorted({r['model'] for r in detail}):
        rr=[r for r in detail if r['model']==model]
        strata=[]
        for family in sorted({r['family'] for r in rr}):
            gg=[r for r in rr if r['family']==family]
            strata.append(dict(family=family,pairs=len(gg),safe_admitted=sum(r['certificate_issued'] and r['declared_risk']=='safe' for r in gg),
                observed_unchecked_changes=sum(r['unchecked_behavior_changed'] is True for r in gg),
                observed_unchecked_drops=sum(r['unchecked_score_down'] for r in gg),
                changed_cases_rejected=sum(r['unchecked_behavior_changed'] is True and not r['certificate_issued'] for r in gg),
                admitted_post_route_divergences=sum(r['certificate_issued'] and r['actual_post_route_ID_difference'] is True for r in gg),
                admitted_post_route_finish_divergences=sum(r['certificate_issued'] and r['actual_post_route_finish_difference'] is True for r in gg),
                post_route_score_drops=sum(r['post_route_score_down'] for r in gg),
                raw_repeat_ID_changes=sum(r['raw_repeat_stable'] is False for r in gg)))
        summary.append(dict(model=model,strata=strata))
    report=dict(status='complete',cells=cell_summary,behavior_candidates=180,manifest_business_controls=72,
        registration_reject_controls=27,all_verification_decisions=198,maximum_GPU_calls=198,
        actual_GPU_calls=sum(r['verification_calls'] for r in verification_rows),
        rejected_publication_events=sum(r['published_events'] for r in verification_rows if not r['issued'] and not r['indeterminate_response']),
        indeterminate_verification_responses=sum(r['indeterminate_response'] for r in verification_rows),
        indeterminate_with_publication=sum(r['indeterminate_response'] and r['published_events']>0 for r in verification_rows),
        behavior_by_model=summary,
        synthetic_mislabel_published_cells=len({r['cell'] for r in manifest if r['trusted_semantic_mislabel'] and r['actual_backend_published_synthetic_marker'] is True}),
        positive_hit_controls=sum(r['control']=='matching_private_value_same_domain' and r['full_committed_prefix_hit'] is True for r in manifest),
        total_matching_same_domain_controls=sum(r['control']=='matching_private_value_same_domain' for r in manifest),
        raw_other_domain_native_marker_hits=(sum(r['control']=='matching_private_value_other_domain' and not r['compiled_route'] and r['native_hit_contains_synthetic_private_marker'] is True for r in manifest) if len(tokenizers)==3 else None),
        raw_tokenizer_hit_decode_available=len(tokenizers)==3,
        limitations=plan['claim_boundary']+['Registration roles/domains are trusted-adapter inputs; not a public IAM gateway.',
            'Synthetic marker publication proves this configuration trust boundary; it is not an exfiltration attack or timing-channel defense.',
            'Native raw APC uses the original unsalted fallback path. Rejecting a certified binding does not imply global raw APC isolation; actual raw hits/marker coverage are separately reported.',
            'Raw repeat fluctuations are retained and reported; finite controlled cases do not prove universal behavior equivalence.',
            'No benchmark-family deployment eligibility, economic threshold or serving scheduler was changed.'])
    write(output/'summary_v1.json',report)
    print(json.dumps({k:report[k] for k in ['status','behavior_candidates','actual_GPU_calls','rejected_publication_events','synthetic_mislabel_published_cells','positive_hit_controls','total_matching_same_domain_controls']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.study,a.output)
