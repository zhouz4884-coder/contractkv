"""Explicit token-level LCP supplement to the frozen historical timeline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    fsha = hashlib.sha256((a.root/'freeze.json').read_bytes()).hexdigest()
    result = []
    for cell in sorted((a.root/'cells').glob('*risk-tail*')):
        rows = [json.loads(x) for x in (cell/'raw.jsonl').open(encoding='utf-8')]
        requests = {x['request_id']: x['payload'] for x in rows if x['row_type'] == 'verification_request'}
        certs = {(x['certificate_namespace'], x['query_scope']): x for x in rows
                 if x['row_type'] == 'verification' and x['certificate_issued']}
        for row in rows:
            if row['row_type'] not in ('warm', 'future') or row['effective_level'] == 'L0':
                continue
            cert = certs[row['certificate_namespace'], row['query_scope']]
            payload = requests[cert['request_id']]
            ids, candidate = row['prompt_token_ids'], payload['prompt_token_ids']
            lcp = next((i for i, (x, y) in enumerate(zip(ids, candidate)) if x != y),
                       min(len(ids), len(candidate)))
            stable, committed = cert['stable_prefix_tokens'], cert['committed_tokens']
            assert lcp >= stable >= committed > 0
            assert ids[:16] == candidate[:16]
            salt = fsha+':'+row['certificate_namespace']
            assert payload['cache_salt'] == salt
            result.append({'cell':cell.name, 'model':row['model'], 'repeat':row['repeat'],
                'source_group':row['source_group'], 'request_id':row['request_id'],
                'turn_id':row['turn_id'], 'tenant_id':row['tenant_id'],
                'actual_LCP_with_certification_payload_tokens':lcp,
                'stable_prefix_tokens':stable,'committed_tokens':committed,
                'LCP_margin_over_committed_tokens':lcp-committed,
                'actual_first16_token_IDs_JSON':json.dumps(ids[:16]),
                'certification_payload_first16_IDs_equal':True,
                'certification_wire_salt':payload['cache_salt'],
                'business_salt_reconstructed_not_wire_logged':salt,
                'prefix_hit_tokens':row['prefix_hit_tokens'],
                'physical_hit_below_commit':row['prefix_hit_tokens']<committed})
    assert len(result) == 1440 and sum(x['physical_hit_below_commit'] for x in result) == 189
    a.output.mkdir(parents=True)
    with (a.output/'compiled_prompt_LCP_v1.csv').open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    summary={'compiled_business_requests':len(result),'physical_hit_below_commit':189,
             'LCP_below_stable_or_commit':0,'first16_ID_mismatches':0,
             'minimum_LCP_margin_over_commit':min(x['LCP_margin_over_committed_tokens'] for x in result),
             'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'primary_freeze_sha256':fsha,'new_GPU_requests':0,
             'business_backend_salt_directly_observed_in_historical_logs':False}
    (a.output/'LCP_summary_v1.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())
    print(json.dumps(summary))


if __name__=='__main__':
    main()
