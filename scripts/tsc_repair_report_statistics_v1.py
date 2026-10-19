"""Post-hoc descriptive report tables from the validated repair raw evidence.

This makes no new admission decision and issues no model requests. Repeated
principals/processes remain correlated observations of six real sources.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics

STUDY = Path('results/tsc_authorization_task_repair_20261019')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def yes(value):
    return value == 'True'


def tally_pairs(data):
    valid = [row for row in data if yes(row['available'])]
    return dict(total=len(data), available=len(valid),
                output_ID_changes=sum(not yes(row['output_IDs_equal']) for row in valid),
                finish_changes=sum(not yes(row['finish_equal']) for row in valid),
                score_up_gt_003=sum(yes(row['score_up']) for row in valid),
                score_down_gt_003=sum(yes(row['score_down']) for row in valid),
                first_mean_score=statistics.fmean(float(row['first_score']) for row in valid) if valid else None,
                second_mean_score=statistics.fmean(float(row['second_score']) for row in valid) if valid else None)


def main(root, output):
    assert not output.exists()
    study = root / STUDY
    summary = read(study / 'analysis_v1/summary_v1.json')
    assert summary['business_requests'] == 828
    requests = rows(study / 'analysis_v1/requests_v1.csv')
    pairs = rows(study / 'analysis_v1/paired_quality_v1.csv')
    qualifications = rows(study / 'analysis_v1/qualifications_v1.csv')
    namespace = rows(study / 'analysis_v1/namespace_checks_v1.csv')
    markers = read(study / 'marker_token_positions_v1.json')['rows']
    names = {'qwen3-8b': 'Qwen3-8B', 'mistral-7b': 'Mistral-7B-Instruct-v0.3',
             'llama-3.1-8b': 'Llama-3.1-8B-Instruct'}
    result = []
    for model, name in names.items():
        rr = [r for r in requests if r['model'] == model]
        qq = [r for r in qualifications if r['model'] == model]
        pp = [r for r in pairs if r['model'] == model]
        cc = [r for r in namespace if r['model'] == model]
        real = [r for r in rr if not yes(r['synthetic'])]
        accepted = {(r['cell'], r['case_id'], r['phase']): int(r['committed_tokens'])
                    for r in qq if yes(r['accepted'])}
        actual = [r for r in real if yes(r['compiled'])]
        covered = sum(int(r['initial_native_hit_tokens']) >= accepted[r['cell'], r['case_id'], 'authorized']
                      for r in actual if r['condition'].startswith('authorized_'))
        marker_end = next(r['marker_token_end_exclusive'] for r in markers
                          if r['model'] == name and r['mode'] == 'raw')
        marker_failures = [r for r in cc if yes(r['synthetic']) and
                           r['property'] in {'legacy_cross_domain_reuse', 'legacy_stale_binding_reuse'}]
        context = dict(model=model, business=len(rr), failures=sum(not yes(r['success']) for r in rr),
                       real_business=len(real), real_compiled_business=len(actual),
                       real_authorized_compiled_business=sum(r['condition'].startswith('authorized_') for r in actual),
                       real_authorized_compiled_initial_hits_cover_committed_prefix=covered,
                       real_length_finishes=sum(r['finish'] == 'length' for r in real),
                       synthetic_Raw_marker_token_end_exclusive=marker_end,
                       legacy_synthetic_cross_domain_or_stale_hits_cover_marker=sum(
                           int(r['second_actual_native_hits']) >= marker_end for r in marker_failures),
                       legacy_synthetic_cross_domain_or_stale_checks=len(marker_failures),
                       actual_verification_RPCs=sum(int(r['RPCs']) for r in qq),
                       qualification_reasons=dict(Counter(r['reason'] or 'PASS' for r in qq)),
                       verification_controller_total_ms=sum(float(r['full_controller_ms']) for r in qq),
                       accepted_controller_ms=sum(float(r['full_controller_ms']) for r in qq if yes(r['accepted'])),
                       not_accepted_controller_ms=sum(float(r['full_controller_ms']) for r in qq if not yes(r['accepted'])),
                       by_comparison={})
        for first, second in sorted({(r['first'], r['second']) for r in pp}):
            subset = [r for r in pp if r['first'] == first and r['second'] == second and not yes(r['synthetic'])]
            context['by_comparison'][first + ' -> ' + second] = tally_pairs(subset)
        context['authorized_compiled_real_pairs'] = tally_pairs([
            r for r in pp if not yes(r['synthetic']) and yes(r['compiled_second']) and
            r['second'] in {'authorized_post_decision', 'authorized_same_group_second_principal'}])
        context['qualification_by_phase'] = {
            phase: dict(decisions=len(part), accepted=sum(yes(r['accepted']) for r in part),
                        actual_RPCs=sum(int(r['RPCs']) for r in part),
                        controller_ms=sum(float(r['full_controller_ms']) for r in part),
                        reasons=dict(Counter(r['reason'] or 'PASS' for r in part)))
            for phase in ('legacy', 'authorized', 'controlled_wrong_candidate')
            for part in [[r for r in qq if r['phase'] == phase]]}
        result.append(context)
    payload = dict(schema_version='contractkv.repair-report-descriptive.v1',
                   post_hoc_reporting_not_an_admission_rule=True, new_GPU_requests=0,
                   independent_real_sources=6, actual_cells=9, model_rows=result,
                   limitation='The two phases have different work counts and ordered cache states. '
                   'No aggregate phase speedup or open-arrival capacity claim. Score changes and '
                   'zero events are observations, not proof of task correctness or general isolation.',
                   source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
