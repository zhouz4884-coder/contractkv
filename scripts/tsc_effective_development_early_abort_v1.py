"""Read actual completed development traces; never perform GPU work."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_effective_early_abort_diagnostic_v1 import observation

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:
        return [json.loads(s) for s in f if s.strip()]

def main(root, output):
    assert not output.exists()
    study = root/'results/tsc_effective_reuse_recovery_20261019'
    result, inventory = [], []
    for relative in read(study/'development_execution_state_v2.json')['completed_cells']:
        cell = study/relative
        traces = {r['request_id']: r for r in lines(cell/'verify_trace.jsonl')
                  if r.get('event') == 'r2_actual_verify_answer_eos_rows'}
        data = lines(cell/'responses.jsonl'); model = data[0]['model']
        for arm in ('V5_authorized','deferred_authorized'):
            rr=lines(cell/arm/'raw.jsonl')
            requests={r['request_id']: r['payload'] for r in rr if r['row_type']=='verification_request'}
            for r in rr:
                if r['row_type'] != 'verification': continue
                for attempt in r['attempts']:
                    payload=requests[attempt['request_id']]
                    result.append(observation('effective-development-full-runner',model,r['family'],arm,
                        payload,attempt,traces[payload['request_id']],r.get('raw_all_tokens_margin_min')))
        for r in data:
            if r['event'] != 'candidate_feasibility': continue
            requests={q['request_id']: q['payload'] for q in r['verification_rows'] if q['row_type']=='verification_request'}
            for attempt in r['result']['attempts']:
                payload=requests[attempt['request_id']]
                result.append(observation('effective-development-new-source-probe',model,r['family'],r['level'],
                    payload,attempt,traces[payload['request_id']],r['result'].get('raw_all_tokens_margin_min')))
        inventory.extend(dict(path=str((cell/name).relative_to(root)),sha256=hashlib.sha256((cell/name).read_bytes()).hexdigest())
                         for name in ['responses.jsonl','verify_trace.jsonl'])
    failed=[r for r in result if not r['accepted']]
    answer=dict(new_GPU_requests=0,actual_RPCs=len(result),PASS=sum(r['accepted'] for r in result),FAIL=len(failed),
        first_token_failures=sum(r['earliest_candidate_failure_index']==0 for r in failed),
        failed_RPC_ms=sum(r['actual_verification_RPC_ms'] or 0 for r in failed),
        hypothetical_Raw_0125_skipped=sum(r['proposed_Raw_0125_gate_would_skip'] for r in result),
        failed_cached_prefix_read_tokens=[r['actual_cached_prefix_read_tokens'] for r in failed],
        failed_tail_slot_fractions=[r['optimistic_tail_slot_fraction'] for r in failed],rows=result,inputs=inventory,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        no_runtime_or_gate_changed=True,
        boundary='Development cells have shared-engine predecessor state and heavy tracing. Token-slot proxy and RPC timing are not GPU kernel costs or an early-abort speedup.')
    with output.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(answer,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in answer.items() if k not in {'rows','inputs'}}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
