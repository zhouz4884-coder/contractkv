"""Known-source fixed-ID diagnostic replay, never a quality/performance test."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase17_live_common import digest, post_json


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(output):
    assert not output.exists()
    root = Path('results/tsc_revision_r4/input_fidelity_validation_v1')
    targets = [('llama', 'LongBench:hotpotqa:hotpotqa:doc:69', 'llama-3.1-8b'),
               ('mistral', 'LongBench:hotpotqa:hotpotqa:doc:19', 'mistral-7b'),
               ('qwen', 'RepoBench:python_v1.1:Gene-Weaver/VoucherVision', 'qwen3-8b')]
    plan = {'schema_version': 'tsc-residency.known-source-diagnostic.v1',
            'base_freeze_sha256': sha(root/'freeze.json'),
            'maximum_business_requests': 138, 'maximum_verification_requests': 9,
            'conditions': ['two immediate serial reuses after first successful commit',
                           'one concurrent warm pair after those serial reuses',
                           'original first two cohorts, each complete ten turns, including intervening raw waves',
                           'two immediate serial reuses after replay'],
            'changes': 'Read-only backend hooks and diagnostic fixed-ID completion transport. Original archived witness and candidate routes are replayed; online gate is not rerun.',
            'nonclaims': ['Not a fresh independent quality validation',
                          'Not original service scheduling/performance reproduction',
                          'No timing or throughput claim from trace runs',
                          'No capacity, safety, layout or certificate rule change'],
            'cells': []}
    for alias, source, served in targets:
        directory = root/'cells'/f'template-fanout_{alias}_risk-tail_r1'
        rows = [json.loads(x) for x in (directory/'raw.jsonl').open(encoding='utf-8')]
        businesses = [x for x in rows if x['row_type'] in ('warm', 'future') and x['source_group'] == source
                      and int(x['tenant_id'].rsplit('tenant', 1)[1]) < 4]
        assert len(businesses) == 40
        namespace = businesses[0]['certificate_namespace']
        certs = {x['query_scope']: x for x in rows if x['row_type'] == 'verification'
                 and x['certificate_namespace'] == namespace}
        verify = {x['request_id']: x['payload'] for x in rows if x['row_type'] == 'verification_request'}
        waves = []
        for cohort in range(2):
            for turn in range(10):
                pair = [x for x in businesses if int(x['tenant_id'].rsplit('tenant', 1)[1])//2 == cohort
                        and x['turn_id'] == turn]
                assert len(pair) == 2
                group = []
                for x in pair:
                    group.append({k: x[k] for k in ('request_id', 'prompt_token_ids', 'output_token_ids', 'output_budget',
                                                  'witness_requested', 'effective_level', 'query_scope', 'tenant_id', 'turn_id')})
                certificate = next((x for x in certs.values() if cohort == 0 and x['turn_id'] == turn
                                    and x.get('request_id') in verify), None)
                waves.append({'cohort': cohort, 'turn': turn, 'businesses': group,
                              'verification': verify[certificate['request_id']] if certificate else None,
                              'verification_scope': certificate['query_scope'] if certificate else None,
                              'archived_certificate_issued': certificate['certificate_issued'] if certificate else None})
        accepted = {k: x['committed_tokens'] for k, x in certs.items() if x['certificate_issued']}
        assert accepted and sum(x['verification'] is not None for x in waves) <= 3
        plan['cells'].append({'alias': alias, 'source_group': source, 'served_model': served,
            'model_identity': businesses[0]['model'], 'namespace': namespace,
            'source_raw_sha256': sha(directory/'raw.jsonl'),
            'accepted_scope_commit_tokens': accepted, 'waves': waves})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2)+'\n').encode())
    print(json.dumps({'cells': len(plan['cells']), 'maximum_business': 138,
                      'verification_replays': sum(w['verification'] is not None for c in plan['cells'] for w in c['waves'])}))


def run(args):
    assert not args.output.exists(), 'Preserve every attempted replay'
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    cell = next(x for x in plan['cells'] if x['alias'] == args.alias)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    issued, results = set(), []

    def record(row):
        with args.output.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False)+'\n')

    def generate(spec, label):
        rid = 'resdiag-'+label+'-'+spec['request_id']
        compiled = spec['effective_level'] != 'L0'
        if compiled and spec['query_scope'] not in issued:
            return {'event': 'skipped_no_current_certificate', 'label': label, 'request_id': rid,
                    'scope': spec['query_scope']}
        payload = {'model': cell['served_model'], 'prompt': spec['prompt_token_ids'],
                   'add_special_tokens': False, 'max_tokens': spec['output_budget'],
                   'temperature': 0, 'top_p': 1, 'seed': 14014, 'return_token_ids': True,
                   'request_id': rid, 'stream': False}
        if compiled:
            payload['cache_salt'] = plan['base_freeze_sha256']+':'+cell['namespace']
        if spec['witness_requested']:
            payload['logprobs'] = 2
        started = time.perf_counter()
        body = post_json(args.url+'/v1/completions', payload, 600)
        ended = time.perf_counter()
        choice = body['choices'][0]
        assert choice['prompt_token_ids'] == spec['prompt_token_ids'], 'Actual prompt IDs changed'
        assert choice['token_ids'] and body['usage']['prompt_tokens'] == len(spec['prompt_token_ids'])
        return {'event': 'business', 'label': label, 'submitted_request_id': rid,
                'actual_request_id': body['id'], 'source_request_id': spec['request_id'],
                'scope': spec['query_scope'], 'level': spec['effective_level'],
                'prompt_ids_sha256': digest(spec['prompt_token_ids']),
                'wire_cache_salt': payload.get('cache_salt'),
                'start_perf_s': started, 'end_perf_s': ended, 'response': body,
                'archived_output_ids_equal': choice['token_ids'] == spec['output_token_ids']}

    extra_done = False
    last_compiled = None
    for wave in cell['waves']:
        label = f"c{wave['cohort']}-t{wave['turn']}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            pair = list(pool.map(lambda x: generate(x, label), wave['businesses']))
        for row in pair:
            record(row); results.append(row)
        for x in wave['businesses']:
            if x['effective_level'] != 'L0' and x['query_scope'] in issued:
                last_compiled = x
        if wave['verification']:
            payload = deepcopy(wave['verification'])
            payload['request_id'] = 'resdiag-'+payload['request_id']
            payload['txn_id'] = 'resdiag-'+payload['txn_id']
            record({'event': 'verification_request', 'label': label, 'payload': payload})
            response = post_json(args.url+'/v1/contractkv/verify', payload, 600)
            record({'event': 'verification_response', 'label': label, 'response': response,
                    'archived_certificate_issued': wave['archived_certificate_issued']})
            if response['certificate_issued']:
                scope = wave['verification_scope']
                if scope in cell['accepted_scope_commit_tokens']:
                    assert response['committed_tokens'] == cell['accepted_scope_commit_tokens'][scope]
                issued.add(scope)
                if not extra_done and scope in cell['accepted_scope_commit_tokens']:
                    target = next(x for w in cell['waves'] for x in w['businesses']
                                  if x['effective_level'] != 'L0' and x['query_scope'] == scope)
                    for i in range(2):
                        row = generate(target, f'immediate-serial-{i}'); record(row); results.append(row)
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        pair = list(pool.map(lambda i: generate(target, f'immediate-pair-{i}'), range(2)))
                    for row in pair:
                        record(row); results.append(row)
                    extra_done = True
        print(json.dumps({'alias': args.alias, 'wave': label, 'issued_scopes': len(issued)}), flush=True)
    if last_compiled:
        for i in range(2):
            row = generate(last_compiled, f'final-serial-{i}'); record(row); results.append(row)
    record({'event': 'diagnostic_completed', 'businesses': len(results),
            'issued_scopes': sorted(issued), 'completed_requests': sum(r['event'] == 'business' for r in results),
            'no_performance_claim': True})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--alias')
    p.add_argument('--url')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.build:
        build(args.build)
    else:
        run(args)


if __name__ == '__main__':
    main()
