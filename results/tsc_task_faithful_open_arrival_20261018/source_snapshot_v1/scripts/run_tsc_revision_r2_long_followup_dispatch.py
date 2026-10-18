"""Fixed Qwen native-mode and Llama larger-content follow-ups, two GPUs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Lock,Event
import time

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    definitions={'long_native_v3':('qwen','long-native-v3',9908,'R2_LONG_NATIVE_V3_COMPLETE'),
                 'long_extent_v4':('llama','long-extent-v4',9910,'R2_LONG_EXTENT_V4_COMPLETE')}
    tasks=[('long_native_v3',1),('long_native_v3',2),('long_extent_v4',1),('long_native_v3',3),('long_extent_v4',2),('long_extent_v4',3)]
    lock=Lock();failed=Event();index=0;completed=Counter()
    def guard(study):
        base=root/'results/tsc_revision_r2'/study;amendment=json.loads((base/'execution_dispatch_freeze_v1.json').read_text())
        if sha(base/'freeze.json')!=amendment['primary_freeze_sha256']:raise ValueError('Primary followup freeze changed')
        for r in amendment['files']:
            if sha(root/r['path'])!=r['sha256'] or sha(base/r['snapshot'])!=r['sha256']:raise ValueError('Followup dispatch source changed')
    for study in definitions:guard(study)
    while 'R2_LONG_FORMAT_V2_COMPLETE' not in (root/'logs/tsc_revision_r2/long_format_v2.log').read_text(errors='replace'):
        if not Path('/proc/2678298').exists():raise RuntimeError('V2 long study ended without completion')
        time.sleep(5)
    def emit(study,row):
        with lock:
            path=root/'results/tsc_revision_r2'/study/'execution_dispatch_v1/execution_events.jsonl'
            with path.open('a') as out:out.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),**row})+'\n')
        print(json.dumps(row),flush=True)
    def gpu_free(lane):
        uuid=subprocess.check_output(['nvidia-smi','-i',str(lane),'--query-gpu=uuid','--format=csv,noheader'],text=True).strip()
        lines=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
        return not any(line.split(',')[0].strip()==uuid for line in lines)
    def worker(lane):
        nonlocal index
        try:
            while not failed.is_set():
                with lock:
                    if index>=len(tasks):return
                    study,repeat=tasks[index];index+=1
                guard(study);model,prefix,port,marker=definitions[study];cell=f'{prefix}_{model}_r{repeat}'
                for _ in range(30):
                    if gpu_free(lane):break
                    time.sleep(2)
                else:raise RuntimeError('GPU occupied; no process stopped')
                base=root/'results/tsc_revision_r2'/study
                emit(study,{'event':'prospective_cell_assignment','cell':cell,'gpu_lane':lane,'primary_freeze_sha256':sha(base/'freeze.json'),'dispatch_freeze_sha256':sha(base/'execution_dispatch_freeze_v1.json')})
                with (root/'logs/tsc_revision_r2'/(study+'.log')).open('a') as log:
                    result=subprocess.run(['bash',str(base/'execution_dispatch_v1/cell_runner.sh'),model,str(repeat),str(lane),str(port+lane)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
                emit(study,{'event':'cell_process_exit','cell':cell,'gpu_lane':lane,'returncode':result.returncode})
                if result.returncode:raise RuntimeError('Followup cell failed; preserve attempt')
                with lock:
                    completed[study]+=1;done=completed[study]==3
                if done:
                    with (root/'logs/tsc_revision_r2'/(study+'.log')).open('a') as log:log.write(marker+'\n')
                    print(marker,flush=True)
        except Exception:
            failed.set();raise
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,lane) for lane in (0,1)]
        for future in futures:future.result()
    print('R2_LONG_FOLLOWUP_V3V4_COMPLETE',flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
