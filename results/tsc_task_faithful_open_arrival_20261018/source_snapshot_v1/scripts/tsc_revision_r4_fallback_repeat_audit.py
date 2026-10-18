"""Relate observed L0 failures/length inflation to prespecified raw repeats.

This is source- and request-matched descriptive evidence, not causal execution
attribution or a new GPU control. Raw and policy variants stay fully retained.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import first_divergence
from scripts.tsc_revision_r4_live_summary import MODELS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(tokens):
    return hashlib.sha256(json.dumps(tokens, separators=(',', ':')).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve repeat diagnostic version')
    audit = a.root / 'analysis/completion_audit_v1.json'
    if not json.loads(audit.read_text())['execution_complete']:
        raise ValueError('All prespecified control repeats must be complete')
    pairs_path = a.root / 'all_business_quality_v1.csv'
    with pairs_path.open(encoding='utf-8', newline='') as stream:
        pairs = list(csv.DictReader(stream))
    selected = defaultdict(list)
    for row in pairs:
        if row['policy'] != 'risk-tail' or row['effective_level'] != 'L0':
            continue
        loss = float(row['quality_drop']) > .03
        raw_tokens = int(row['raw_output_tokens'])
        policy_tokens = int(row['policy_output_tokens'])
        inflation = policy_tokens >= 4 * max(raw_tokens, 1) and policy_tokens - raw_tokens >= 128
        if loss or inflation:
            key = row['study'], row['model'], row['source_group'], row['session_id'], int(row['turn_id'])
            selected[key].append({'repeat': int(row['repeat']), 'quality_drop': float(row['quality_drop']),
                                  'material_drop_gt0_03': loss, 'large_length_inflation': inflation})
    measured = defaultdict(list)
    provenance = []
    for path in sorted((a.root / 'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text(encoding='utf-8'))
        if summary['policy'] not in ('raw-order', 'risk-tail'):
            continue
        raw_path = path.with_name('raw.jsonl')
        if not summary['execution_complete'] or sha(raw_path) != summary['raw_file_sha256']:
            raise ValueError('Incomplete or changed cell')
        with raw_path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row['row_type'] not in ('warm', 'future'):
                    continue
                key = row['study'], row['model'], row['source_group'], row['session_id'], row['turn_id']
                if key not in selected:
                    continue
                measured[key].append({
                    'policy': row['policy'], 'repeat': row['repeat'],
                    'cell': path.parent.name, 'row_type': row['row_type'],
                    'effective_level': row['effective_level'], 'family': row['family'],
                    'task_score': row['task_score'], 'task_metric': row['task_metric'],
                    'output_text': row['output_text'], 'output_token_ids': row['output_token_ids'],
                    'prompt_token_ids': row['prompt_token_ids'],
                    'prompt_ids_sha256': row['prompt_ids_sha256'],
                    'output_signature_sha256': signature(row['output_token_ids']),
                    'output_tokens': len(row['output_token_ids']), 'output_budget': row['output_budget'],
                    'finish_reason': row['finish_reason'], 'prefix_hit_tokens': row['prefix_hit_tokens'],
                    'latency_ms': row['latency_ms'], 'ttft_ms': row['ttft_ms'],
                    'ready_ttft_ms': row['ready_ttft_ms'],
                })
        provenance.append({'cell': path.parent.name, 'summary_sha256': sha(path), 'raw_sha256': sha(raw_path)})
    cases = []
    for key, events in sorted(selected.items()):
        group = measured[key]
        raw = sorted([r for r in group if r['policy'] == 'raw-order'], key=lambda r: r['repeat'])
        fallback = sorted([r for r in group if r['policy'] == 'risk-tail' and r['effective_level'] == 'L0'], key=lambda r: r['repeat'])
        expected_repeats = {int(r['repeat']) for r in pairs if r['study'] == key[0] and r['model'] == key[1]}
        if {r['repeat'] for r in raw} != expected_repeats:
            raise ValueError('Missing raw repeat for selected case')
        reference_prompt = raw[0]['prompt_token_ids']
        if any(r['prompt_token_ids'] != reference_prompt for r in raw + fallback):
            raise ValueError('Actual matched raw/L0 prompts differ')
        raw_by_repeat = {r['repeat']: r for r in raw}
        raw_signatures = {r['output_signature_sha256'] for r in raw}
        fallback_signatures = {r['output_signature_sha256'] for r in fallback}
        overlap = fallback_signatures <= raw_signatures
        if len(fallback) < 2:
            label = 'fewer_than_two_policy_L0_controls_no_L0_stability_classification'
        elif len(raw_signatures) > 1:
            label = 'raw_varies_and_all_L0_variants_also_observed_in_raw' if overlap else 'raw_varies_but_not_all_L0_variants_seen_in_raw_controls'
        elif len(fallback_signatures) == 1 and not overlap:
            label = 'raw_stable_and_policy_L0_stably_different_in_observed_controls'
        elif len(fallback_signatures) > 1:
            label = 'raw_stable_and_policy_L0_varies_in_observed_controls'
        else:
            label = 'same_observed_raw_and_L0_output_signature'
        paired = []
        for row in fallback:
            ref = raw_by_repeat[row['repeat']]
            paired.append({'repeat': row['repeat'],
                           'first_output_ID_divergence': first_divergence(ref['output_token_ids'], row['output_token_ids']),
                           'quality_drop': ref['task_score'] - row['task_score'],
                           'output_token_increase': row['output_tokens'] - ref['output_tokens'],
                           'raw_finish': ref['finish_reason'], 'L0_finish': row['finish_reason'],
                           'raw_and_L0_same_prefix_hit_count': ref['prefix_hit_tokens'] == row['prefix_hit_tokens']})
        for row in group:
            row.pop('prompt_token_ids')
        cases.append(dict(zip(('study', 'model', 'source_group', 'session_id', 'turn_id'), key),
                          family=raw[0]['family'], trigger_events=events,
                          actual_raw_and_L0_prompt_IDs_equal=True, classification=label,
                          raw_controls=len(raw), policy_L0_controls=len(fallback),
                          raw_unique_output_signatures=len(raw_signatures),
                          L0_unique_output_signatures=len(fallback_signatures),
                          all_L0_output_signatures_observed_among_raw_controls=overlap,
                          raw_length_stop_count=sum(r['finish_reason'] == 'length' for r in raw),
                          L0_length_stop_count=sum(r['finish_reason'] == 'length' for r in fallback),
                          paired_repeat_changes=paired, original_business_outputs=group))
    source_groups = defaultdict(list)
    for case in cases:
        source_groups[case['study'], case['model'], case['source_group'], case['family']].append(case)
    source_records = []
    for key, group in sorted(source_groups.items()):
        source_records.append(dict(zip(('study', 'model', 'source_group', 'family'), key),
                                   distinct_session_turn_cases=len(group),
                                   paired_trigger_events=sum(len(r['trigger_events']) for r in group),
                                   material_drop_events=sum(e['material_drop_gt0_03'] for r in group for e in r['trigger_events']),
                                   length_inflation_events=sum(e['large_length_inflation'] for r in group for e in r['trigger_events']),
                                   classifications=dict(Counter(r['classification'] for r in group))))
    result = {
        'schema_version': 'tsc-r4.L0-prespecified-repeat-audit.v1',
        'source_sha256': sha(Path(__file__)), 'business_pairs_sha256': sha(pairs_path),
        'new_GPU_requests': 0, 'case_count': len(cases), 'cases': cases,
        'source_records': source_records, 'cell_provenance': provenance,
        'selection': 'All risk-tail L0 business pairs with frozen score drop >.03 or >=4x output length and >=128 additional tokens; all prespecified raw repeats retained for each selected request.',
        'interpretation_limits': [
            'Cases are selected after observing failures/length inflation. These conditional frequencies do not estimate an unconditional population failure rate.',
            'Three raw controls cannot rule out a rare native variant. A policy L0 variant also seen in raw controls does not prove policy causally unrelated.',
            'Stable raw versus stable different L0 in these controls flags a policy-associated execution difference; it is not proof of a particular batch, kernel, precision, cache or scheduling cause.',
            'Identical prompt IDs and prefix hit counts do not establish identical numerical execution. Runtime/device identities remain in the linked cell manifests.',
            'All length-limited outputs, quality failures and measured costs remain in the primary estimands. No scorer repair, generation rewriting or GPU probe is performed.',
            'Source summaries retain correlated tenant/turn events rather than treating them as independent failure sources.',
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'affected_source_model_study_units': len(source_records),
                      'classifications': dict(Counter(r['classification'] for r in cases)), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
