"""Continue five never-measured cells; reuse nineteen complete cells verbatim.

The frozen v3 run_cell, client, policy, models and runtimes are unchanged.
This explicit execution addendum supersedes pair-level replay after a bind
failure before the first TP2 Contract server/client was even started.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_tableIII_fullcost_worker_v3 as original


def check(root,study,addendum):
    assert original.sha(Path(__file__))==addendum['continuation_source_sha256']
    assert original.sha(Path(original.__file__))==addendum['unchanged_worker_v3_sha256']
    for path,digest in addendum['frozen_files'].items():
        assert original.sha(root/path)==digest,path
    for entry in addendum['preserved_completed_files']:
        path=study/entry['path']
        assert path.is_file() and path.stat().st_size==entry['bytes'] and original.sha(path)==entry['sha256'],entry['path']
    previous=study/'launch_attempt3_preflight'
    receipt=previous/'preflight_receipt_v1.json'
    assert original.sha(receipt)==addendum['unchanged_preflight_receipt_sha256']
    for entry in original.read(receipt)['metadata_files']:
        assert original.sha(previous/entry['path'])==entry['sha256']
    for model in original.read(previous/'model_registry_v1.json')['models']:
        for entry in model['files']:
            st=(original.DISK/'models'/model['model']/entry['file']).stat()
            assert (st.st_size,st.st_mtime_ns)==(entry['bytes'],entry['mtime_ns'])
    for kind in ('qwen','phase19c'):
        inv=original.read(previous/(kind+'_runtime_v1.json'))
        assert original.runtime_inventory(Path(inv['copy'])/'vllm')==inv['after']
    protocol=original.read(study/'protocol_v1.json')
    models={x['key']:x for x in protocol['models']}
    for pair in addendum['completed_pair_paths']:
        name=Path(pair).parts[1];model=models[name.rsplit('_r',1)[0]]
        assert original.read(study/pair/'pair_completion_v1.json')['status']=='complete'
        for policy in ('raw','contract'):original.validate_cell(study/pair/policy,model,policy)
    raw=study/addendum['completed_unpaired_raw_path']
    raw_checks=original.validate_cell(raw,models['qwen14'],'raw')
    assert raw_checks['future_requests']==225 and raw_checks['completed_business_rows']==250
    failed=study/'cells/qwen14_r1/attempt3/contract'
    assert {p.name for p in failed.iterdir()}=={'failure_v1.json'},'Only a prelaunch failure can use this continuation'
    assert original.read(failed/'failure_v1.json')['error_type']=='OSError'
    assert len(addendum['completed_pair_paths'])==9 and len(addendum['remaining_cells'])==5
    assert len({(x['repeat'],x['policy']) for x in addendum['remaining_cells']})==5
    return models['qwen14']


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=('preflight','execute'),required=True)
    p.add_argument('--execution-addendum-sha256',required=True);p.add_argument('--receipt-sha256')
    a=p.parse_args();root=a.root.resolve();study=root/original.STUDY_REL
    assert sys.platform=='linux' and root.is_relative_to(original.DISK)
    addendum_path=study/'execution_continuation_v4.json'
    assert original.sha(addendum_path)==a.execution_addendum_sha256
    addendum=original.read(addendum_path)
    assert not original.foreign_pids(original.resource_snapshot()),'Never overlap another GPU task'
    with (study/'worker.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        model=check(root,study,addendum)
        out=study/'continuation_v4_preflight';receipt=out/'receipt_v1.json'
        if not receipt.exists():
            out.mkdir()
            original.write(out/'resource_observation_v1.json',original.resource_snapshot())
            original.write(receipt,dict(utc=original.now(),execution_addendum_sha256=a.execution_addendum_sha256,
                source_sha256=original.sha(Path(__file__)),old_preflight_reused=True,
                full_weights_rehashed=False,model_stat_and_existing_runtime_hashes_match=True,
                complete_cells_reused_without_rerun=19,remaining_new_cells=5,new_GPU_requests=0))
        assert original.read(receipt)['execution_addendum_sha256']==a.execution_addendum_sha256
        if a.mode=='preflight':
            print(json.dumps(dict(status='CONTINUATION_PREFLIGHT_COMPLETE',receipt_sha256=original.sha(receipt))))
            return 0
        assert a.receipt_sha256==original.sha(receipt),'Publish this exact receipt before continuation'
        state_path=study/'execution_state_v1.json';state=original.read(state_path)
        # Preserve the old failure state separately. Operational state alone is
        # updated so existing downstream guards can observe final completion.
        completed=list(addendum['completed_pair_paths']);owned=set()
        state.update(status='RUNNING',formal_worker_pid=os.getpid(),worker_attempt=4,
            formal_GPU_cells_completed=19,paired_GPU_cells_completed=18,completed_pairs=completed,
            execution_continuation_addendum_sha256=a.execution_addendum_sha256)
        original.write(state_path,state)
        try:
            for repeat in (1,2,3):
                pair=study/'cells'/f'qwen14_r{repeat}'/'attempt4'
                pair.mkdir(parents=True)
                checks={}
                if repeat==1:
                    source=(study/addendum['completed_unpaired_raw_path']).resolve()
                    assert source.is_relative_to(study.resolve())
                    (pair/'raw').symlink_to(source,target_is_directory=True)
                    original.validate_cell(pair/'raw',model,'raw')
                    checks['raw']=original.read(source/'completion_v1.json')['checks']
                    original.write(pair/'reused_complete_cell_v1.json',dict(source=str(source),
                        completion_sha256=original.sha(source/'completion_v1.json'),not_a_partial_cell_resume=True))
                state.update(current_pair=f'qwen14_r{repeat}');original.write(state_path,state)
                jobs=[x for x in addendum['remaining_cells'] if x['repeat']==repeat]
                for job in jobs:
                    policy=job['policy'];assert policy not in checks
                    checks[policy]=original.run_cell(root,study/'launch_attempt3_preflight/runtimes/phase19c',
                        model,repeat,policy,pair/policy,job['port'],'0,1',owned)
                    state['formal_GPU_cells_completed']+=1;original.write(state_path,state)
                assert set(checks)=={'raw','contract'} and not original.foreign_pids(original.resource_snapshot())
                original.write(pair/'pair_completion_v1.json',dict(status='complete',time_utc=original.now(),
                    model=model['model'],repeat=repeat,cells=checks,
                    direct_wall_multiplier=checks['raw']['service_wall_with_drain_s']/checks['contract']['service_wall_with_drain_s'],
                    future_pairs=225,execution_continuation_addendum_sha256=a.execution_addendum_sha256,
                    preserved_raw_from_before_prelaunch_failure=repeat==1,
                    claim='New original-cohort measurement. Prelaunch bind failure retained; complete Raw cell reused without rerun.'))
                completed.append(str(pair.relative_to(study)));state.update(completed_pairs=completed,paired_GPU_cells_completed=len(completed)*2)
                original.write(state_path,state)
            assert state['formal_GPU_cells_completed']==24 and len(completed)==12
            # Verify all preserved measurement bytes once more after completion.
            for entry in addendum['preserved_completed_files']:
                assert original.sha(study/entry['path'])==entry['sha256']
            state.update(status='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS',current_pair=None,formal_worker_pid=None,completed_at_utc=original.now())
            original.write(state_path,state)
        except BaseException as e:
            state.update(status='INFRASTRUCTURE_OR_PROTOCOL_FAILURE',formal_worker_pid=None,error_type=type(e).__name__,error_message=str(e),time_utc=original.now())
            original.write(state_path,state);raise
    return 0


if __name__=='__main__':raise SystemExit(main())
