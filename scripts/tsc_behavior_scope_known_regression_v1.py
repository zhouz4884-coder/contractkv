"""Offline admission regression using the original 36 actual negative pairs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

def rows(p):
    with p.open(encoding='utf-8') as f:
        for s in f:
            if s.strip():yield json.loads(s)
def main(workspace,evidence,output):
    old=Path('results/tsc_template_task_serving_20261019')
    with (workspace/old/'formal_analysis_v1/paired_quality_v1.csv').open(encoding='utf-8',newline='') as f:
        negative=[r for r in csv.DictReader(f) if r['compiled']=='True' and r['score_down']=='True']
    jobs=json.loads((evidence/old/'formal_protocol_v1.json').read_text())['jobs'];needed={}
    for r in negative:
        for policy in ['Raw-authorized',r['policy']]:
            needed.setdefault((r['model'],r['load'],int(r['repeat']),policy),set()).add((r['source'],int(r['tenant']),int(r['turn'])))
    data={}
    for job in jobs:
        key=(job['model'],job['load'],job['repeat'],job['policy'])
        if key not in needed:continue
        for row in rows(evidence/old/'runs'/job['id']/'attempt1/responses.jsonl'):
            if row['row_type']=='business' and (row['source_group'],row['tenant'],row['turn']) in needed[key]:
                data[key+(row['source_group'],row['tenant'],row['turn'])]=row
    result=[]
    for r in negative:
        common=(r['model'],r['load'],int(r['repeat']));coordinate=(r['source'],int(r['tenant']),int(r['turn']))
        raw=data[common+('Raw-authorized',)+coordinate];compiled=data[common+(r['policy'],)+coordinate]
        ids1=raw['result']['output_token_ids'];ids2=compiled['result']['output_token_ids']
        assert ids1!=ids2 and float(r['delta'])<-.03
        result.append(dict(model=r['model'],repeat=r['repeat'],policy=r['policy'],source=r['source'],tenant=int(r['tenant']),turn=int(r['turn']),
            actual_Raw_prompt_ids_sha256=raw['result']['prompt_ids_sha256'],actual_compiled_prompt_ids_sha256=compiled['result']['prompt_ids_sha256'],
            actual_Raw_output_ids=ids1,actual_compiled_output_ids=ids2,Raw_score=raw['task_score'],compiled_score=compiled['task_score'],
            would_be_rejected_by_exact_free_generation_comparison=True,old_deployment_record_is_not_Raw_evidence=True))
    assert len(result)==36 and len({(r['source'],r['tenant'],r['turn']) for r in result})==6
    out=dict(status='PASS',events=36,distinct_conditions=6,actual_existing_output_mismatches_rejected=36,rows=result,new_GPU_requests=0,
        boundary='CPU replay of admission predicates on old actual pairs. Does not predict what a fresh GPU execution of doc107 will generate.',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.workspace,a.evidence,a.output)
