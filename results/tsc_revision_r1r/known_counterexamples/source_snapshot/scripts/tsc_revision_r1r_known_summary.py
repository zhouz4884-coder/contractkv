"""Known-counterexample raw/legacy-scope/query-bound behavior; no performance claim."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.tsc_revision_r1r_summary import route_audit


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args()
    errors=[]; cells={}; count=0; new_route=[]; invariants=[]
    for model in ('qwen','mistral','llama'):
        expected=18 if model=='qwen' else 9
        for policy in ('raw-order','legacy-unbound','query-prefix'):
            directory=a.root/model/policy; path=directory/'raw.jsonl'
            if not (directory/'summary.json').exists(): errors.append(model+':'+policy+':missing'); continue
            summary=json.loads((directory/'summary.json').read_text()); rows=read(path)
            recorded=summary.get('raw_file_sha256',summary.get('source_sha256'))
            if hashlib.sha256(path.read_bytes()).hexdigest()!=recorded: errors.append(model+':'+policy+':hash')
            future=[r for r in rows if r['row_type']=='future']; count+=len(future)
            if len(future)!=expected or len({r['request_id'] for r in future})!=expected: errors.append(model+':'+policy+':count_or_identity')
            if any(not r['success'] or not r['token_ids_available'] or not r['metric_join_success'] for r in future): errors.append(model+':'+policy+':actual_evidence')
            if policy=='query-prefix':
                audit=route_audit(rows); new_route.append(audit)
                if audit['scope_invalid_admissions'] or audit['rejected_published_tokens']: errors.append(model+':new_route_invariant')
            cells[(model,policy)]=future
    pairs=[]
    for (model,policy),rows in cells.items():
        if policy=='raw-order' or (model,'raw-order') not in cells: continue
        refs={(r['session_id'],r['turn_id']):r for r in cells[(model,'raw-order')]}
        for r in rows:
            ref=refs[(r['session_id'],r['turn_id'])]
            pairs.append({'model':model,'policy':policy,'source_group':r['source_group'],'session_id':r['session_id'],
                          'family':r['family'],'turn_id':r['turn_id'],'effective_level':r['effective_level'],
                          'raw_score':ref['task_score'],'candidate_score':r['task_score'],'quality_drop':ref['task_score']-r['task_score'],
                          'first_diverging_token':first_divergence(ref['output_token_ids'],r['output_token_ids']),
                          'raw_text':ref['output_text'],'candidate_text':r['output_text']})
    grouped=defaultdict(list)
    for r in pairs: grouped[(r['model'],r['policy'],r['source_group'])].append(r)
    table=[]
    for key,rows in sorted(grouped.items()):
        table.append({'model':key[0],'policy':key[1],'source_group':key[2],'pairs':len(rows),
                      'compiled_pairs':sum(r['effective_level']!='L0' for r in rows),
                      'token_divergences':sum(r['first_diverging_token']!=-1 for r in rows),
                      'material_drops_gt0_03':sum(r['quality_drop']>.03 for r in rows),
                      'compiled_material_drops':sum(r['quality_drop']>.03 and r['effective_level']!='L0' for r in rows),
                      'raw_mean_score':sum(r['raw_score'] for r in rows)/len(rows),
                      'candidate_mean_score':sum(r['candidate_score'] for r in rows)/len(rows)})
    if table: write(a.root/'quality_summary_v1.csv',table); write(a.root/'quality_pairs_v1.csv',pairs)
    record={'schema_version':'tsc-r1r.known-counterexample-completion.v1','complete_policy_cells':len(cells),
            'expected_policy_cells':9,'future_generations':count,'expected_future_generations':108,
            'errors':errors,'execution_complete':len(cells)==9 and count==108 and not errors,
            'known_model_source_units':4,'selected_after_observed_R1_failures':True,'heldout_generalization_evidence':False,
            'same_new_backend_for_all_policies':True,'legacy_scope_client_is_controlled_adaptation_not_original_runtime_reproduction':True,
            'one_fresh_process_per_model_policies_share_engine':True,'no_original_batch_shape_identity_claim':True,
            'performance_claim':False,'new_route_audit':new_route}
    (a.root/'completion_audit_v1.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))
    return 0 if record['execution_complete'] else 2


if __name__=='__main__': raise SystemExit(main())
