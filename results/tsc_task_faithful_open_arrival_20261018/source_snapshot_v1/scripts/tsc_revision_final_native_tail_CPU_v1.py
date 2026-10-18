"""Join existing faithful timing tails to actual initial scheduler observations.

No inference or new runtime hooks. Native block reassignments are interval
observations between known hashes, not a complete eviction/preemption counter.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def csvrows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def main(root,output):
    if output.exists():raise FileExistsError('Never overwrite a completed analysis')
    primary=root/'results/tsc_revision_r4/input_fidelity_validation_v1'
    old=root/'results/tsc_final_existing_evidence_CPU_20261018/analysis_v1'
    inventory={x['path']:x['sha256'] for x in csvrows(primary/'raw_evidence_inventory_v1.csv')}
    timing=csvrows(old/'faithful_future_timing_decomposition_v1.csv')
    slow={(x['model'],int(x['repeat']),x['session_id'],int(x['turn_id'])) for x in csvrows(old/'faithful_p99_requests_v1.csv')}
    inputs={};business={};observations={};certs={};physical_changes={};cell_summary=[]
    for cell in sorted((primary/'cells').iterdir()):
        if not cell.is_dir():continue
        actual={}
        for name in ('raw.jsonl','metrics.jsonl'):
            path=cell/name;rel=path.relative_to(root).as_posix();digest=sha(path)
            assert digest==inventory[rel],rel
            inputs[rel]=dict(bytes=path.stat().st_size,sha256=digest)
        with (cell/'raw.jsonl').open(encoding='utf-8') as f:
            for line in f:
                row=json.loads(line)
                if row['row_type'] in ('warm','future'):
                    key=(row['model'],int(row['repeat']),row['policy'],row['session_id'],int(row['turn_id']))
                    assert key not in business;business[key]=row;actual[row['request_id']]=key
                elif row['row_type']=='verification':
                    certs[(cell.name,row['certificate_namespace'],row['query_scope'])]=row
        assert len(actual)==600
        seen={};selected=[];known_reassignments=0
        with (cell/'metrics.jsonl').open(encoding='utf-8') as f:
            for sequence,line in enumerate(f):
                m=json.loads(line)
                if m.get('event')!='prefix_cache_request_observation' or not m.get('initial_prefill_observation'):continue
                changes=[]
                ids=m['physical_block_ids'];hashes=m['physical_block_hashes']
                assert len(ids)==len(hashes)
                for block,block_hash in zip(ids,hashes):
                    if block_hash is None:continue
                    encoded=json.dumps(block_hash,sort_keys=True)
                    previous=seen.get(block)
                    if previous and previous['hash']!=encoded:
                        changes.append(dict(block_id=block,previous_request_id=previous['request_id'],
                            previous_observation_ts=previous['ts'],current_observation_ts=m.get('ts'),
                            boundary='Known physical block ID has a different known hash at this later initial observation; actual intervening eviction time/count unavailable.'))
                    seen[block]=dict(hash=encoded,request_id=m['request_id'],ts=m.get('ts'))
                known_reassignments+=len(changes)
                rid=m['request_id']
                if rid not in actual:continue
                key=actual[rid];assert key not in observations
                assert m['prompt_tokens']==len(business[key]['prompt_token_ids'])
                assert m['used_gpu_blocks']+m['free_gpu_blocks']==m['total_gpu_blocks'] and m['total_gpu_blocks']>0
                assert 0<=m['prefix_hit_tokens']<=m['prompt_tokens']
                observations[key]=m;physical_changes[key]=changes;selected.append(m)
        assert len(selected)==600,cell.name
        cell_summary.append(dict(cell=cell.name,matched_business_requests=len(selected),
            native_total_gpu_blocks=sorted({m['total_gpu_blocks'] for m in selected}),
            max_used_gpu_blocks_at_initial_business_observations=max(m['used_gpu_blocks'] for m in selected),
            max_running_at_initial_business_observations=max(m['scheduler_running_requests'] for m in selected),
            max_waiting_at_initial_business_observations=max(m['scheduler_waiting_requests'] for m in selected),
            observed_known_hash_reassignments_across_all_initial_observations=known_reassignments,
            eviction_count_field_available=any(m.get('prefix_cache_evictions') is not None for m in selected)))
    assert len(cell_summary)==18 and len(observations)==10800
    joined=[];changes_for_tails=[]
    for row in timing:
        model,repeat,sid,turn=row['model'],int(row['repeat']),row['session_id'],int(row['turn_id'])
        key=(model,repeat,'risk-tail',sid,turn);rawkey=(model,repeat,'raw-order',sid,turn)
        b=business[key];m=observations[key];raw=observations[rawkey]
        short={'Qwen3-8B':'qwen','Mistral-7B-Instruct-v0.3':'mistral','Llama-3.1-8B-Instruct':'llama'}[model]
        certificate=certs.get((f'template-fanout_{short}_risk-tail_r{repeat}',b['certificate_namespace'],b['query_scope']))
        compiled=b['effective_level']!='L0'
        committed=int(certificate['committed_tokens']) if compiled and certificate else 0
        if compiled:assert certificate and certificate['certificate_issued'] and committed>0
        item=dict(row,actual_request_id=b['request_id'],raw_actual_request_id=business[rawkey]['request_id'],
            in_per_process_p99_tail=(model,repeat,sid,turn) in slow,
            initial_native_scheduler_wait_ms=m['scheduler_wait_ms'],initial_scheduler_running=m['scheduler_running_requests'],
            initial_scheduler_waiting=m['scheduler_waiting_requests'],total_gpu_blocks=m['total_gpu_blocks'],
            used_gpu_blocks=m['used_gpu_blocks'],free_gpu_blocks=m['free_gpu_blocks'],
            initial_physical_block_count=m['physical_block_count'],initial_cached_physical_entries=m['cached_physical_entries'],
            native_prefix_hit_tokens=m['prefix_hit_tokens'],native_prompt_tokens=m['prompt_tokens'],
            certified_committed_prefix_tokens=committed,
            compiled_prefix_tokens_not_hit=max(0,committed-m['prefix_hit_tokens']) if compiled else 0,
            actual_prefix_hit_class=('full' if m['prefix_hit_tokens']>=committed else 'partial' if m['prefix_hit_tokens'] else 'zero') if compiled else 'not_compiled',
            raw_initial_native_scheduler_wait_ms=raw['scheduler_wait_ms'],raw_initial_scheduler_running=raw['scheduler_running_requests'],
            raw_initial_scheduler_waiting=raw['scheduler_waiting_requests'],raw_used_gpu_blocks=raw['used_gpu_blocks'],
            observed_known_hash_reassignments_in_current_block_table=len(physical_changes[key]),
            complete_native_eviction_or_recomputation_count='not_retained_by_this_initial_scheduler_probe')
        joined.append(item)
        if item['in_per_process_p99_tail']:
            for change in physical_changes[key]:changes_for_tails.append(dict(model=model,repeat=repeat,request_id=b['request_id'],**change))
    assert len(joined)==4860 and sum(x['in_per_process_p99_tail'] for x in joined)==54
    summary=[]
    for model in sorted({x['model'] for x in joined}):
        rows=[x for x in joined if x['model']==model];tail=[x for x in rows if x['in_per_process_p99_tail']]
        summary.append(dict(model=model,requests=len(rows),tail_requests=len(tail),
            compiled_futures=sum(x['route']!='L0' for x in rows),
            compiled_actual_native_hit_classes=dict(Counter(x['actual_prefix_hit_class'] for x in rows if x['route']!='L0')),
            tail_mean_initial_native_wait_ms=statistics.fmean(x['initial_native_scheduler_wait_ms'] for x in tail),
            tail_max_initial_native_wait_ms=max(x['initial_native_scheduler_wait_ms'] for x in tail),
            tail_max_running_at_initial_observation=max(x['initial_scheduler_running'] for x in tail),
            tail_max_waiting_at_initial_observation=max(x['initial_scheduler_waiting'] for x in tail),
            tail_mean_allocator_used_fraction=statistics.fmean(x['used_gpu_blocks']/x['total_gpu_blocks'] for x in tail),
            tail_known_hash_reassignments_in_initial_tables=sum(x['observed_known_hash_reassignments_in_current_block_table'] for x in tail)))
    output.mkdir(parents=True)
    with (output/'native_timing_join_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(joined[0]));w.writeheader();w.writerows(joined)
    for name,data in [('cell_native_capacity_v1.json',cell_summary),('tail_native_summary_v1.json',summary),
                      ('tail_observed_block_hash_changes_v1.json',changes_for_tails),('input_inventory_v1.json',inputs)]:
        with (output/name).open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')
    report=dict(status='existing_native_tail_join_complete',new_GPU_requests=0,actual_business_metric_joins=10800,
        paired_future_native_joins=len(joined),p99_tail_requests=54,analysis_source_sha256=sha(Path(__file__)),
        boundaries=['Initial native scheduler wait is an observed server-side interval, not an isolated GPU prefill timer.',
            'Initial running/waiting/pool observations are request-sampled, not continuous whole-run maxima.',
            'Known hash reassignment is bounded physical recycling evidence, not a complete native eviction counter.',
            'Missing hashes, evictions and decode/recompute steps are never imputed as zero.',
            'Use native Prometheus preemption counters and pool metrics in the new serving study; do not add the heavy residency diagnostic hook to performance timing.'])
    with (output/'completion_v1.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
