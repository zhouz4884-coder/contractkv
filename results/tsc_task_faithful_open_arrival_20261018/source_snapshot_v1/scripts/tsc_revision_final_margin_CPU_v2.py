"""Two-floor offline sensitivity and byte-verified historical scope counterexample.

Reuses the already declared fixed grid; never selects new admission thresholds.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

GRID=(0.,.03125,.0625,.125,.25,.5,1.)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def csvrows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def finite(x):
    try:
        z=float(x);return z if math.isfinite(z) else None
    except (ValueError,TypeError):return None
def rows(p):
    with p.open(encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]


def main(root,output):
    if output.exists():raise FileExistsError(output)
    base=root/'results/tsc_final_existing_evidence_CPU_20261018'
    margin_path=base/'analysis_v1/margin_observed_RPCs_v1.csv';measured=csvrows(margin_path)
    inputs={margin_path.relative_to(root).as_posix():sha(margin_path)}
    previous=read(base/'analysis_v1/completion_v1.json');assert list(GRID)==previous['post_hoc_grid']
    for row in measured:
        row['model']=row['cell'].split('_')[1]
        for k in ('raw_margin_min','candidate_margin_min','terminal_stop_margin'):row[k]=finite(row[k])
        row['originally_issued']=row['observed_issued']=='True'
    grid=[]
    for model in sorted({x['model'] for x in measured}):
        group=[x for x in measured if x['model']==model]
        complete=[x for x in group if all(x[k] is not None for k in ('raw_margin_min','candidate_margin_min','terminal_stop_margin'))]
        for raw_floor in GRID:
            for candidate_floor in GRID:
                passing=[x for x in complete if x['raw_margin_min']>=raw_floor and min(x['candidate_margin_min'],x['terminal_stop_margin'])>=candidate_floor]
                grid.append(dict(model=model,raw_floor=raw_floor,candidate_and_EOS_floor=candidate_floor,
                    frozen_two_floor_baseline=raw_floor==.0625 and candidate_floor==.125,
                    measured_RPCs=len(group),complete_margin_responses=len(complete),
                    originally_issued_among_complete=sum(x['originally_issued'] for x in complete),
                    margin_predicate_PASS=len(passing),originally_issued_still_margin_PASS=sum(x['originally_issued'] for x in passing),
                    originally_issued_no_longer_margin_PASS=sum(x['originally_issued'] for x in complete)-sum(x['originally_issued'] for x in passing),
                    originally_not_issued_but_margin_PASS=sum(not x['originally_issued'] for x in passing),
                    boundary='Measured-response sensitivity only; not full qualification coverage or new future generation.'))

    review_path=root/'results/tsc_revision_r3/failure_review_v1.json';review=read(review_path)
    inputs[review_path.relative_to(root).as_posix()]=sha(review_path)
    assert review['compiled_material_pairs']==3 and review['distinct_model_source_query_units']==1
    old=root/'results/tsc_revision_r3/validation_v1';archive_inventory={x['path']:x['sha256'] for x in csvrows(old/'raw_evidence_inventory_v1.csv')}
    known=[]
    for case in review['reviewed']:
        repeat=int(case['pair']['repeat']);sid=case['pair']['session_id'];scope=case['query_scope']
        policy=old/'cells'/f'single-session_qwen_margin-benefit_r{repeat}'/'raw.jsonl'
        raw=old/'cells'/f'single-session_qwen_raw-order_r{repeat}'/'raw.jsonl'
        for p,expected in [(policy,case['policy_raw_sha256']),(raw,case['baseline_raw_sha256'])]:
            digest=sha(p);assert digest==expected==archive_inventory[p.relative_to(root).as_posix()]
            inputs[p.relative_to(root).as_posix()]=digest
        rr=rows(raw);pp=rows(policy)
        future=next(x for x in pp if x.get('row_type')=='future' and x['session_id']==sid and x['turn_id']==7)
        witness=next(x for x in pp if x.get('row_type')=='future' and x['session_id']==sid and x['turn_id']==1)
        reference=next(x for x in rr if x.get('row_type')=='future' and x['session_id']==sid and x['turn_id']==1)
        raw_future=next(x for x in rr if x.get('row_type')=='future' and x['session_id']==sid and x['turn_id']==7)
        certificate=next(x for x in pp if x.get('row_type')=='verification' and x.get('query_scope')==scope and x.get('certificate_issued'))
        assert future['output_token_ids']==witness['output_token_ids']==reference['output_token_ids']
        assert future['output_token_ids']!=raw_future['output_token_ids']
        assert witness['prompt_token_ids']==reference['prompt_token_ids']
        a,b=reference['prompt_token_ids'],raw_future['prompt_token_ids']
        assert len(a)==len(b)==2803
        changed_positions=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        assert len(changed_positions)==1
        raw_margin=min(witness['reference_margins']);cand=float(certificate['candidate_margin_min']);stop=float(certificate['terminal_stop_margin'])
        assert abs(raw_margin-case['raw_full_margin_min'])<1e-6 and cand==case['candidate_margin_min']==.40625
        delta=float(future['task_score'])-float(raw_future['task_score']);assert delta<-.03
        known.append(dict(source=case['pair']['source_group'],repeat=repeat,scope=scope,
            raw_reference_margin_min=raw_margin,candidate_margin_min=cand,candidate_stop_margin=stop,
            raw_reference_prompt_tokens=len(a),raw_future_prompt_tokens=len(b),changed_raw_prompt_positions=changed_positions,
            compiled_future_equals_witness_IDs=True,compiled_future_equals_raw_future_IDs=False,
            raw_future_score=raw_future['task_score'],compiled_future_score=future['task_score'],score_delta=delta,
            witness_request_id=witness['request_id'],compiled_future_request_id=future['request_id'],raw_future_request_id=raw_future['request_id'],
            two_floor_predicate_current_PASS=raw_margin>=.0625 and min(cand,stop)>=.125,
            candidate_floor_point25_with_raw_point0625_PASS=raw_margin>=.0625 and min(cand,stop)>=.25))
    output.mkdir(parents=True)
    with (output/'two_floor_margin_grid_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(grid[0]));w.writeheader();w.writerows(grid)
    for name,value in [('historical_point40625_counterexample_v1.json',known),('input_inventory_v1.json',inputs)]:
        with (output/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    result=dict(status='offline_two_floor_and_historical_ID_audit_complete',new_GPU_requests=0,
        measured_responses=len(measured),grid=list(GRID),two_floor_rows=len(grid),
        historical_counterexample_repeats=len(known),historical_distinct_sources=1,
        current_floors_still_admit_all_known_witnesses=all(x['two_floor_predicate_current_PASS'] for x in known),
        candidate_point25_still_admits_all_known_witnesses=all(x['candidate_floor_point25_with_raw_point0625_PASS'] for x in known),
        known_future_raw_differences_are_outside_same_observation_witness=True,
        source_sha256=sha(Path(__file__)),thresholds_selected=False,
        boundaries=['No unexecuted candidate or missing margin is imputed; this is measured-response coverage, not all-request coverage.',
            'The historical .40625 case is separated from the later diagnostic .34375, not relabeled as one measurement.',
            'The three historical repeats share one source and query; they are not three independent sources.',
            'Margin evidence on one witness cannot establish future behavior under a changed raw prompt. Scope constraints remain necessary.',
            'No new GPU certification, future quality guarantee, queueing latency or full-wall performance is inferred from this grid.'])
    with (output/'completion_v1.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
