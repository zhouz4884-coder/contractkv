"""Require actual receipts before recording bounded experimental completion."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
STUDY=Path('results/tsc_behavior_scope_repair_20261020')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(root,report):
    s=root/STUDY;proof=read(s/'all_local_independent_recompute_v1.json');fees=read(s/'all_fee_coverage_v1.json');conformance=read(s/'validation_conformance_v1.json')
    assert proof['status']==fees['status']==conformance['status']=='PASS'
    assert all(r['all_values_exactly_equal'] for r in proof['independent_recomputations'])
    primary=read(s/'validation_analysis_v5.json')
    assert sum(v['compiled_pairs'] for v in primary['models'].values())==84
    assert all(v['compiled_ID_or_EOS_changes']==v['compiled_score_drops']==v['allroute_score_drops']==0 for v in primary['models'].values())
    assert conformance['counts']['strict_compiled_actual_prefix_and_exact_scope_and_witness_match']==84
    assert conformance['counts']['rejected_registrations_zero_compiled_publication']==14
    assert fees['total_actual_generated_HTTP']==954 and fees['total_actual_verification_HTTP']==34
    release=read(s/'final_release_observation_v1.json');assert not release['GPU'] and not release['actual_worker_command']
    counts={};elapsed=0
    for phase in ['development','validation']:
        state=read(s/(phase+'_execution_state_v4.json'));exit=read(s/(phase+'_exit_v4.json'))
        assert state['status']=='COMPLETE_PENDING_INDEPENDENT_ANALYSIS' and exit['returncode']==0 and not exit['automatic_retries']
        expected=6 if phase=='development' else 12;assert len(state['completed_cells'])==state['planned_cells']==expected
        counts[phase]=expected;elapsed+=exit['ended_epoch_s']-exit['started_epoch_s']
    table=read(s/'final_descriptive_tables_v1.json')
    ratios={r['model']:r['full_wall_throughput_ratio'] for r in table['aggregate'] if r['phase']=='validation' and r['policy']=='Strict-exact'}
    result=dict(status='BOUNDED_EXPERIMENT_AND_CODE_REPAIR_COMPLETE',cells=counts,total_cells=18,business_requests=912,
        strict_independent_compiled_pairs=84,strict_independent_ID_EOS_differences=0,strict_independent_score_drops=0,
        independent_full_wall_ratios=ratios,performance_not_universally_positive=True,
        total_actual_generation_HTTP=954,total_actual_verification_HTTP=34,
        all_fees_and_initial_Native_requests_accounted=True,own_worker_stopped_and_GPU_released=True,
        GPU_worker_elapsed_seconds_two_stages_sum=elapsed,
        elapsed_includes_model_startup_and_shutdown_not_pure_GPU_kernel_time=True,
        original_archive_members=379,archive_sha256=proof['archive_sha256'],
        report=report.relative_to(root).as_posix(),report_sha256=sha(report),
        independent_recompute_receipt_sha256=sha(s/'all_local_independent_recompute_v1.json'),
        manuscript_Response_Letter_edits=False,new_GPU_matrix_after_declared_completion=False,
        publication='See publication_receipt_v1.json for subsequently verified data commit; not inferred from this local completion record.',
        source_sha256=sha(Path(__file__)))
    out=s/'completion_receipt_v1.json'
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.report.resolve())
