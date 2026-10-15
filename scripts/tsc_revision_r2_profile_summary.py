"""Audit development controls and export data for prospective policy selection."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_live import FROZEN_LEVELS
from scripts.tsc_revision_summarize import first_divergence

MODELS={'qwen':'Qwen3-8B','mistral':'Mistral-7B-Instruct-v0.3','llama':'Llama-3.1-8B-Instruct'}
def read(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def audit(root, output):
    project=root.parents[2]; freeze=json.loads((root/'freeze.json').read_text(encoding='utf-8'))
    sources=read(root/'source_snapshot/results/tsc_revision_r2/inputs/development_sessions_v1.jsonl')
    source={x['revision_source_group']:x for x in sources}
    config=json.loads((root/'source_snapshot/configs/tsc_revision_r2_profile_v1.json').read_text(encoding='utf-8'))
    errors=[]; slots=[]; pairs=[]; coefficients=[]; totals=[]
    for item in freeze['files']:
        if sha(root/'source_snapshot'/item['path'])!=item['sha256']: errors.append('snapshot:'+item['path'])
        if (project/item['path']).exists() and sha(project/item['path'])!=item['sha256']: errors.append('current:'+item['path'])
    for name,identity in MODELS.items():
        base=root/name; rows=read(base/'raw.jsonl'); summary=json.loads((base/'raw.summary.json').read_text(encoding='utf-8'))
        if not summary['execution_complete'] or sha(base/'raw.jsonl')!=summary['raw_sha256']: errors.append(name+':completion/hash')
        metrics={r['request_id']:r for r in read(base/'metrics.jsonl') if r.get('event')=='prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        generations=[r for r in rows if r['row_type']=='generation']
        levelslots=[r for r in rows if r['row_type']=='level_slot']
        before={r['request_id']:r for r in rows if r['row_type']=='qualification_request'}
        refs={r['request_id']:r for r in generations if r['role']=='reference'}
        raw={(r['source_group'],r['query_scope'],r['turn'],r['tenant']):r for r in generations if r['role']=='raw_future'}
        candidates={}
        for r in generations:
            if r['role']=='candidate_future': candidates.setdefault(r['qualification_request_id'],[]).append(r)
        eligible=[s for s in sources if FROZEN_LEVELS[identity][s['revision_family']]!='L0']
        expected={(s['revision_source_group'],p['witness_turn'],f'L{i}') for s in eligible for p in config['query_probes'] for i in range(1,int(FROZEN_LEVELS[identity][s['revision_family']][1:])+1)}
        actual={(s['source_group'],s['witness_turn'],s['level']) for s in levelslots}
        if expected!=actual or len(actual)!=len(levelslots) or len(levelslots)!=config['expected_level_slots'][name]: errors.append(name+':level/source/query coverage')
        if len(generations)!=summary['actual_generations'] or len(raw)!=len(eligible)*12 or len(refs)!=len(eligible)*6: errors.append(name+':generation coverage')
        seen=set()
        for r in generations:
            rid=r['request_id']; event=metrics.get(rid); ids=r['prompt_token_ids']; sample=source[r['source_group']]
            if rid in seen: errors.append(name+':duplicate request')
            seen.add(rid)
            if not (r['success'] and r['stream_done'] and r['prompt_ids_available'] and r['token_ids_available'] and r['prompt_tokens']==len(ids) and r['completion_tokens']==len(r['output_token_ids']) and digest(ids)==r['prompt_ids_sha256']): errors.append(name+':IDs/usage/hash')
            if not event or event['prompt_tokens']!=len(ids): errors.append(name+':metric join')
            score,metric,provenance=standard_score(sample['dataset'],sample['task'],r['output_text'],sample.get('answer',''))
            if (score,metric,provenance)!=(r['task_score'],r['task_metric'],r['metric_source']): errors.append(name+':official score')
            if r['role']=='reference':
                if not (r['witness_available'] and len(r['reference_margins'])==len(r['output_token_ids']) and all(math.isfinite(v) for v in r['reference_margins'])): errors.append(name+':reference margins')
            if r['role']=='raw_future' and event:
                new=len(ids)-event['prefix_hit_tokens']
                coefficients.append({'model_key':name,'model':identity,'family':r['family'],'source_group':r['source_group'],'query_scope':r['query_scope'],'new_prefill_tokens':new,'native_prefix_hit_tokens':event['prefix_hit_tokens'],'ttft_ms':r['ttft_ms'],'ttft_per_new_prefill_token_ms':r['ttft_ms']/new if new>0 else None})
        rejected_pub=0; issued=0
        for r in levelslots:
            if not r['attempted']: errors.append(name+':unexpected unattempted profile slot'); continue
            rid=r['request_id']; payload=r['payload']; plan=r['plan']; response=r['response']; ref=refs[r['reference_request_id']]
            event=metrics.get(rid)
            if rid in seen or not event or event['prompt_tokens']!=len(payload['prompt_token_ids']): errors.append(name+':qualification metric/ID')
            seen.add(rid)
            if rid not in before or before[rid]['payload']!=payload or before[rid]['prompt_ids_sha256']!=digest(payload['prompt_token_ids']) or not before[rid]['request_hash_computed_before_dispatch']: errors.append(name+':pre-dispatch identity')
            if payload['prompt_token_ids']!=plan['prompt_token_ids']+ref['output_token_ids'] or payload['reference_raw_margins']!=ref['reference_margins'][:-1] or payload['reference_answer_ids']!=ref['output_token_ids'][:-1] or payload['terminal_stop_token_id']!=ref['output_token_ids'][-1]: errors.append(name+':forced path identity')
            if plan['prompt_ids_sha256']!=digest(plan['prompt_token_ids']) or payload['stable_content_hash']!=digest(plan['prompt_token_ids'][:plan['stable_prefix_end_token']]): errors.append(name+':stable identity')
            issued+=bool(response['certificate_issued'])
            if not response['certificate_issued']: rejected_pub+=int(response['committed_tokens'])
            else:
                if response['committed_tokens']!=plan['stable_full_blocks']*16: errors.append(name+':publication length')
            observed=candidates.get(rid,[])
            if len(observed)!=(4 if response['certificate_issued'] else 0): errors.append(name+':outcome-dependent control count')
            drops=0
            for candidate in observed:
                match=raw[(candidate['source_group'],candidate['query_scope'],candidate['turn'],candidate['tenant'])]
                hit=metrics[candidate['request_id']]['prefix_hit_tokens']; commit=response['committed_tokens']
                if candidate['cache_salt']!=payload['cache_salt'] or hit<commit or candidate['prompt_token_ids'][:commit]!=plan['prompt_token_ids'][:commit]: errors.append(name+':actual certified reuse')
                drop=match['task_score']-candidate['task_score']>.03; drops+=drop
                pairs.append({'model_key':name,'family':r['family'],'source_group':r['source_group'],'query_scope':r['query_scope'],'level':r['level'],'qualification_request_id':rid,'turn':candidate['turn'],'tenant':candidate['tenant'],'raw_score':match['task_score'],'candidate_score':candidate['task_score'],'material_drop':drop,'first_ID_divergence':first_divergence(match['output_token_ids'],candidate['output_token_ids']),'prefix_hit_tokens':hit})
            slots.append({'model_key':name,'model':identity,'family':r['family'],'source_group':r['source_group'],'query_scope':r['query_scope'],'witness_turn':r['witness_turn'],'level':r['level'],'qualification_request_id':rid,'raw_full_min_including_eos':min(ref['reference_margins']),'candidate_answer_min':response['candidate_margin_min'],'candidate_eos_margin':response['terminal_stop_margin'],'rank_path_certificate_issued':response['certificate_issued'],'stable_full_blocks':plan['stable_full_blocks'],'planning_ms':plan['cpu_http_preparation_ms'],'verification_rpc_ms':r['verification_http_ms'],'complete_qualification_ms':r['complete_qualification_ms'],'observed_candidate_futures':len(observed),'observed_material_drops':drops})
        if rejected_pub or issued!=summary['issued_qualifications']: errors.append(name+':publication/issued count')
        joins=summary['request_metric_joins']
        if len(joins)!=len(seen) or {x['request_id'] for x in joins}!=seen or not all(x['matched'] for x in joins): errors.append(name+':closed metric joins')
        manifest=json.loads((base/'runtime_manifest.json').read_text(encoding='utf-8'))
        if manifest['freeze_sha256']!=sha(root/'freeze.json') or not manifest['registry_point_in_time_full_weight_hashes_present']: errors.append(name+':runtime registry')
        totals.append({'model':name,'actual_generations':len(generations),'qualification_calls':len(levelslots),'issued':issued,'actual_paired_compiled_controls':sum(len(v) for v in candidates.values()),'rejected_published_tokens':rejected_pub,'metric_joins':len(seen),'declared_gpu_lane':manifest['declared_gpu_lane'],'raw_sha256':sha(base/'raw.jsonl')})
    output.mkdir(parents=True,exist_ok=True)
    for name,values in [('slots_v1.csv',slots),('paired_controls_v1.csv',pairs),('latency_predictor_observations_v1.csv',coefficients)]:
        with (output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(values[0])); writer.writeheader();writer.writerows(values)
    write(output/'selection_input_v1.json',{'slots':slots,'latency_predictor_observations':coefficients,'frozen_generation_source_sha256':sha(root/'freeze.json'),'profile_is_development_counterfactual_not_serving_efficacy':True})
    result={'schema_version':'tsc-r2.development-profile-audit.v1','execution_complete':not errors,'errors':sorted(set(errors)),'cases':totals,'frozen_files':len(freeze['files']),'all_candidate_calls_are_post_issued_actual_reuse_controls':True,'unexecuted_candidates_are_not_real_raw_fallbacks':True,'not_end_to_end_policy_efficacy':True}
    write(output/'completion_audit_v1.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(a.root.resolve(),a.output);print(json.dumps(result));raise SystemExit(0 if result['execution_complete'] else 2)
