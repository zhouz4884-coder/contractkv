"""Wait for the existing Qwen phase only, audit/package on CPU, never rerun GPU."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

def read(p):return json.loads(p.read_text())
def state(p,x):
    q=p.with_suffix('.tmp');q.write_text(json.dumps(x,indent=2)+'\n');q.replace(p)
def main(root):
    study=root/'results/tsc_template_task_serving_20261019';path=study/'postprocessing_Qwen_v4.json'
    assert not path.exists();current=dict(status='WAITING_FOR_EXISTING_QWEN_PHASE',pid=os.getpid(),steps=[],new_GPU_requests=0);state(path,current)
    try:
        deadline=time.monotonic()+3*3600
        while not (study/'development_exit_qwen_v4.json').exists():
            if time.monotonic()>deadline:raise TimeoutError('No GPU worker was restarted')
            time.sleep(10)
        assert read(study/'development_exit_qwen_v4.json')['returncode']==0,'Preserve and attribute infrastructure failure'
        py='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
        commands=[('analysis',[py,'-B',str(root/'scripts/tsc_template_task_development_analysis_v2.py'),'--root',str(root),'--model','Qwen3-8B','--output',str(study/'analysis_Qwen3-8B_v4')]),
                  ('package',[py,'-B',str(root/'scripts/tsc_template_task_package_development_v4.py'),'--root',str(root),'--model','Qwen3-8B'])]
        for name,command in commands:
            current['status']='CPU_'+name.upper();state(path,current)
            with (study/f'CPU_tmp/postprocessing_{name}_Qwen_v4.log').open('xb') as f:done=subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT)
            current['steps'].append(dict(stage=name,returncode=done.returncode));state(path,current)
            assert done.returncode==0,'CPU audit/delivery failed; preserve records, do not rerun GPU'
        current.update(status='READY_FOR_LOCAL_INDEPENDENT_RECOMPUTE',pid=None);state(path,current)
    except BaseException as e:
        current.update(status='FAILURE_PRESERVED',pid=None,error_type=type(e).__name__,error_message=str(e));state(path,current);raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);main(p.parse_args().root.resolve())
