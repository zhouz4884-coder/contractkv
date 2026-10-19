"""Audit all served answers, including tenant turn-zero compiled reuse.

Frozen primary quality estimands use future turns. In shared-template replay,
later tenants can already reuse a certificate on turn zero. This supplement
counts those real business answers separately without changing primary tables.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_revision_r4_live_summary import MODELS
from scripts.tsc_revision_summarize import read, write, first_divergence


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    output_json = Path(str(args.output_prefix) + '.json')
    output_csv = Path(str(args.output_prefix) + '.csv')
    if output_json.exists() or output_csv.exists():
        raise ValueError('Preserve all-business supplement version')
    primary = args.root / 'analysis'
    if not json.loads((primary / 'completion_audit_v1.json').read_text())['execution_complete']:
        raise ValueError('Complete primary audit is required')
    protocol = json.loads((args.root / 'freeze.json').read_text())['protocol']
    samples = {study: {r['revision_source_group']: r for r in read(args.root / 'source_snapshot' / path)}
               for study, path in protocol['input_files'].items()}
    pairs = []
    provenance = []
    for study in protocol['studies']:
        for alias in protocol['models']:
            for repeat in range(1, protocol['repeats'] + 1):
                base = args.root / 'cells' / f'{study}_{alias}_raw-order_r{repeat}'
                raw_path = base / 'raw.jsonl'
                raw_rows = {(r['session_id'], r['turn_id']): r for r in read(raw_path)
                            if r['row_type'] in ('warm', 'future')}
                for policy in [p for p in protocol['policies'] if p != 'raw-order']:
                    path = args.root / 'cells' / f'{study}_{alias}_{policy}_r{repeat}' / 'raw.jsonl'
                    rows = read(path)
                    witnesses = {}
                    for row in rows:
                        if row['row_type'] in ('warm', 'future') and row['scope_first_raw_business']:
                            witnesses.setdefault((row['certificate_namespace'], row['query_scope']), row)
                    observed = set()
                    for row in rows:
                        if row['row_type'] not in ('warm', 'future'):
                            continue
                        key = row['session_id'], row['turn_id']
                        if key in observed:
                            raise ValueError('Duplicate business output')
                        observed.add(key)
                        raw = raw_rows[key]
                        sample = samples[study][row['source_group']]
                        for output in (raw, row):
                            score, _, _ = standard_score(sample['dataset'], sample['task'], output['output_text'], sample.get('answer', ''))
                            if abs(score - output['task_score']) > 1e-12:
                                raise ValueError('Frozen task metric mismatch')
                        compiled = row['effective_level'] != 'L0'
                        if not compiled and raw['prompt_token_ids'] != row['prompt_token_ids']:
                            raise ValueError('L0 actual prompt IDs differ, including turn zero')
                        witness = witnesses[(row['certificate_namespace'], row['query_scope'])] if compiled else None
                        pairs.append({'study': study, 'model': MODELS[alias], 'policy': policy, 'repeat': repeat,
                                      'row_type': row['row_type'], 'source_group': row['source_group'],
                                      'session_id': key[0], 'turn_id': key[1], 'family': row['family'],
                                      'effective_level': row['effective_level'], 'raw_score': raw['task_score'],
                                      'policy_score': row['task_score'], 'quality_drop': raw['task_score'] - row['task_score'],
                                      'first_output_ID_divergence': first_divergence(raw['output_token_ids'], row['output_token_ids']),
                                      'first_ID_divergence_from_witness': first_divergence(witness['output_token_ids'], row['output_token_ids']) if witness else None,
                                      'positions_beyond_witness_length': max(0, len(row['output_token_ids']) - len(witness['output_token_ids'])) if witness else None,
                                      'raw_output_tokens': len(raw['output_token_ids']), 'policy_output_tokens': len(row['output_token_ids']),
                                      'raw_finish_reason': raw['finish_reason'], 'policy_finish_reason': row['finish_reason']})
                    if observed != set(raw_rows):
                        raise ValueError('Incomplete all-business pair set')
                    provenance.append({'cell': path.parent.name, 'raw_sha256': sha(raw_path), 'policy_sha256': sha(path)})
    groups = defaultdict(list)
    for row in pairs:
        for population in ('all_business', row['row_type']):
            groups[row['study'], row['model'], row['policy'], population].append(row)
    summary = []
    for (study, model, policy, population), rows in sorted(groups.items()):
        compiled = [r for r in rows if r['effective_level'] != 'L0']
        summary.append({'study': study, 'model': model, 'policy': policy, 'population': population,
                        'paired_business_answers': len(rows), 'compiled_answers': len(compiled),
                        'compiled_material_drops': sum(r['quality_drop'] > .03 for r in compiled),
                        'compiled_any_score_decreases': sum(r['quality_drop'] > 0 for r in compiled),
                        'compiled_output_ID_divergences': sum(r['first_output_ID_divergence'] != -1 for r in compiled),
                        'compiled_ID_divergences_from_witness': sum(r['first_ID_divergence_from_witness'] != -1 for r in compiled),
                        'fallback_material_drops': sum(r['quality_drop'] > .03 and r['effective_level'] == 'L0' for r in rows),
                        'all_route_material_drops': sum(r['quality_drop'] > .03 for r in rows)})
    with (primary / 'quality_summary_v1.csv').open(encoding='utf-8', newline='') as stream:
        original = {(r['study'], r['model'], r['policy']): r for r in csv.DictReader(stream) if r['family'] == 'ALL'}
    for row in summary:
        if row['population'] != 'future':
            continue
        reference = original[row['study'], row['model'], row['policy']]
        for field, old in [('paired_business_answers', 'pairs'), ('compiled_answers', 'compiled_pairs'),
                           ('compiled_material_drops', 'compiled_material_drops'),
                           ('compiled_any_score_decreases', 'compiled_any_score_decrease'),
                           ('compiled_output_ID_divergences', 'compiled_ID_divergences'),
                           ('all_route_material_drops', 'all_material_drops')]:
            if row[field] != int(reference[old]):
                raise ValueError('Primary future-quality count changed')
    output_json.parent.mkdir(parents=True, exist_ok=True)
    write(output_csv, pairs)
    result = {'schema_version': 'tsc-r4.all-business-quality.v1',
              'added_after_primary_freeze': True, 'new_GPU_requests': 0,
              'primary_future_estimand_and_counts_unchanged': True,
              'turn_zero_are_actual_business_answers_not_server_warmup': True,
              'source_sha256': sha(Path(__file__)), 'paired_csv_sha256': sha(output_csv),
              'provenance': provenance, 'summary': summary,
              'boundary': 'All-business adds turn-zero answers, including already certified reuse by later tenants. Repeats, tenants and protocols remain correlated; no universal zero-risk claim.'}
    output_json.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'paired_business_answers': len(pairs), 'new_GPU_requests': 0,
                      'new_policy_all_business': [r for r in summary if r['policy'] == 'risk-tail' and r['population'] == 'all_business']}))


if __name__ == '__main__':
    main()
