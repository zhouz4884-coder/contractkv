"""Build document facts from completed, audited R4 tables without new inference.

This post-freeze reporting supplement keeps all metrics, policies and primary
estimands unchanged. Absolute task scores are separated by benchmark family.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def summarize(group):
    compiled = [r for r in group if r['effective_level'] != 'L0']
    fallback = [r for r in group if r['effective_level'] == 'L0']
    mean = lambda values: statistics.fmean(values) if values else None
    return {
        'paired_business_requests': len(group), 'compiled_business_requests': len(compiled),
        'compiled_coverage_fraction': len(compiled) / len(group),
        'raw_mean_task_score': mean([float(r['raw_score']) for r in group]),
        'policy_mean_task_score': mean([float(r['policy_score']) for r in group]),
        'raw_positive_score_requests': sum(float(r['raw_score']) > 0 for r in group),
        'raw_zero_score_requests': sum(float(r['raw_score']) == 0 for r in group),
        'compiled_subset_raw_mean_score': mean([float(r['raw_score']) for r in compiled]),
        'compiled_subset_policy_mean_score': mean([float(r['policy_score']) for r in compiled]),
        'compiled_subset_raw_positive_score_requests': sum(float(r['raw_score']) > 0 for r in compiled),
        'compiled_any_score_decrease': sum(float(r['quality_drop']) > 0 for r in compiled),
        'compiled_material_drop_gt0_03': sum(float(r['quality_drop']) > .03 for r in compiled),
        'compiled_output_ID_divergences': sum(int(r['first_output_ID_divergence']) != -1 for r in compiled),
        'compiled_witness_ID_divergences': sum(int(r['first_ID_divergence_from_witness']) != -1 for r in compiled),
        'fallback_material_drop_gt0_03': sum(float(r['quality_drop']) > .03 for r in fallback),
        'all_route_material_drop_gt0_03': sum(float(r['quality_drop']) > .03 for r in group),
        'all_route_any_score_decrease': sum(float(r['quality_drop']) > 0 for r in group),
        'raw_output_tokens_sum': sum(int(r['raw_output_tokens']) for r in group),
        'policy_output_tokens_sum': sum(int(r['policy_output_tokens']) for r in group),
        'fresh_repeats': len({r['repeat'] for r in group}),
        'source_groups': len({r['source_group'] for r in group}),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True, action='append')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve report fact version')
    result = {'schema_version': 'tsc-r4.experimental-report-facts.v1',
              'postfreeze_reporting_only': True, 'new_GPU_requests': 0,
              'source_sha256': sha(Path(__file__)), 'studies': []}
    metrics = {'RULER': 'substring matching (string_match_part)',
               'HotpotQA': 'frozen QA F1', 'NarrativeQA': 'frozen QA F1',
               'Qasper': 'frozen QA F1',
               'RepoBench': 'frozen edit similarity (legacy SequenceMatcher)'}
    for root in a.root:
        audit = root / 'analysis/completion_audit_v1.json'
        if not json.loads(audit.read_text())['execution_complete']:
            raise ValueError('Completed primary audit required')
        quality = root / 'all_business_quality_v1.csv'
        population = rows(quality)
        primary = rows(root / 'analysis/quality_summary_v1.csv')
        for r in primary:
            if r['family'] != 'ALL':
                continue
            group = [x for x in population if x['row_type'] == 'future'
                     and (x['study'], x['model'], x['policy']) == (r['study'], r['model'], r['policy'])]
            measured = summarize(group)
            for field, expected in [('paired_business_requests', 'pairs'),
                                    ('compiled_business_requests', 'compiled_pairs'),
                                    ('compiled_material_drop_gt0_03', 'compiled_material_drops'),
                                    ('all_route_material_drop_gt0_03', 'all_material_drops')]:
                if measured[field] != int(r[expected]):
                    raise ValueError('Primary future quality crosscheck failed: ' + field)
        family_groups = defaultdict(list)
        source_groups = defaultdict(list)
        global_groups = defaultdict(list)
        for row in population:
            for pop in ('all_business', row['row_type']):
                family_groups[row['study'], row['model'], row['policy'], row['family'], pop].append(row)
                global_groups[row['study'], row['model'], row['policy'], pop].append(row)
            source_groups[row['study'], row['model'], row['policy'], row['family'], row['source_group']].append(row)
        family_records = [dict(zip(('study', 'model', 'policy', 'family', 'population'), key),
                               task_metric=metrics[key[3]], **summarize(group))
                          for key, group in sorted(family_groups.items())]
        source_records = [dict(zip(('study', 'model', 'policy', 'family', 'source_group'), key),
                               task_metric=metrics[key[3]], **summarize(group),
                               compiled_requests_by_repeat=dict(Counter(r['repeat'] for r in group if r['effective_level'] != 'L0')))
                          for key, group in sorted(source_groups.items())]
        globals_ = [dict(zip(('study', 'model', 'policy', 'population'), key),
                         **{k: v for k, v in summarize(group).items() if 'mean' not in k})
                    for key, group in sorted(global_groups.items())]
        compiled_differences = [r for r in population if r['effective_level'] != 'L0'
                                and (float(r['quality_drop']) > 0 or int(r['first_output_ID_divergence']) != -1)]
        sources = [audit, quality, root / 'all_business_quality_v1.json',
                   root / 'analysis/quality_summary_v1.csv',
                   root / 'analysis/performance_comparison_v1.csv',
                   root / 'analysis/performance_by_cell_v1.csv',
                   root / 'analysis/raw_repeat_controls_v1.csv',
                   root / 'routing_attribution_v1.json', root / 'scope_object_audit_v1.json',
                   root / 'family_tail_audit_v1.json', root / 'fallback_metric_analysis_v1.json',
                   root / 'evidence_availability_v1.json', root / 'fallback_repeat_audit_v1.json']
        provenance = [{'path': f.as_posix(), 'sha256': sha(f)} for f in sources]
        result['studies'].append({
            'root': root.as_posix(), 'provenance': provenance,
            'family_absolute_and_relative_quality': family_records,
            'source_absolute_and_relative_quality': source_records,
            'global_counts_no_pooled_mixed_metric_mean': globals_,
            'all_compiled_decreases_or_ID_differences': compiled_differences,
            'primary_performance_comparison_unmodified': rows(root / 'analysis/performance_comparison_v1.csv'),
            'per_cell_performance_unmodified': rows(root / 'analysis/performance_by_cell_v1.csv'),
            'literal_availability_source_records': json.loads((root / 'evidence_availability_v1.json').read_text(encoding='utf-8'))['source_input_records'],
            'L0_repeat_source_records': json.loads((root / 'fallback_repeat_audit_v1.json').read_text(encoding='utf-8'))['source_records'],
        })
    result['interpretation'] = [
        'Absolute scores use separate frozen metrics by family. They are not pooled into a cross-task accuracy.',
        'Raw positive F1 or edit similarity does not establish full task correctness; relative preservation is a separate outcome.',
        'Compiled coverage and failures retain every source and request, including turn-zero business reuse; future primary denominators are crosschecked separately.',
        'Source/repeat/request observations are correlated. Zero observed compiled differences does not establish universal dynamic-input safety.',
        'This file extracts measured facts; the experiment stop decision additionally requires protocol, scope, publication and evidence-integrity review.',
    ]
    structure_path = Path('results/tsc_revision_r4/frozen_input_structure_audit_v1.json')
    result['shared_input_structure_audit'] = {
        'path': structure_path.as_posix(), 'sha256': sha(structure_path),
        'audit': json.loads(structure_path.read_text(encoding='utf-8')),
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'complete_protocols': len(result['studies']),
                      'source_records': sum(len(s['source_absolute_and_relative_quality']) for s in result['studies']),
                      'compiled_difference_rows': sum(len(s['all_compiled_decreases_or_ID_differences']) for s in result['studies'])}))


if __name__ == '__main__':
    main()
