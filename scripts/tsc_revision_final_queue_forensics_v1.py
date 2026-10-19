"""Describe actual client backlog and sampled VRAM; no counterfactual queue."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

STUDY = Path('results/tsc_task_faithful_open_arrival_20261018')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_queue(arrivals, departures):
    events = [(t, 1) for t in arrivals] + [(t, -1) for t in departures]
    level = peak = 0
    for _, change in sorted(events, key=lambda x: (x[0], -x[1])):
        level += change
        assert level >= 0
        peak = max(peak, level)
    assert level == 0
    return peak


def main(root, output):
    assert not output.exists()
    study = root / STUDY
    source = study / 'formal_analysis_v1/requests_v1.csv'
    with source.open(encoding='utf-8', newline='') as handle:
        requests = list(csv.DictReader(handle))
    assert len(requests) == 10800
    protocol_path = study / 'formal_protocol_v1.json'
    protocol = read(protocol_path)
    files = {source: sha(source), protocol_path: sha(protocol_path)}
    resources = {}
    results = []
    for job in protocol['jobs']:
        group = [r for r in requests if r['cell'] == job['id']]
        assert len(group) == 360
        arrival_path = study / job['arrival']
        assert sha(arrival_path) == job['arrival_sha256']
        trace = read(arrival_path)
        arrivals, processing, submitted = [], [], []
        for row in group:
            wave = trace['waves'][int(row['wave_index'])]
            assert row['session_id'] in wave['session_ids'] and int(row['turn']) == wave['turn']
            t = wave['ready_offset_s']
            before = float(row['queue_before_controller_ms']) / 1000
            controller = float(row['controller_to_submit_ms']) / 1000
            assert before >= 0 and controller >= 0
            arrivals.append(t)
            processing.append(t + before)
            submitted.append(t + before + controller)
        wave_path = study / 'formal/waves' / f"wave_{job['wave']}_GPU_resources_v1.jsonl"
        if wave_path not in resources:
            values = []
            for line in wave_path.read_text(encoding='utf-8').splitlines():
                item = json.loads(line)
                assert not item['foreign_GPU_PIDs']
                values.append(item['snapshot']['devices'])
            assert values
            resources[wave_path] = values
            files[wave_path] = sha(wave_path)
        memory = []
        for devices in resources[wave_path]:
            device = next(d for d in devices if int(d[0]) == job['lane'])
            assert device[3].endswith(' MiB')
            memory.append(float(device[3].split()[0]))
        files[arrival_path] = sha(arrival_path)
        results.append(dict(cell=job['id'], regime=job['phase'], model=job['model'],
            load=job['load'], policy=job['policy'], economic_gate=job['economic_gate'], repeat=job['repeat'],
            business_requests=360, peak_arrived_not_controller_started=peak_queue(arrivals, processing),
            peak_arrived_not_backend_submitted=peak_queue(arrivals, submitted),
            mean_queue_before_controller_ms=statistics.fmean(float(r['queue_before_controller_ms']) for r in group),
            sampled_VRAM_max_MiB=max(memory), sampled_VRAM_min_MiB=min(memory),
            resource_samples=len(memory)))
    value = dict(schema_version='contractkv.actual-client-queue-forensics.v1',
        post_hoc_descriptive_reconstruction=True, new_GPU_requests=0,
        source_records=10800, cells=results,
        boundary='Counts use frozen scheduled arrivals and each actual processing/submission offset from verified request clocks; no alternative scheduler or queue was simulated. Simultaneous arrivals precede departures, so the instantaneous ready batch of2 is included even without backlog. Client pending counts differ from native GPU waiting/active counters. VRAM is a2-second sampled total-use maximum, not a continuous peak or allocator/cached-resident breakdown. These observations do not uniquely attribute accumulated waiting to certification.',
        inputs=[dict(path=p.relative_to(root).as_posix(), sha256=h) for p, h in sorted(files.items())],
        source_sha256=sha(Path(__file__)))
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
    print(json.dumps(dict(cells=len(results), source_records=10800, new_GPU_requests=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
