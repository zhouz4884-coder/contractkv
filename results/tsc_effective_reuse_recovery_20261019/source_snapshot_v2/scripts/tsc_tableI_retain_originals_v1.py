"""Retain label-free original selected inputs without reselecting/repacking."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.tsc_revision_build_inputs import source,family
from scripts.tsc_tableI_survey_common_v1 import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True)
    a=p.parse_args();meta=json.loads((a.inputs/'input_preparation_v1.json').read_text())
    pool=ROOT/'results/workload/phase14d_full_pool_v2.jsonl'
    assert hashlib.sha256(pool.read_bytes()).hexdigest()==meta['source_pool_sha256']
    selected=[json.loads(l) for l in (a.inputs/'selected_packed_sources_v1.jsonl').open() if l.strip()]
    original={}
    for line in pool.open(encoding='utf-8'):
        r=json.loads(line);original.setdefault(source(r),r)
    output=[]
    for r in selected:
        v=original[r['source_group']]
        sample={'family':family(v),'source_group':source(v),'source_dataset':v['dataset'],
                'source_task':v['task'],'sample_id':str(v['sample_id']),
                'segments':[{'type':s['type'],'text':s['text']} for s in v['segments']]}
        assert digest(sample['segments'])==r['source_segments_sha256']
        output.append(sample)
    path=a.inputs/'selected_original_sources_v1.jsonl'
    with path.open('x',encoding='utf-8') as f:
        f.write(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in output))
    report={'sources':len(output),'originals_match_preparation_source_hashes':True,
            'selected_packed_inputs_changed':False,'labels_included':False,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'new_model_forwards':0}
    (a.inputs/'original_source_retention_v1.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
