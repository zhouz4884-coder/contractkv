"""Post-hoc clock bound for completed fixed-arrival cells; not a capacity estimate."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

STUDY = 'results/tsc_task_faithful_open_arrival_20261018'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(root, output):
    assert not output.exists()
    study = root / STUDY
    protocol_path = study / 'formal_protocol_v1.json'
    frozen = read(study / 'formal_freeze_v1.json')
    assert sha(protocol_path) == next(x['sha256'] for x in frozen['files']
                                     if x['path'] == protocol_path.relative_to(root).as_posix())
    jobs = [j for j in read(protocol_path)['jobs'] if j['phase'] != 'gate']
    assert len(jobs) == 24
    groups = defaultdict(list)
    for job in jobs:
        groups[job['phase'], job['model'], job['load'], job['repeat']].append(job)
    rows = []
    inputs = {protocol_path: sha(protocol_path)}
    for (phase, model, load, repeat), group in sorted(groups.items()):
        assert len(group) == 2
        one = next(j for j in group if j['policy'] == 'raw-order')
        two = next(j for j in group if j['policy'] != 'raw-order')
        summaries = []
        for job in (one, two):
            cell = study / 'formal/cells' / job['id']
            complete_path = cell / 'completion_v1.json'
            summary_path = cell / 'summary.json'
            complete = read(complete_path)
            summary = read(summary_path)
            assert complete['status'] == 'complete' and complete['job'] == job
            # Completion commits the original raw stream, not the summary file.
            # Retain the metadata hash below; final full analysis audits raw clocks.
            assert summary['raw_file_sha256'] == next(x['sha256'] for x in complete['files'] if x['path'] == 'raw.jsonl')
            arrival_path = study / job['arrival']
            trace = read(arrival_path)
            assert sha(arrival_path) == job['arrival_sha256'] == summary['arrival_trace_sha256']
            last = max(w['ready_offset_s'] for w in trace['waves'])
            wall = summary['wall_s_including_all_setup_and_verification']
            assert abs(last - summary['planned_last_arrival_offset_s']) < 1e-8
            assert summary['execution_complete'] and summary['arrival_requests'] == 360
            assert summary['successful_futures'] == summary['futures'] == 324
            assert wall >= last > 0
            assert abs(summary['wall_service_end_time'] - summary['wall_begin_time'] - wall) < 1e-8
            summaries.append((wall, last, summary['arrival_trace_sha256']))
            for p in (complete_path, summary_path, arrival_path):
                inputs[p] = sha(p)
        (raw_wall, last, raw_trace), (contract_wall, other_last, contract_trace) = summaries
        assert raw_trace == contract_trace and last == other_last
        rows.append(dict(phase=phase, model=model, load=load, repeat=repeat,
                         Raw_cell=one['id'], Contract_cell=two['id'],
                         actual_Raw_wall_s=raw_wall, actual_Contract_wall_s=contract_wall,
                         observed_wall_ratio=raw_wall / contract_wall,
                         last_frozen_arrival_s=last,
                         maximum_possible_wall_ratio_against_this_Raw_clock=raw_wall / last,
                         Raw_wall_fraction_at_or_before_last_arrival=last / raw_wall,
                         Contract_time_after_last_arrival_s=contract_wall - last))
    aggregates = []
    for model, load in sorted({(r['model'], r['load']) for r in rows}):
        group = [r for r in rows if (r['model'], r['load']) == (model, load)]
        assert len(group) == 3
        raw = sum(r['actual_Raw_wall_s'] for r in group)
        contract = sum(r['actual_Contract_wall_s'] for r in group)
        lower = sum(r['last_frozen_arrival_s'] for r in group)
        aggregates.append(dict(model=model, load=load, repeats=3,
                               pooled_observed_wall_ratio=raw / contract,
                               pooled_maximum_possible_wall_ratio=raw / lower,
                               pooled_Raw_wall_fraction_at_or_before_last_arrival=lower / raw,
                               Raw_wall_s=raw, Contract_wall_s=contract,
                               unavoidable_frozen_arrival_span_s=lower))
    result = dict(schema_version='contractkv.post-hoc-arrival-wall-bound.v1',
                  post_hoc_explanatory_analysis=True, new_GPU_requests=0,
                  no_protocol_SLO_or_analysis_rule_changed=True,
                  boundary='For these completed fixed arrivals, all-request service wall is at least the last scheduled arrival. This bounds a wall ratio against the observed Raw clock, even with hypothetical zero service time. It is not an observed optimization, a Goodput bound, a capacity claim, a confidence interval, or a population generalization. Full original-log clock/quality/native integrity remains a separate audit.',
                  rows=rows, aggregates=aggregates,
                  inputs=[dict(path=p.relative_to(root).as_posix(), sha256=h) for p, h in sorted(inputs.items())],
                  entry_sha256=sha(Path(__file__)))
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(dict(complete_pairs=len(rows), aggregates=aggregates, new_GPU_requests=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
