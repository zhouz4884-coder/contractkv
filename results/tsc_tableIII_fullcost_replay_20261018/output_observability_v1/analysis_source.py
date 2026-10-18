"""Audit exact retained output-text lengths and real verifier HTTP call counts.

The archived client cannot supply per-request token lengths/IDs it did not
retain. This audit makes that boundary explicit instead of retokenizing text.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]


def main(study,output):
    if output.exists():raise FileExistsError(output)
    state=read(study/'execution_state_v1.json')
    assert state['status']=='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS' and state['formal_GPU_cells_completed']==24
    assert len(state['completed_pairs'])==12
    entries=[];cells=[];provenance=[]
    pattern=re.compile(r'INFO:\s+127\.0\.0\.1:\d+ - "POST /v1/contractkv/verify HTTP/1\.1" (\d{3})\b')
    for pair_name in state['completed_pairs']:
        pair=study/pair_name;info=read(pair/'pair_completion_v1.json');model=info['model'];repeat=info['repeat']
        policies={}
        for policy in ('raw','contract'):
            cell=pair/policy;request_path=cell/'requests.jsonl';rr=rows(request_path)
            ff={(r['session_id'],int(r['turn_id'])):r for r in rr if r.get('row_type')=='future'}
            policies[policy]=ff;events=rows(cell/'audit/complete_controller_events_v1.jsonl')
            calls=[x for x in events if x['event']=='compact_verify']
            http=[]
            with (cell/'server.log').open(encoding='utf-8',errors='replace') as f:
                for line in f:
                    match=pattern.search(line)
                    if match:http.append(int(match[1]))
            native=rows(cell/'metrics.jsonl')
            native=[x for x in native if x.get('event')=='prefix_cache_request_observation']
            cells.append(dict(model=model,repeat=repeat,policy=policy,future_requests=len(ff),
                wrapped_verification_attempts=len(calls),actual_verifier_HTTP_access_records=len(http),
                verifier_HTTP_status_counts=dict(Counter(http)),all_wrapped_attempts_have_positive_elapsed=all(x['elapsed_ms']>0 for x in calls),
                native_initial_request_records=len(native),native_initial_unique_request_IDs=len({x['request_id'] for x in native}),
                native_probe_is_initial_observation_not_GPU_forward_counter=True,
                future_rows_with_output_ID_list=sum(isinstance(x.get('output_token_ids'),list) and bool(x['output_token_ids']) for x in ff.values()),
                future_rows_with_prompt_ID_list=sum(isinstance(x.get('prompt_token_ids'),list) and bool(x['prompt_token_ids']) for x in ff.values()),
                future_rows_with_stored_completion_tokens=sum(isinstance(x.get('completion_tokens'),(int,float)) for x in ff.values()),
                future_rows_with_stored_finish_reason=sum('finish_reason' in x for x in ff.values()),
                raw_reference_canary_finish_counts=dict(Counter(str(x.get('raw_finish_reason','not_retained')) for x in rr if x.get('row_type')=='canary'))))
            for name in ('requests.jsonl','metrics.jsonl','server.log','final_metrics.txt','audit/complete_controller_events_v1.jsonl'):
                p=cell/name;provenance.append(dict(path=str(p.relative_to(study)),sha256=sha(p),bytes=p.stat().st_size))
        assert set(policies['raw'])==set(policies['contract'])
        for key,r in policies['raw'].items():
            c=policies['contract'][key]
            assert isinstance(r['output_text'],str) and isinstance(c['output_text'],str)
            a,b=len(r['output_text']),len(c['output_text'])
            entries.append(dict(model=model,repeat=repeat,session_id=key[0],turn_id=key[1],
                effective_level=c.get('effective_level',c.get('effective_policy')),
                raw_output_characters=a,contract_output_characters=b,character_delta=b-a,
                raw_output_UTF8_bytes=len(r['output_text'].encode('utf-8')),contract_output_UTF8_bytes=len(c['output_text'].encode('utf-8')),
                raw_output_whitespace_units=len(r['output_text'].split()),contract_output_whitespace_units=len(c['output_text'].split()),
                exact_text_equal=r['output_text']==c['output_text'],
                length_unit_boundary='Exact retained text characters/UTF8 bytes; whitespace units are not model tokens.',
                actual_per_request_output_token_length='not_retained_by_archived_client',
                raw_finish_reason=r.get('finish_reason','not_retained_by_archived_client'),
                contract_finish_reason=c.get('finish_reason','not_retained_by_archived_client')))
    assert len(entries)==4725 and len(cells)==24
    output.mkdir(parents=True)
    with (output/'retained_output_text_lengths_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(entries[0]));w.writeheader();w.writerows(entries)
    grouped=defaultdict(list)
    for x in entries:grouped[x['model']].append(x)
    summary=[dict(model=k,pairs=len(v),
        mean_raw_output_characters=statistics.fmean(x['raw_output_characters'] for x in v),
        mean_contract_output_characters=statistics.fmean(x['contract_output_characters'] for x in v),
        longer_contract_text=sum(x['character_delta']>0 for x in v),shorter_contract_text=sum(x['character_delta']<0 for x in v),
        equal_character_length=sum(x['character_delta']==0 for x in v),equal_text=sum(x['exact_text_equal'] for x in v)) for k,v in grouped.items()]
    result=dict(status='retained_output_and_HTTP_observability_audit_complete',future_pairs=len(entries),cells=cells,
        by_model=summary,source_sha256=sha(Path(__file__)),new_GPU_requests=0,
        exact_per_request_output_text_lengths=True,per_request_model_token_lengths_recovered=False,
        per_request_output_IDs_recovered=False,
        boundaries=['All original output texts are retained; length means characters/UTF8 bytes unless explicitly stated otherwise.',
            'Actual server generation-token lifetime totals and histograms are in analysis_v3/native_generation_and_cache_totals_v1.json. They are not per-future lengths.',
            'HTTP access records prove endpoint requests, not a number of GPU kernels or pure GPU durations.',
            'A legacy request-ID may be reused across level descent. An initial-request-only metric probe is not a verifier attempt/forward counter.',
            'Unknown future cutoff/EOS and token-ID fields remain unavailable; no completed GPU cell was repeated or client modified to fill them.'])
    for name,value in [('summary_v1.json',result),('input_inventory_v1.json',provenance)]:
        with (output/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    with (output/'analysis_source.py').open('xb') as f:f.write(Path(__file__).read_bytes())
    print(json.dumps(dict(pairs=len(entries),cells=len(cells),actual_HTTP_verification_requests=sum(x['actual_verifier_HTTP_access_records'] for x in cells))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.study.resolve(),a.output.resolve())
