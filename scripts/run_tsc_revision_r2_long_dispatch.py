"""Run the fixed nine long cells on GPUs as their pilot work finishes."""
import argparse
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
    base=root/'results/tsc_revision_r2/long_format_v2';dispatch=base/'execution_dispatch_v1'
    amendment=json.loads((base/'execution_dispatch_freeze_v1.json').read_text())
    def guard():
        if sha(base/'freeze.json')!=amendment['primary_freeze_sha256']:raise ValueError('Primary long freeze changed')
        for item in amendment['files']:
            if sha(root/item['path'])!=item['sha256'] or sha(base/item['snapshot'])!=item['sha256']:raise ValueError('Dispatch source changed')
    guard();tasks=[(m,r) for m in ('qwen','mistral','llama') for r in (1,2,3)]
    lock=Lock();failed=Event();index=0
    def emit(row):
        with lock:
            with (dispatch/'execution_events.jsonl').open('a') as stream:stream.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),**row})+'\n')
        print(json.dumps(row),flush=True)
    def pilot_done(lane):
        if lane==0:
            names=[f'{s}_qwen_{policy}_r1' for s in ('single-session','template-fanout') for policy in ('raw-order','legacy-prefix','margin-benefit')]
            for name in names:
                path=root/'results/tsc_revision_r2/development_pilot_v1/cells'/name/'summary.json'
                if not path.exists() or not json.loads(path.read_text())['execution_complete']:return False
            return True
        return 'R2_DEVELOPMENT_PILOT_V1_COMPLETE' in (root/'logs/tsc_revision_r2/development_pilot_v1.log').read_text(errors='replace')
    def no_gpu_process(lane):
        uuid=subprocess.check_output(['nvidia-smi','-i',str(lane),'--query-gpu=uuid','--format=csv,noheader'],text=True).strip()
        rows=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
        return not any(row.split(',')[0].strip()==uuid for row in rows)
    def worker(lane):
        nonlocal index
        while not pilot_done(lane):
            if failed.is_set():return
            if not Path('/proc/2646740').exists():raise RuntimeError('Pilot ended without required completion')
            time.sleep(5)
        while not failed.is_set():
            with lock:
                if index>=len(tasks):return
                model,repeat=tasks[index];index+=1
            guard();cell=f'long-format-v2_{model}_r{repeat}'
            for _ in range(30):
                if no_gpu_process(lane):break
                time.sleep(2)
            else:raise RuntimeError('GPU remains occupied; inspect ownership, no process killed')
            emit({'event':'prospective_cell_assignment','cell':cell,'gpu_lane':lane,'primary_freeze_sha256':amendment['primary_freeze_sha256'],'dispatch_freeze_sha256':sha(base/'execution_dispatch_freeze_v1.json')})
            result=subprocess.run(['bash',str(dispatch/'cell_runner.sh'),model,str(repeat),str(lane),str(9904+lane)],cwd=root)
            emit({'event':'cell_process_exit','cell':cell,'gpu_lane':lane,'returncode':result.returncode})
            if result.returncode:failed.set();raise RuntimeError('Long cell failed, preserve attempt')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(worker,lane) for lane in (0,1)]
        for result in results:
            try:result.result()
            except Exception:
                failed.set();raise
    if failed.is_set():return 2
    print('R2_LONG_FORMAT_V2_COMPLETE',flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
