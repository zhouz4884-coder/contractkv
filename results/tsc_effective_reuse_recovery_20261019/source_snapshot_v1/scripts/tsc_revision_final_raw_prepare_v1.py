"""Freeze Raw-only calibration source, input bindings and the conditional rules."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')


def main(root):
    study=root/'results/tsc_task_faithful_open_arrival_20261018'
    assert not (study/'source_snapshot_v1').exists() and not (study/'raw_calibration_freeze_v1.json').exists()
    assert json.loads((study/'input_selection_complete_v1.json').read_text())['all_source_sets_disjoint']
    inputs=study/'inputs_v1/faithful_selected_sessions_v1.jsonl';samples=[json.loads(x) for x in inputs.read_text(encoding='utf-8').splitlines()]
    assert len(samples)==6
    ids=[x['revision_session_id']+f'-tenant{tenant:02d}' for x in samples for tenant in range(2)]
    waves=[]
    for start in range(0,len(ids),2):
        for turn in range(10):waves.append(dict(cohort_start=start,turn=turn,ready_offset_s=0.,session_ids=ids[start:start+2],wave_index=len(waves)))
    arrival=study/'calibration/arrivals/raw_burst_v1.json'
    write(arrival,dict(schema_version='tsc-r4.fixed-wave-arrivals.v1',sessions_sha256=sha(inputs),tenants_per_template=2,
        concurrency=2,actual_business_requests=120,waves=waves,protocol='all-ready-at-zero Raw-only capacity calibration, not formal SLO service'))
    jobs=[]
    for index,(name,model,lane,wave) in enumerate([
        ('raw_burst_q_gpu0','Qwen3-8B',0,0),('raw_burst_q_gpu1','Qwen3-8B',1,0),
        ('raw_burst_m_gpu0','Mistral-7B-Instruct-v0.3',0,1),('raw_burst_l_gpu1','Llama-3.1-8B-Instruct',1,1)]):
        jobs.append(dict(id=name,model=model,lane=lane,wave=wave,port=9600+index,arrival=arrival.relative_to(study).as_posix(),client_timeout_s=3600))
    protocol=dict(schema_version='contractkv.raw-calibration.v1',generation_protocol='configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json',
        selected_catalog='results/tsc_revision_r4/development_fit_v3/calibration_v1.json',baseline_jobs=jobs,
        maximum_Raw_cells=7,Raw_requests_per_cell=120,maximum_Raw_business_requests=840,
        source_templates=6,tenants_per_template=2,turns=10,client_concurrency=2,max_num_seqs=2,common_window=16384,
        model_parameters_unchanged=True,Raw_only_no_Contract_results=True,
        capacity_rule='Cq=median(two concurrent Qwen burst N/full-wall values); Cm/Cl=their concurrent burst values',
        profile_rule=dict(Qwen_multipliers=[.4,.7,1.05],waves=[2,2,3],GPU_lanes=[0,1,0],ports=[9604,9605,9606]),
        formal_load_rule=dict(common_multiplier=.9,common_capacity='min(Cq,Cm,Cl)',Qwen_high_multiplier=1.05,Qwen_high_capacity='Cq'),
        SLO_rule=dict(TTFT='max across model P95(backend TTFT + controller-to-submit), times1.25 rounded up100ms, min100ms',
            TPOT='max across model P95 TPOT, times1.25 rounded up5ms, min20ms',primary='TTFT and TPOT both meet SLO',
            secondary='TTFT-only goodput; full E2E distribution without extra selected SLO'),
        formal_request_budget=dict(tenants_per_template=6,requests_per_cell=360,maximum_cells=24),
        gate_request_budget=dict(ON_OFF_fresh_pairs=3,maximum_cells=6,requests_per_cell=360,
            peer_regime='isolated same-GPU sequential ON/OFF pairs; not substituted by main colocated ON'),
        arrival_rule='Fixed-seed exponential inter-wave spacings normalized to last offset=(W-1)*2/lambda, horizon=N/lambda; freeze all actual traces before formal Contract outputs',
        no_model_loading_during_either_peer_measurement=True,final_backend_request_drain_inside_clock=True,
        no_heavy_residency_hook=True,measurements_not_pure_GPU_time=True,
        no_extra_load_or_SLO_selection_from_Contract_results=True)
    write(study/'raw_calibration_protocol_v1.json',protocol)
    tracked=subprocess.check_output(['git','ls-files','-z','--','scripts'],cwd=root).decode().split('\x00')
    source_paths={x for x in tracked if x.endswith('.py')}
    source_paths.update(['scripts/tsc_revision_final_raw_prepare_v1.py','scripts/tsc_revision_final_raw_worker_v1.py','scripts/tsc_revision_final_fixed_client_v2.py'])
    snapshot=study/'source_snapshot_v1';snapshot.mkdir()
    assert not (root/'scripts/sitecustomize.py').exists(),'An undeclared root startup hook would undermine the light instrumentation regime'
    source_records=[]
    for rel in sorted(source_paths):
        p=root/rel;target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(p.read_bytes())
        assert sha(target)==sha(p);source_records.append(dict(path=rel,sha256=sha(target)))
    inputs_to_bind=[study/'selection_protocol_v1.json',study/'input_selection_complete_v1.json',
        study/'raw_calibration_protocol_v1.json',arrival,*sorted((study/'inputs_v1').glob('*.json*')),
        root/protocol['generation_protocol'],root/protocol['selected_catalog'],root/'configs/tsc_revision_r3_catalog_v1.json',
        root/'scripts/tsc_revision_final_raw_prepare_v1.py',root/'scripts/tsc_revision_final_raw_worker_v1.py',root/'scripts/tsc_revision_final_fixed_client_v2.py',
        root/'scripts/tsc_tableIII_fullcost_worker_v3.py',root/'scripts/tsc_revision_mechanism_worker_v3.py']
    unique=sorted(set(inputs_to_bind))
    freeze=dict(schema_version='contractkv.raw-calibration-freeze.v1',files=[dict(path=p.relative_to(root).as_posix(),sha256=sha(p)) for p in unique],
        snapshot_files=source_records,parent_runtime_receipt_sha256=sha(root/'results/tsc_revision_mechanism_controls_20261018/preflight_v3/receipt_v1.json'),
        no_model_runtime_or_tokenizer_copy=True,only_small_source_snapshot_created=True,new_GPU_requests=0,
        all_rules_before_new_source_model_outputs=True,entry_point='scripts/tsc_revision_final_raw_worker_v1.py')
    write(study/'raw_calibration_freeze_v1.json',freeze)
    print(json.dumps(dict(freeze_sha256=sha(study/'raw_calibration_freeze_v1.json'),source_files=len(source_records),baseline_cells=4,total_Raw_cells_bound=7,new_GPU_requests=0)))


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
