"""Watch the one existing formal worker; no launch/retry or parameter changes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def state(p,r):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(r,indent=2)+'\n');t.replace(p)
def main(root):
    study=root/'results/tsc_template_task_serving_20261019';path=study/'postprocessing_formal_v1.json'
    assert not path.exists();value=dict(status='WAITING_FOR_EXISTING_FORMAL_WORKER',pid=os.getpid(),new_GPU_requests=0,steps=[]);state(path,value)
    try:
        deadline=time.monotonic()+24*3600
        while not (study/'formal_exit_v1.json').exists():
            if time.monotonic()>deadline:raise TimeoutError('Formal wait expired; no worker restarted')
            time.sleep(20)
        assert read(study/'formal_exit_v1.json')['returncode']==0,'Preserve incomplete scientific phase; do not rerun GPU'
        py='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
        tasks=[('analysis',[py,'-B',str(root/'scripts/tsc_template_task_formal_analysis_v1.py'),'--root',str(root),'--output',str(study/'formal_analysis_v1')]),
               ('package',[py,'-B',str(root/'scripts/tsc_template_task_package_formal_v1.py'),'--root',str(root)])]
        for label,command in tasks:
            value['status']='CPU_'+label.upper();state(path,value)
            if shutil.which('ionice'):command=['ionice','-c','3',*command]
            with (study/('CPU_tmp/postprocessing_formal_'+label+'_v1.log')).open('xb') as f:
                done=subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT,preexec_fn=lambda:os.nice(10))
            value['steps'].append(dict(stage=label,returncode=done.returncode));state(path,value)
            assert done.returncode==0,'CPU analysis/delivery failure retained, no GPU rerun'
        value.update(status='FORMAL_EVIDENCE_READY_PENDING_LOCAL_INDEPENDENT_RECOMPUTE_AND_MD_REPORT',pid=None);state(path,value)
    except BaseException as e:
        value.update(status='FAILURE_PRESERVED',pid=None,error_type=type(e).__name__,error_message=str(e));state(path,value);raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
