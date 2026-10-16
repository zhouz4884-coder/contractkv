"""Source-order-only fanout subset; no model outputs or test-score selection."""
import argparse
import hashlib
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--input-sha256',required=True);a=p.parse_args()
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(a.input)!=a.input_sha256:raise ValueError('Frozen independent sources changed')
    if a.output.exists():raise RuntimeError('Preserve existing fanout subset')
    samples=[json.loads(x) for x in a.input.read_text(encoding='utf-8').splitlines()];selected=[];counts={}
    for sample in samples:
        family=sample['revision_family']
        if counts.get(family,0)<2:selected.append(sample);counts[family]=counts.get(family,0)+1
    if len(samples)!=50 or len(selected)!=10 or set(counts.values())!={2}:raise ValueError('Five-family fixed source coverage')
    a.output.write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in selected),encoding='utf-8')
    a.output.with_suffix('.commitment.json').write_text(json.dumps({'schema_version':'tsc-r2.source-order-fanout.v1','input_sha256':sha(a.input),'output_sha256':sha(a.output),'selection':'First two sources per family in frozen source order; model outcomes unavailable','sources':[s['revision_source_group'] for s in selected],'families':counts},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sources':len(selected),'sha256':sha(a.output),'no_test_generation_or_outcome_used':True}))

if __name__=='__main__':main()
