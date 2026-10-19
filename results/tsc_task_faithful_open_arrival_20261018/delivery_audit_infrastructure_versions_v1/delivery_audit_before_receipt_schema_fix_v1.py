"""Validate completed experimental delivery; no measurement or analysis reruns."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

STUDY = Path('results/tsc_task_faithful_open_arrival_20261018')
DOCS = [
    'ContractKV_TSC_Final_Experimental_Strengthening_Report.md',
    'ContractKV_Contribution_Necessity_Evidence_Matrix.md',
    'ContractKV_Reviewer_Experimental_Closure_Matrix.md',
    'ContractKV_Service_Performance_and_Tail_Analysis.md',
    'ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md',
    'ContractKV_Final_Experimental_Completion_Audit.md',
    'tsc_revision_stage_progress_20261018_zh.md',
    'tsc_revision_GPU_execution_decisions_20261018_zh.md',
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main(root, output):
    assert not output.exists(), 'Preserve previous receipts'
    study = root / STUDY
    evidence = []

    def record(path):
        path = root / path
        assert path.is_file()
        evidence.append(dict(path=path.relative_to(root).as_posix(),
                             bytes=path.stat().st_size, sha256=sha(path)))

    old = ['tsc_tableIII_fullcost_replay_20261018',
           'tsc_revision_mechanism_controls_20261018',
           'tsc_mechanism_budget256_20261018',
           'tsc_real_repobench_mechanism_20261018']
    for name in old:
        for filename in ('local_archive_verification_v1.json', 'local_independent_recompute_v1.json'):
            path = Path('results') / name / filename
            assert read(root / path)['status'] == 'PASS'
            record(path)
    frozen = {
        'formal_freeze_v1.json': '390ea8314f3e60f38c393c7b18873148f5e8d0af69bdeb6b89911cebe03652ff',
        'raw_calibration_freeze_v1.json': 'f9a2b64a28952f9fa5f9929699ab60416dbbdd030f4348731d6444753af64b92',
    }
    for name, expected in frozen.items():
        assert sha(study / name) == expected
        record(STUDY / name)
    integrity = read(study / 'post_execution_integrity_v1.json')
    assert (integrity['execution_cells'], integrity['actual_business_requests']) == (37, 11640)
    assert integrity['all_checked_frozen_sources_and_runtime_match']
    assert integrity['checked_root_files'] == 58 and integrity['checked_snapshot_files'] == 564
    assert len(integrity['GPU_measurement_waves']) == 22
    assert integrity['models_size_and_mtime_match_original_full_SHA_registry']
    assert not integrity['full_model_SHA_or_runtime_copy_repeated']
    record(STUDY / 'post_execution_integrity_v1.json')

    package = study / 'evidence_package_v1'
    receipt = read(package / 'package_receipt_v1.json')
    assert receipt['sha256'] == 'ce8a001e246f04012d56276232ad2b4acb706149dfde60d0155473e649320cfc'
    assert receipt['bytes'] == 234884895 and receipt['regular_members'] == 1246
    assert receipt['round_trip_member_bytes_verified']
    assert receipt['all_frozen_root_dependencies_included'] and receipt['frozen_root_dependencies'] == 58
    assert sha(package / 'raw_member_inventory_v1.json') == receipt['member_inventory_sha256']
    joined = hashlib.sha256()
    total = 0
    for item in receipt['parts']:
        path = package / item['path']
        assert path.is_file() and path.stat().st_size == item['bytes']
        assert sha(path) == item['sha256']
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(8 << 20), b''):
                joined.update(block)
                total += len(block)
        record(STUDY / 'evidence_package_v1' / item['path'])
    assert total == receipt['bytes'] and joined.hexdigest() == receipt['sha256']
    for name in ('package_receipt_v1.json', 'raw_member_inventory_v1.json', 'README_zh.md'):
        record(STUDY / 'evidence_package_v1' / name)
    restored = read(study / 'local_archive_verification_v1.json')
    assert restored['status'] == 'PASS' and restored['verified_and_restored_regular_members'] == 1246
    assert restored['original_frozen_root_dependencies_verified'] == 58
    recomputed = read(study / 'local_independent_recompute_v1.json')
    assert recomputed['status'] == 'PASS'
    assert recomputed['independently_recomputed_cells'] == 37
    assert recomputed['independently_rescored_business_requests'] == 11640
    assert recomputed['original_archive_members_unchanged_after_recomputation'] == 1246
    assert recomputed['original_frozen_analysis_source_unchanged']
    assert recomputed['statistics_inputs_proven_equal_to_fresh_raw_recomputation']
    csv_count = 0
    for name, leaves in [('formal', 6891), ('calibration', 934)]:
        value = recomputed['phase_comparisons'][name]
        assert value['summary']['all_values_exact'] and value['summary']['exact_leaves'] == leaves
        assert value['summary']['close_float_leaves'] == 0
        assert value['summary_LF_normalized_bytes_equal']
        csv_count += len(value['CSV_bytes_equal'])
    assert csv_count == 13
    assert recomputed['source_sensitivity_comparison']['exact_leaves'] == 135
    assert recomputed['source_sensitivity_comparison']['all_values_exact']
    assert recomputed['new_GPU_requests'] == 0
    for name in ('local_archive_verification_v1.json', 'local_independent_recompute_v1.json',
                 'formal_analysis_v1/summary_v1.json', 'calibration_analysis_v1/summary_v1.json',
                 'formal_goodput_source_sensitivity_v1.json', 'actual_client_queue_forensics_v1.json',
                 'arrival_wall_bound_v1.json'):
        record(STUDY / name)
    summary = read(study / 'formal_analysis_v1/summary_v1.json')
    assert summary['complete_cells'] == 30 and summary['measured_business_requests'] == 10800
    assert summary['measured_future_requests'] == 9720
    assert summary['compiled_future_requests'] == 318 and summary['compiled_vs_witness_changes'] == 0
    assert summary['actual_verification_RPCs'] == 90
    calibration = read(study / 'calibration_analysis_v1/summary_v1.json')
    assert calibration['complete_cells'] == 7 and calibration['measured_business_requests'] == 840
    queue = read(study / 'actual_client_queue_forensics_v1.json')
    assert len(queue['cells']) == 30 and queue['source_records'] == 10800
    assert queue['new_GPU_requests'] == 0 and queue['post_hoc_descriptive_reconstruction']

    expected = {f'E{i}' for i in range(1, 6)} | {f'AE{i}' for i in range(1, 6)}
    expected |= {'R1.1', 'R1.2a', 'R1.2b', 'R1.3a', 'R1.3b', 'R1.4a', 'R1.4b'}
    expected |= {f'R1.{i}' for i in range(5, 13)}
    expected |= {f'R2.{i}' for i in range(1, 7)} | {f'R3.{i}' for i in range(1, 6)}
    matrix = (root / 'docs/ContractKV_Reviewer_Experimental_Closure_Matrix.md').read_text(encoding='utf-8')
    ids = re.findall(r'^\| ((?:AE|E|R[123]\.)[0-9]+[ab]?) \|', matrix, flags=re.M)
    assert len(ids) == 36 and set(ids) == expected and len(set(ids)) == len(ids)
    for name in DOCS:
        record(Path('docs') / name)
    for name in ('local_archive', 'local_recompute', 'queue_forensics', 'delivery_audit'):
        path = Path(f'scripts/tsc_revision_final_{name}_v1.py')
        record(path)
    assert sha(root / 'scripts/tsc_revision_final_serving_analysis_v1.py') == recomputed['analysis_source_sha256']
    assert sha(root / 'scripts/tsc_revision_final_local_recompute_v1.py') == recomputed['source_sha256']
    assert sha(root / 'scripts/tsc_revision_final_queue_forensics_v1.py') == queue['source_sha256']
    result = dict(status='PASS', scope='Experimental evidence delivery only, not manuscript submission readiness',
                  new_GPU_requests=0, old_completed_packages_reused=len(old),
                  new_complete_cells=37, new_actual_business_requests=11640,
                  frozen_Root_dependencies=58, raw_members=1246,
                  original_archive_sha256=receipt['sha256'], reviewed_requirement_IDs=sorted(expected),
                  reviewed_requirement_count=36, independently_recomputed_CSV_files=13,
                  JSON_original_bytes_not_claimed_equal=True, all_values_exact=True,
                  all_measured_negative_results_retained=True,
                  no_new_mechanism_or_threshold_or_source_selection=True,
                  publication_still_requires_remote_commit_and_blob_verification=True,
                  formal_manuscript_and_Response_Letter_deferred=True, evidence=evidence,
                  entry_sha256=sha(Path(__file__)))
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'new_complete_cells', 'new_actual_business_requests',
                                            'reviewed_requirement_count', 'new_GPU_requests')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve())
