"""Read-only final frozen-source/runtime/worker audit; never hashes weights anew."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight
from scripts.tsc_tableIII_fullcost_worker_v3 import resource_snapshot

STUDY='results/tsc_task_faithful_open_arrival_20261018'
CORE='results/tsc_revision_mechanism_controls_20261018'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main(root,output):
    assert sys.platform=='linux' and not output.exists()
    study=root/STUDY;worker_observations=[];states=[]
    for phase,directory in [('baseline','calibration'),('profiles','calibration'),('qwen','formal'),('cross','formal'),('gate','formal')]:
        state=read(study/directory/f'{phase}_execution_state_v1.json')
        assert state['status']=='COMPLETE_PENDING_ANALYSIS' and state['worker_pid'] is None
        assert read(study/directory/f'{phase}_exit_v1.json')['returncode']==0
        launch=read(study/directory/f'{phase}_launch_v1.json');pid=launch['worker_pid'];cmdline=Path('/proc')/str(pid)/'cmdline'
        actual=cmdline.read_bytes().split(b'\0') if cmdline.exists() else []
        actual=[x.decode(errors='replace') for x in actual if x]
        same_live=actual==launch['command'];assert not same_live,'An owned experiment worker is still live'
        worker_observations.append(dict(phase=phase,recorded_PID=pid,PID_exists_at_check=cmdline.exists(),
            live_process_matches_owned_command=same_live,unrelated_process_arguments_not_retained=True))
        states+=state['completed_cells']
    assert len(states)==len(set(states))==37
    assert read(study/'calibration/profiles_supervisor_exit_v1.json')['returncode']==0
    assert read(study/'formal/formal_supervisor_exit_v1.json')['returncode']==0
    raw=read(study/'raw_calibration_freeze_v1.json');formal=read(study/'formal_freeze_v1.json')
    checked={}
    for frozen in (raw,formal):
        for row in frozen['files']:
            assert sha(root/row['path'])==row['sha256'],row['path'];checked[row['path']]=row['sha256']
    for row in raw['snapshot_files']:
        path=study/'source_snapshot_v1'/row['path'];assert sha(path)==row['sha256']
    assert sha(root/CORE/'preflight_v3/receipt_v1.json')==raw['parent_runtime_receipt_sha256']
    validate_preflight(root/CORE)
    requests=0
    for relative in states:
        cell=study/relative;complete=read(cell/'completion_v1.json');summary=read(cell/'summary.json')
        assert complete['status']=='complete' and summary['execution_complete']
        assert sha(cell/'raw.jsonl')==summary['raw_file_sha256']
        for row in complete['files']:assert sha(cell/row['path'])==row['sha256'] and (cell/row['path']).stat().st_size==row['bytes']
        requests+=summary['arrival_requests']
    assert requests==11640
    waves=[]
    for directory in ('calibration','formal'):
        for path in sorted((study/directory/'waves').glob('*_GPU_resources_v1.jsonl')):
            samples=0;hosts=Counter()
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    row=json.loads(line);assert not row.get('error_type') and row['foreign_GPU_PIDs']==[]
                    assert len(row['snapshot']['devices'])==2
                    samples+=1;hosts[row['snapshot']['host']]+=1
            assert samples>0;waves.append(dict(path=path.relative_to(study).as_posix(),samples=samples,hosts=dict(hosts),sha256=sha(path)))
    assert len(waves)==22,'4 calibration waves plus18 formal waves expected'
    value=dict(schema_version='contractkv.final-serving-post-integrity.v1',execution_cells=37,actual_business_requests=11640,
        all_checked_frozen_sources_and_runtime_match=True,checked_root_files=len(checked),checked_snapshot_files=len(raw['snapshot_files']),
        parent_full_model_SHA_receipt_reused=True,models_size_and_mtime_match_original_full_SHA_registry=True,
        full_model_SHA_or_runtime_copy_repeated=False,worker_observations=worker_observations,GPU_measurement_waves=waves,
        resource_snapshot_at_postcheck=resource_snapshot(),
        postcheck_GPU_occupancy_does_not_rewrite_earlier_measurement_exclusivity=True,new_GPU_requests=0,entry_sha256=sha(Path(__file__)))
    with output.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in value.items() if k not in ('worker_observations','GPU_measurement_waves','resource_snapshot_at_postcheck')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output)
