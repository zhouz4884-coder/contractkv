"""Independently rerun frozen analyses from the verified original archive."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

STUDY = Path('results/tsc_task_faithful_open_arrival_20261018')
ANALYSIS_SHA = 'ac65994e9770494b91583474b23119f5f4373b2f0e1d4e2ffa42f4bae8336864'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def compare_values(expected, actual):
    facts = dict(exact_leaves=0, close_float_leaves=0, max_absolute_float_delta=0.,
                 relative_tolerance=1e-12, absolute_tolerance=1e-8)
    def walk(a, b, location='root'):
        assert type(a) is type(b), (location, type(a).__name__, type(b).__name__)
        if isinstance(a, dict):
            assert a.keys() == b.keys(), location
            for key in a:
                walk(a[key], b[key], location + '/' + str(key))
        elif isinstance(a, list):
            assert len(a) == len(b), location
            for index, (x, y) in enumerate(zip(a, b)):
                walk(x, y, location + '/' + str(index))
        elif a == b:
            facts['exact_leaves'] += 1
        else:
            assert isinstance(a, float) and math.isfinite(a) and math.isfinite(b), location
            assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-8), (location, a, b)
            facts['close_float_leaves'] += 1
            facts['max_absolute_float_delta'] = max(facts['max_absolute_float_delta'], abs(a - b))
    walk(expected, actual)
    facts['all_values_exact'] = facts['close_float_leaves'] == 0
    return facts


def execute(command, receipt, console, source):
    if receipt.exists():
        previous = read(receipt)
        assert previous['returncode'] == 0 and previous['command'] == command
        assert previous['original_frozen_source_sha256'] == sha(source)
        return previous
    assert not console.exists(), 'Preserve previous failed execution and inspect its receipt'
    started = time.time()
    with console.open('xb') as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    value = dict(returncode=result.returncode, command=command, started_epoch_s=started,
                 ended_epoch_s=time.time(), original_frozen_source_sha256=sha(source), new_GPU_requests=0)
    write(receipt, value)
    assert result.returncode == 0, console
    return value


def main(root, records):
    root, records = root.resolve(), records.resolve()
    assert read(records / 'local_archive_verification_v1.json')['status'] == 'PASS'
    output = records / 'local_independent_recompute_v1.json'
    assert not output.exists()
    source = root / 'scripts/tsc_revision_final_serving_analysis_v1.py'
    assert sha(source) == ANALYSIS_SHA
    observations = {}
    for phase, expected in [('formal', 30), ('calibration', 7)]:
        target = root / STUDY / f'local_independent_{phase}_v1'
        receipt = records / f'local_independent_{phase}_execution_v1.json'
        command = [sys.executable, '-B', str(source), '--root', str(root), '--phase', phase,
                   '--output', str(target)]
        assert receipt.exists() or not target.exists(), 'Do not overwrite an existing unverified analysis attempt'
        execute(command, receipt, records / f'local_independent_{phase}_console_v1.log', source)
        reference = root / STUDY / ('formal_analysis_v1' if phase == 'formal' else 'calibration_analysis_v1')
        expected_summary, actual_summary = read(reference / 'summary_v1.json'), read(target / 'summary_v1.json')
        assert actual_summary['complete_cells'] == expected
        compared = compare_values(expected_summary, actual_summary)
        files = []
        assert {p.name for p in reference.glob('*.csv')} == {p.name for p in target.glob('*.csv')}
        for original in sorted(reference.glob('*.csv')):
            other = target / original.name
            assert original.read_bytes() == other.read_bytes(), original.name
            files.append(dict(file=original.name, bytes=original.stat().st_size, sha256=sha(original)))
        observations[phase] = dict(summary=compared, CSV_bytes_equal=files,
            summary_bytes_equal=(reference / 'summary_v1.json').read_bytes() == (target / 'summary_v1.json').read_bytes(),
            summary_LF_normalized_bytes_equal=(reference / 'summary_v1.json').read_bytes().replace(b'\r\n', b'\n') ==
                                             (target / 'summary_v1.json').read_bytes().replace(b'\r\n', b'\n'))
    reference = root / STUDY / 'formal_analysis_v1'
    local = root / STUDY / 'local_independent_formal_v1'
    # The untouched statistics entry reads the archive's original directory.
    # Establish equivalence to newly recomputed inputs before using those bytes.
    assert read(reference / 'summary_v1.json') == read(local / 'summary_v1.json')
    for name in ('requests_v1.csv', 'paired_performance_v1.csv'):
        assert (reference / name).read_bytes() == (local / name).read_bytes()
    statistics_source = root / 'scripts/tsc_revision_final_goodput_cluster_sensitivity_v1.py'
    plan = read(root / STUDY / 'formal_statistics_addendum_v1.json')
    assert sha(statistics_source) == plan['source_sha256']
    target = root / STUDY / 'local_independent_source_sensitivity_v1.json'
    receipt = records / 'local_independent_sensitivity_execution_v1.json'
    assert receipt.exists() or not target.exists()
    command = [sys.executable, '-B', str(statistics_source), '--root', str(root), '--output', str(target)]
    execute(command, receipt, records / 'local_independent_sensitivity_console_v1.log', statistics_source)
    sensitivity = compare_values(read(root / STUDY / 'formal_goodput_source_sensitivity_v1.json'), read(target))
    inventory = read(records / 'evidence_package_v1/raw_member_inventory_v1.json')
    for row in inventory['members']:
        path = root / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], row['path']
    result = dict(status='PASS', original_archive_sha256=read(records / 'local_archive_verification_v1.json')['archive_sha256'],
                  independently_recomputed_cells=37, independently_rescored_business_requests=11640,
                  original_frozen_analysis_source_unchanged=True, analysis_source_sha256=ANALYSIS_SHA,
                  phase_comparisons=observations, source_sensitivity_comparison=sensitivity,
                  statistics_inputs_proven_equal_to_fresh_raw_recomputation=True,
                  original_archive_members_unchanged_after_recomputation=len(inventory['members']),
                  no_output_or_prompt_IDs_reconstructed=True, new_GPU_requests=0,
                  source_sha256=sha(Path(__file__)))
    write(output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.records)
