"""Check old cohort membership and archived rendering, without GPU inference."""
from pathlib import Path
import hashlib, json, sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'

def load(p):return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    protocol=json.loads((OUT/'protocol_v1.json').read_text(encoding='utf-8'))
    for record in protocol['archived_source_files']+protocol['input_files']:
        assert sha(ROOT/record['path'])==record['sha256'],record['path']
    sys.path.insert(0,str(OUT/'source_snapshot'))
    from scripts.phase19b_end_to_end_live import messages,turn_case
    records=[]
    historic=ROOT/'results/tsc_revision_evidence_closure_20261017/original_tableIII'
    for row in protocol['models']:
        samples=load(OUT/'inputs'/row['session_file']);ids={s['phase19b_session_id'] for s in samples}
        assert len(ids)==row['sessions']
        if row['key'] in ['qwen','mistral']:
            old=historic/f"results/submission_repeats/{row['key']}/repeat1/raw-order.jsonl"
        elif row['key']=='qwen14':old=historic/'results/scale_up/qwen3_14b_tp2_v0/r1/r1-raw.jsonl'
        else:old=ROOT/'results/cross_model/llama_broad_generalization_r3/repeat1/r1-raw.jsonl'
        oldrows=[r for r in load(old) if r.get('row_type')=='future']
        assert {(r['session_id'],r['turn_id']) for r in oldrows}=={(sid,t) for sid in ids for t in range(1,10)}
        hashes=[]
        for sample in samples:
            for turn in range(10):
                first=turn_case(sample,turn,row['stable_word_limit'])
                second=turn_case(sample,turn,row['stable_word_limit'])
                assert first==second
                order=[s['segment_id'] for s in first['segments']]
                text=json.dumps(messages(first,order),ensure_ascii=True,sort_keys=True).encode()
                hashes.append(hashlib.sha256(text).hexdigest())
        records.append({'model':row['model'],'registered_sessions':len(ids),'original_future_keys_matched':len(oldrows),
            'archived_raw_renders_checked':len(hashes),'render_sha256':hashlib.sha256('\n'.join(hashes).encode()).hexdigest(),
            'historical_prompt_ID_identity_established':False,
            'limitation':'Archived renderer and cohort verified; old full prompt IDs are unavailable, so tokenizer/service equality still needs actual replay input checks.'})
    record={'status':'PASS','models':records,'source_files_hashed':len(protocol['archived_source_files']),
        'new_GPU_requests':0,'no_new_certification_threshold_or_source_selection':True,
        'runtime_preflight_and_GPU_measurement_complete':False}
    (OUT/'frozen_cohort_CPU_check_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    paths=[OUT/'protocol_v1.json',OUT/'instrumentation_CPU_check_v1.json',OUT/'frozen_cohort_CPU_check_v1.json']
    paths+=[ROOT/'scripts'/name for name in ['tsc_tableIII_instrument_frozen_client_v1.py','tsc_tableIII_timing_instrumentation_check_v1.py','tsc_tableIII_prepare_fullcost_replay_v1.py','tsc_tableIII_check_frozen_replay_v1.py']]
    freeze={'schema_version':'contractkv.original-sample-fullcost-freeze.v1','before_GPU_measurement':True,
            'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in paths]}
    freeze_path=OUT/'freeze_v1.json'
    if freeze_path.exists():assert json.loads(freeze_path.read_text(encoding='utf-8'))==freeze
    else:freeze_path.write_text(json.dumps(freeze,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','old_cohort_future_keys':sum(r['original_future_keys_matched'] for r in records),
                      'raw_renders':sum(r['archived_raw_renders_checked'] for r in records),'GPU_measured':False}))

if __name__=='__main__':main()
