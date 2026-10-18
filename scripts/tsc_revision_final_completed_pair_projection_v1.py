"""Low-priority read-only projection of complete paired cells; not final inference."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import time

STUDY='results/tsc_task_faithful_open_arrival_20261018'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def different(a,b):return (a['output_token_ids'],a['finish_reason'])!=(b['output_token_ids'],b['finish_reason'])


def load_cell(cell):
    summary=read(cell/'summary.json');assert read(cell/'completion_v1.json')['status']=='complete'
    business={};witnesses={};decisions=[];plans=[];hasher=hashlib.sha256()
    with (cell/'raw.jsonl').open('rb') as handle:
        for line in handle:
            hasher.update(line);row=json.loads(line);typ=row['row_type']
            if typ in ('warm','future'):
                key=row['source_group'],row['session_id'],row['turn_id'];assert key not in business
                keep={k:row[k] for k in ('row_type','source_group','family','session_id','turn_id','effective_level','task_score',
                    'output_token_ids','finish_reason','prompt_ids_sha256','certificate_namespace','query_scope')}
                business[key]=keep
                if row['scope_first_raw_business']:witnesses.setdefault((row['certificate_namespace'],row['query_scope']),keep)
            elif typ=='verification':decisions.append(row)
            elif typ=='prospective_plan':plans.append({k:v for k,v in row.items() if k not in ('plan','scope_case')})
    assert len(business)==360 and hasher.hexdigest()==summary['raw_file_sha256']
    return dict(summary=summary,business=business,witnesses=witnesses,decisions=decisions,plans=plans)


def main(root,repeat,output):
    assert not output.exists();start=time.perf_counter();study=root/STUDY
    protocol=read(study/'formal_protocol_v1.json')
    jobs=[j for j in protocol['jobs'] if j['phase']=='qwen' and j['repeat']==repeat];assert len(jobs)==4
    loaded={j['id']:load_cell(study/'formal/cells'/j['id']) for j in jobs};comparisons=[]
    for load in ('common','high'):
        pair=[j for j in jobs if j['load']==load]
        one=loaded[next(j['id'] for j in pair if j['policy']=='raw-order')]
        two=loaded[next(j['id'] for j in pair if j['policy']=='risk-tail')]
        assert one['business'].keys()==two['business'].keys()
        rows=[]
        for key,row in two['business'].items():
            raw=one['business'][key];compiled=row['effective_level']!='L0';scope=row['certificate_namespace'],row['query_scope']
            if not compiled:assert raw['prompt_ids_sha256']==row['prompt_ids_sha256']
            delta=row['task_score']-raw['task_score']
            rows.append(dict(source_group=row['source_group'],family=row['family'],session_id=row['session_id'],turn=row['turn_id'],
                row_type=row['row_type'],compiled=compiled,raw_score=raw['task_score'],contract_score=row['task_score'],score_delta=delta,
                material_down=delta<-.03,material_up=delta>.03,ID_or_finish_change=different(raw,row),
                change_from_actual_witness=different(two['witnesses'][scope],row) if compiled else None,
                raw_output_token_ids=raw['output_token_ids'],contract_output_token_ids=row['output_token_ids'],
                raw_finish=raw['finish_reason'],contract_finish=row['finish_reason']))
        by_source=[]
        for source in sorted({r['source_group'] for r in rows}):
            group=[r for r in rows if r['source_group']==source]
            by_source.append(dict(source_group=source,family=group[0]['family'],business=len(group),
                compiled_business=sum(r['compiled'] for r in group),compiled_futures=sum(r['compiled'] and r['row_type']=='future' for r in group),
                material_down=sum(r['material_down'] for r in group),material_up=sum(r['material_up'] for r in group)))
        reasons=Counter('PASS' if d['certificate_issued'] else d['failure_reason'] for d in two['decisions'])
        comparisons.append(dict(load=load,repeat=repeat,raw_wall_s=one['summary']['wall_s_including_all_setup_and_verification'],
            contract_wall_s=two['summary']['wall_s_including_all_setup_and_verification'],
            all_business_pairs=len(rows),future_pairs=sum(r['row_type']=='future' for r in rows),
            compiled_business=sum(r['compiled'] for r in rows),compiled_future=sum(r['compiled'] and r['row_type']=='future' for r in rows),
            compiled_ID_or_finish_changes=sum(r['compiled'] and r['ID_or_finish_change'] for r in rows),
            compiled_changes_from_witness=sum(r['change_from_actual_witness'] is True for r in rows),
            all_material_up=sum(r['material_up'] for r in rows),all_material_down=sum(r['material_down'] for r in rows),
            qualification_reasons=dict(reasons),per_source=by_source,actual_decisions=two['decisions'],plans=two['plans'],pairs=rows))
    result=dict(schema_version='contractkv.complete-pair-readonly-projection.v1',preliminary_single_repeat=True,
        comparisons=comparisons,new_GPU_requests=0,input_logs_unchanged=True,elapsed_wall_s=time.perf_counter()-start,
        low_CPU_priority=os.getpriority(os.PRIO_PROCESS,0) if hasattr(os,'getpriority') else None,
        not_final_three_repeat_effect_or_confidence_interval=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({**{k:v for k,v in result.items() if k!='comparisons'},'comparisons':[{k:v for k,v in c.items() if k not in ('actual_decisions','plans','pairs')} for c in comparisons]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--repeat',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();main(args.root.resolve(),args.repeat,args.output)
