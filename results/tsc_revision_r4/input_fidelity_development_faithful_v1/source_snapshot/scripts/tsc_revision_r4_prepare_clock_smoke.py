"""Prospective old-input burst replay to verify the exogenous readiness clock."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    base=root/'results/tsc_revision_r4/clock_smoke_v1'
    if base.exists():raise ValueError('Preserve smoke version')
    parent=json.loads((root/'results/tsc_revision_r4/development_pilot_v1/freeze.json').read_text(encoding='utf-8'))
    for row in parent['files']:
        if sha(root/row['path'])!=row['sha256']:raise ValueError('Parent frozen bytes changed: '+row['path'])
    source=root/'results/tsc_revision_r4/development_inputs_v1/cold_sessions.jsonl'
    samples=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()][:2]
    if len(samples)!=2 or any(s['revision_family']!='RULER' for s in samples):raise ValueError('Two observed RULER sources expected')
    base.mkdir(parents=True);sessions=base/'sessions.jsonl'
    with sessions.open('x',encoding='utf-8',newline='\n') as out:
        for s in samples:out.write(json.dumps(s,ensure_ascii=False,sort_keys=True)+'\n')
    arrival=base/'arrivals.json'
    trace={'schema_version':'tsc-r4.fixed-wave-arrivals.v1','sessions_sha256':sha(sessions),'tenants_per_template':1,'concurrency':2,
           'actual_business_requests':20,'boundary':'All ten waves arrive at zero; observed inputs only, clock/queue smoke and not efficacy evidence.',
           'waves':[{'wave_index':t,'cohort_start':0,'turn':t,'session_ids':[s['revision_session_id'] for s in samples],'ready_offset_s':0.} for t in range(10)]}
    arrival.write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8')
    config={'schema_version':'tsc-r4.clock-smoke.v1','development_only':True,'models':['qwen'],'policies':['raw-order','risk-tail'],
            'studies':{'single-session':1},'repeats':1,'expected_cells':2,'expected_actual_generations':40,'expected_future_requests':36,
            'input_files':{'single-session':sessions.relative_to(root).as_posix()},'arrival_files':{'single-session':{'1':arrival.relative_to(root).as_posix()}},
            'selected_catalog':'results/tsc_revision_r4/development_fit_v3/calibration_v1.json','previous_catalog':'configs/tsc_revision_r3_catalog_v1.json',
            'generation_protocol':'configs/tsc_revision_r1r_validation_protocol_v1.json','profile':'balanced','clock':'All waves at0, same barrier and all queue/controller costs included.',
            'no_validation_inputs_used':True,'not_efficacy_evidence':True}
    target=root/'configs/tsc_revision_r4_clock_smoke_v1.json'
    with target.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(config,indent=2)+'\n')
    files={r['path'] for r in parent['files']}
    files.update([target.relative_to(root).as_posix(),sessions.relative_to(root).as_posix(),arrival.relative_to(root).as_posix(),
                  'scripts/tsc_revision_r4_prepare_clock_smoke.py','scripts/tsc_revision_r4_live_fixed.py','scripts/tsc_revision_r4_arrival_protocol.py',
                  'scripts/run_tsc_revision_r4_clock_smoke.sh','tests/test_tsc_revision_r4_arrival_protocol.py'])
    print(json.dumps(freeze_scope(root,base,target,files,{'observed_inputs_only':True,'clock_smoke_not_method_validation':True})))


if __name__=='__main__':main()
