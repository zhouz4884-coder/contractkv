"""Wait for the existing9 cells, then CPU audit/analyze/package exactly once."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight, resource_snapshot


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
def state(p,value):
    q=p.with_suffix('.tmp');q.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');q.replace(p)


def main(root):
    study=root/'results/tsc_authorization_task_repair_20261019'
    sp=study/'postprocessing_state_v1.json';assert not sp.exists()
    current=dict(status='WAITING_FOR_EXISTING_GPU',postprocess_pid=os.getpid(),new_GPU_requests=0,steps=[])
    state(sp,current)
    deadline=time.monotonic()+6*3600
    try:
        while not (study/'worker_exit_v2.json').exists():
            if time.monotonic()>deadline:raise TimeoutError('Wait expired; existing GPU work was not interrupted')
            time.sleep(10)
        assert read(study/'worker_exit_v2.json')['returncode']==0,'Preserve failed GPU run; no automatic retry'
        run=read(study/'execution_state_v2.json')
        assert run['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(run['completed_cells'])==9
        freeze=read(study/'freeze_v2.json')
        assert sha(study/'freeze_v2.json')=='b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3'
        for row in freeze['files']:assert sha(root/row['path'])==row['sha256']
        parent=root/'results/tsc_revision_mechanism_controls_20261018'
        validate_preflight(parent)
        assert sha(parent/'preflight_v3/receipt_v1.json')==freeze['parent_runtime_receipt_sha256']
        actual=0
        for relative in run['completed_cells']:
            cell=study/relative;completion=read(cell/'completion_v1.json')
            for row in completion['files']:assert sha(cell/row['path'])==row['sha256']
            with (cell/'responses.jsonl').open() as f:
                rows=[json.loads(line) for line in f if line.strip()]
            assert rows[-1]['counts']['business']==92
            actual+=sum(row['event']=='business' for row in rows)
        assert actual==828
        write(study/'post_execution_integrity_v1.json',dict(status='PASS',GPU_cells=9,actual_business_requests=actual,
            checked_frozen_files=len(freeze['files']),models_stat_and_immutable_parent_runtime_match=True,
            no_full_model_hash_or_runtime_copy_repeated=True,resource_at_postcheck=resource_snapshot(),
            source_sha256=sha(Path(__file__)),new_GPU_requests=0))
        python='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
        commands=[('marker_positions',[python,'-B',str(root/'scripts/tsc_repair_marker_positions_v1.py'),'--root',str(root)]),
                  ('analysis',[python,'-B',str(root/'scripts/tsc_repair_analyze_v1.py'),'--root',str(root),'--output',str(study/'analysis_v1')]),
                  ('package',[python,'-B',str(root/'scripts/tsc_repair_package_v1.py'),'--root',str(root)])]
        control=study/'CPU_tmp';control.mkdir(exist_ok=True)
        for label,command in commands:
            current['status']='RUNNING_'+label.upper();state(sp,current)
            started=time.time()
            with (control/(label+'_v1.log')).open('xb') as log:
                done=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            current['steps'].append(dict(stage=label,returncode=done.returncode,
                started_epoch_s=started,ended_epoch_s=time.time(),source_sha256=sha(Path(command[2]))))
            state(sp,current)
            assert done.returncode==0,'CPU step failed; retain data and logs without automatic retry: '+label
        current.update(status='CPU_ANALYSIS_PACKAGE_COMPLETE_PENDING_LOCAL_RECOMPUTE',postprocess_pid=None)
        state(sp,current)
        write(study/'postprocessing_exit_v1.json',dict(returncode=0,completed_stages=3,new_GPU_requests=0,
              source_sha256=sha(Path(__file__))))
    except BaseException as error:
        current.update(status='CPU_FAILURE_PRESERVED',postprocess_pid=None,error_type=type(error).__name__,error_message=str(error))
        state(sp,current)
        write(study/'postprocessing_exit_v1.json',dict(returncode=1,error_type=type(error).__name__,error_message=str(error),new_GPU_requests=0))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root.resolve())
