"""Independent Windows derivation, with explicit cross-version float comparison."""
import argparse
import json
from pathlib import Path
import shutil
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_raw_derive_v1 as derive


def main(root,view,receipt):
    relative=Path(derive.STUDY);study=root/relative
    assert not view.exists() and not receipt.exists()
    paths=[relative/'raw_calibration_protocol_v1.json',relative/'raw_calibration_freeze_v1.json',
        relative/'inputs_v1/faithful_selected_sessions_v1.jsonl',relative/'calibration/baseline_execution_state_v1.json',relative/'calibration/baseline_exit_v1.json']
    for job in derive.read(study/'raw_calibration_protocol_v1.json')['baseline_jobs']:
        paths += [relative/'calibration/cells'/job['id']/name for name in ('raw.jsonl','summary.json','completion_v1.json','client_audit_v2.json')]
    for path in paths:
        target=view/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/path,target)
    original=derive.write
    def Linux_text_write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as handle:json.dump(value,handle,indent=2);handle.write('\n')
    try:
        derive.write=Linux_text_write;derive.derive(view)
    finally:derive.write=original
    outputs=['calibration/derived_profile_plan_v1.json']+[f'calibration/arrivals/raw_profile_q_{i}_v1.json' for i in range(3)]
    expected=derive.read(study/outputs[0]);actual=derive.read(view/relative/outputs[0])
    offset_differences=[];arrival_checks=[]
    for index,name in enumerate(outputs[1:]):
        one=derive.read(study/name);two=derive.read(view/relative/name)
        assert one.keys()==two.keys()
        for key in one:
            if key!='waves':assert one[key]==two[key],key
        assert len(one['waves'])==len(two['waves'])==60
        differences=[]
        for a,b in zip(one['waves'],two['waves']):
            assert a.keys()==b.keys()
            for key in a:
                if key!='ready_offset_s':assert a[key]==b[key],key
            delta=abs(a['ready_offset_s']-b['ready_offset_s']);assert delta<=1e-9
            differences.append(delta)
        offset_differences+=differences
        expected_hash=derive.sha(study/name);actual_hash=derive.sha(view/relative/name)
        assert expected['profile_jobs'][index]['arrival_sha256']==expected_hash
        assert actual['profile_jobs'][index]['arrival_sha256']==actual_hash
        # Normalize only the proven arrival-byte hashes in comparison memory;
        # neither the archived arrival nor either derivation file is rewritten.
        actual['profile_jobs'][index]['arrival_sha256']=expected_hash
        arrival_checks.append(dict(file=name,actual_Linux_sha256=expected_hash,independent_Windows_sha256=actual_hash,
            max_absolute_offset_roundoff_s=max(differences),offsets_with_nonzero_roundoff=sum(x>0 for x in differences)))
    assert expected==actual,'Only arrival-file hashes may differ after bounded offset-roundoff check'
    with receipt.open('x',encoding='utf-8') as handle:json.dump(dict(
        derived_non_arrival_hash_fields_exact=True,arrival_identity_fields_exact=True,
        arrival_offset_absolute_tolerance_s=1e-9,max_actual_offset_roundoff_s=max(offset_differences),arrival_checks=arrival_checks,
        independent_Windows_recompute_from_four_actual_Raw_logs=True,
        algorithm_source_sha256=derive.sha(Path(derive.__file__)),
        adapter_boundary='Only output JSON newline LF; formulas, percentile, random seeds, input bytes and algorithm unchanged. CPython3.13 versus3.10 float-sum/libm roundoff in normalized arrival offsets is explicitly bounded; all executed traces retain their original Linux hashes.',
        derived_sha256=derive.sha(study/outputs[0]),new_GPU_requests=0),handle,indent=2)
    print('Independent Raw capacities/SLO/load exact; arrival membership/seed exact; max offset roundoff s='+str(max(offset_differences)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--view',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True);args=parser.parse_args();main(args.root.resolve(),args.view.resolve(),args.receipt)
