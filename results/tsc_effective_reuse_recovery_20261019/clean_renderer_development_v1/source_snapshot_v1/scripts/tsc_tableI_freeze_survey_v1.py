"""Create the immutable survey manifest after CPU preparation, before forwards."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    a=p.parse_args();a.root=a.root.resolve();assert not (a.root/'freeze.json').exists()
    assert not (a.root/'cells').exists()
    protocol=ROOT/'configs/tsc_tableI_remeasurement_20261018_v1.json'
    prepared=json.loads((a.root/'inputs_v1/input_preparation_v1.json').read_text())
    assert prepared['protocol_sha256']==sha(protocol)
    assert prepared['selected_packed_file_sha256']==sha(a.root/'inputs_v1/selected_packed_sources_v1.jsonl')
    assert prepared['selected_sources']==125 and prepared['distinct_sources']==125
    native=json.loads((a.root/'native_preflight_v1.json').read_text())
    assert native['overlay_registered_python_files_all_match_RECORD'] and native['model_files_all_sha256_match']
    files=[protocol,ROOT/'results/tsc_revision_r4/model_registry_v1.json']
    files += sorted((ROOT/'scripts').glob('tsc_tableI_*v1.py'))
    files += [ROOT/'scripts/run_tsc_tableI_survey_v1.sh',ROOT/'scripts/tsc_revision_r4_input_fidelity.py',
              ROOT/'scripts/phase22_llama_layout_ladder.py',ROOT/'scripts/phase12_posc_layout_compiler.py',
              ROOT/'scripts/tsc_revision_build_inputs.py',a.root/'native_preflight_v1.json']
    files += sorted((a.root/'inputs_v1').glob('*'))
    records=[]
    for path in sorted(set(files)):
        assert path.is_file()
        relative=path.relative_to(ROOT)
        snapshot=a.root/'source_snapshot'/relative
        snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,snapshot)
        records.append({'path':relative.as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)})
    record={'schema':'contractkv.independent-structural-survey.freeze.v1',
            'created_UTC':datetime.now(timezone.utc).isoformat(),
            'protocol_path':protocol.relative_to(ROOT).as_posix(),'files':records,
            'selected_sources':125,'eligible_sources':prepared['eligible_sources'],
            'expected_requests_per_repeat':prepared['eligible_sources']*10,
            'expected_repetitions':3,'model_forwards_before_freeze':0,
            'target_old_numeric_values_used_for_tuning':False}
    (a.root/'freeze.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'freeze_sha256':sha(a.root/'freeze.json'),'files':len(records),
                      'expected_business_requests':3*record['expected_requests_per_repeat']}))


if __name__=='__main__':main()
