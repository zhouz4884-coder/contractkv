"""Small read-only metric projection for completed Qwen pairs; no online changes."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time

STUDY='results/tsc_task_faithful_open_arrival_20261018'
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main(root,repeat,output):
    assert not output.exists();started=time.perf_counter();study=root/STUDY
    protocol=read(study/'formal_protocol_v1.json');slo=protocol['SLO'];results=[]
    jobs=[j for j in protocol['jobs'] if j['phase']=='qwen' and j['repeat']==repeat];assert len(jobs)==4
    for job in jobs:
        cell=study/'formal/cells'/job['id'];assert read(cell/'completion_v1.json')['status']=='complete'
        summary=read(cell/'summary.json');rows=[];decisions={};hasher=hashlib.sha256()
        with (cell/'raw.jsonl').open('rb') as handle:
            for line in handle:
                hasher.update(line);row=json.loads(line)
                if row['row_type']=='verification':decisions[row['certificate_namespace'],row['query_scope']]=row
                elif row['row_type'] in ('warm','future'):
                    rows.append({k:row[k] for k in ['source_group','family','row_type','effective_level','certificate_namespace','query_scope',
                        'ready_ttft_ms','tpot_ms','metric_join_success','prefix_hit_tokens','new_prefill_tokens','prompt_tokens','finish_reason']})
        assert len(rows)==360 and hasher.hexdigest()==summary['raw_file_sha256']
        assert all(r['metric_join_success'] for r in rows)
        compiled=[r for r in rows if r['effective_level']!='L0'];classes=Counter();compiled_records=[]
        for row in compiled:
            certificate=decisions[row['certificate_namespace'],row['query_scope']];commit=certificate['committed_tokens'];assert commit>0
            kind='full' if row['prefix_hit_tokens']>=commit else 'partial' if row['prefix_hit_tokens'] else 'zero';classes[kind]+=1
            compiled_records.append(dict(source_group=row['source_group'],row_type=row['row_type'],committed_tokens=commit,
                actual_native_prefix_hit_tokens=row['prefix_hit_tokens'],hit_class=kind))
        n=sum(r['ready_ttft_ms']<=slo['TTFT_ms'] and r['tpot_ms']<=slo['TPOT_ms'] for r in rows)
        wall=summary['wall_s_including_all_setup_and_verification']
        results.append(dict(cell=job['id'],load=job['load'],policy=job['policy'],repeat=repeat,business=360,
            wall_s=wall,SLO_compliant=n,absolute_goodput=n/wall,achieved_throughput=360/wall,
            actual_GPU_verification_calls=summary['verification_calls'],complete_controller_work_ms=summary['verification_ms_total'],
            business_logical_new_prefill_tokens=sum(r['new_prefill_tokens'] for r in rows),
            compiled_business=len(compiled),compiled_native_hit_classes=dict(classes),compiled_hit_records=compiled_records,
            length_events=sum(r['finish_reason']=='length' for r in rows)))
    result=dict(schema_version='contractkv.completed-pair-small-metrics.v1',results=results,preliminary_single_repeat=True,
        new_GPU_requests=0,input_data_unchanged=True,elapsed_wall_s=time.perf_counter()-started,
        CPU_priority=os.getpriority(os.PRIO_PROCESS,0) if hasattr(os,'getpriority') else None,
        boundary='Counts on complete paired cells only; not3-repeat confidence or causal attribution. Business logical new-prefill excludes verification and does not measure total GPU work.')
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({**{k:v for k,v in result.items() if k!='results'},'results':[{k:v for k,v in r.items() if k!='compiled_hit_records'} for r in results]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--repeat',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();main(args.root.resolve(),args.repeat,args.output)
