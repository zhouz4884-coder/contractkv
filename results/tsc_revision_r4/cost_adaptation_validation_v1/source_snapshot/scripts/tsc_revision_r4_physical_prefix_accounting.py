"""Account for observed physical prefixes and actual native APC counters.

These are controlled benchmark traces. No production prevalence, original
Table I provenance, GPU-time decomposition or certification guarantee follows.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.contractkv_pstp import lcp_length
from scripts.tsc_revision_live import load_metrics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve physical-accounting versions')
    config = json.loads((args.root / 'freeze.json').read_text(encoding='utf-8'))['protocol']
    records = []
    templates = []
    for path in sorted((args.root / 'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text(encoding='utf-8'))
        raw = path.with_name('raw.jsonl')
        if not summary['execution_complete'] or sha(raw) != summary['raw_file_sha256']:
            raise ValueError('Completed, unchanged cells required')
        rows = [json.loads(line) for line in raw.open(encoding='utf-8')]
        metrics = load_metrics(path.with_name('metrics.jsonl'))
        business = [row for row in rows if row['row_type'] in ('warm', 'future')]
        verification = [row for row in rows if row['row_type'] == 'verification_request']
        groups = defaultdict(list)
        for row in business:
            event = metrics[row['request_id']]
            if (event['prompt_tokens'] != len(row['prompt_token_ids']) or
                    row['prefix_hit_tokens'] != event['prefix_hit_tokens']):
                raise ValueError('Actual prompt/metric identity mismatch')
            groups[row['certificate_namespace']].append(row)
        for namespace, group in groups.items():
            common = group[0]['prompt_token_ids']
            for row in group[1:]:
                common = common[:lcp_length(common, row['prompt_token_ids'])]
            compiled = [row for row in group if row['effective_level'] != 'L0']
            all_tokens = sum(len(row['prompt_token_ids']) for row in group)
            hits = sum(row['prefix_hit_tokens'] for row in group)
            templates.append({'cell': path.parent.name, 'namespace': namespace,
                              'source_group': group[0]['source_group'], 'family': group[0]['family'],
                              'model': group[0]['model'], 'policy': summary['policy'], 'repeat': summary['repeat'],
                              'business_requests': len(group), 'compiled_business_requests': len(compiled),
                              'observed_all_business_prompt_ID_LCP_tokens': len(common),
                              'mean_actual_prompt_tokens': statistics.fmean(len(row['prompt_token_ids']) for row in group),
                              'actual_business_prompt_tokens': all_tokens, 'actual_native_prefix_hit_tokens': hits,
                              'actual_new_business_prefill_tokens': all_tokens-hits,
                              'token_weighted_native_hit_fraction': hits/all_tokens,
                              'LCP_boundary': 'Common prefix of all observed business prompts in this cell/template, across routes and tenants; not stable-content fraction or a cache entitlement.'})
        verification_events = [metrics[row['request_id']] for row in verification]
        requests = [row['request_id'] for row in business + verification]
        if len(set(requests)) != len(requests):
            raise ValueError('Duplicate measured request IDs')
        compiled = [row for row in business if row['effective_level'] != 'L0']
        records.append({'cell': path.parent.name, 'study': summary['study'], 'model': business[0]['model'],
                        'policy': summary['policy'], 'repeat': summary['repeat'],
                        'business_requests': len(business), 'compiled_business_requests': len(compiled),
                        'actual_business_prompt_tokens': sum(len(row['prompt_token_ids']) for row in business),
                        'actual_business_native_hit_tokens': sum(row['prefix_hit_tokens'] for row in business),
                        'actual_new_business_prefill_tokens': sum(row['new_prefill_tokens'] for row in business),
                        'actual_compiled_prompt_tokens': sum(len(row['prompt_token_ids']) for row in compiled),
                        'actual_compiled_native_hit_tokens': sum(row['prefix_hit_tokens'] for row in compiled),
                        'actual_qualification_requests': len(verification),
                        'actual_qualification_prompt_including_witness_tokens': sum(event['prompt_tokens'] for event in verification_events),
                        'actual_qualification_native_hit_tokens': sum(event['prefix_hit_tokens'] for event in verification_events),
                        'actual_qualification_new_prefill_including_witness_tokens': sum(event['prompt_tokens']-event['prefix_hit_tokens'] for event in verification_events),
                        'raw_sha256': sha(raw)})
    if len(records) != config['expected_cells']:
        raise ValueError('Require complete declared matrix')
    result = {'schema_version': 'tsc-r4.actual-physical-prefix-accounting.v1',
              'analysis_source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(args.root/'freeze.json'),
              'cells': records, 'templates': templates, 'execution_complete': True,
              'pre_measurement_control_requests_excluded': True,
              'is_original_Table_I_reproduction': False, 'is_production_prevalence': False,
              'boundary': 'All measured business and qualification requests, including initial raw and failed qualifications. Token counts are not GPU-time or wall-time attribution. Raw/policy decode lengths and route coverage must be reported alongside these counts.'}
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'complete_cells': len(records), 'template_records': len(templates), 'execution_complete': True}))


if __name__ == '__main__':
    main()
