"""CPU-only audit of prior unique inputs and actual negative coordinates."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():yield json.loads(line)

def main(root,evidence,output):
    old=Path('results/tsc_template_task_serving_20261019')
    assert read(root/old/'formal_local_independent_recompute_v1.json')['status']=='PASS'
    jobs=read(evidence/old/'formal_protocol_v1.json')['jobs']
    cells=[];negative=[]
    with (root/old/'formal_analysis_v1/paired_quality_v1.csv').open(encoding='utf-8',newline='') as f:
        bad=[r for r in csv.DictReader(f) if r['compiled']=='True' and r['score_down']=='True']
    wanted={(r['model'],r['load'],int(r['repeat']),r['policy'],r['source'],int(r['tenant']),int(r['turn'])) for r in bad}
    for job in jobs:
        path=evidence/old/'runs'/job['id']/'attempt1/responses.jsonl'
        business=[r for r in rows(path) if r['row_type']=='business']
        exact=Counter((r['source_group'],r['result']['prompt_ids_sha256']) for r in business)
        cells.append(dict(job=job['id'],business=len(business),unique_actual_inputs=len(exact),
                          within_engine_repeat_histogram=dict(Counter(exact.values())),sha256=sha(path)))
        for r in business:
            key=(job['model'],job['load'],job['repeat'],job['policy'],r['source_group'],r['tenant'],r['turn'])
            if key in wanted:
                negative.append(dict(model=job['model'],policy=job['policy'],repeat=job['repeat'],source=r['source_group'],
                    tenant=r['tenant'],turn=r['turn'],compiled_prompt_ids=r['result']['prompt_token_ids'],
                    output_token_ids=r['result']['output_token_ids'],finish=r['result']['finish_reason'],
                    old_score=r['task_score'],strict_without_Raw_evidence='DENY'))
    assert len(negative)==36
    assert all(c['business']==c['unique_actual_inputs']==384 for c in cells)
    result=dict(status='PASS',new_GPU_requests=0,cells=cells,all_prior_exact_inputs_one_use_per_engine=True,
        unique_bad_coordinates=len({(r['source'],r['tenant'],r['turn']) for r in negative}),
        known_compiled_score_drop_events=len(negative),regression_events=negative,
        result='All old unique inputs require Raw fallback under strict exact scope; across fresh engines is not reuse.',
        source_sha256=sha(Path(__file__)))
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['cells','regression_events']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.evidence,a.output)
