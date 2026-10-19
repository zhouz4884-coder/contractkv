"""Describe the worst readiness requests without changing admission or scoring."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write
from scripts.tsc_revision_live import FROZEN_LEVELS

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    tails=[];summary=[];inputs=[]
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        closed=json.loads(path.read_text(encoding='utf-8'));raw=path.parent/'raw.jsonl';sha=hashlib.sha256(raw.read_bytes()).hexdigest()
        if not closed['execution_complete'] or closed['raw_file_sha256']!=sha:raise ValueError('Incomplete/modified source cell')
        rows=[r for r in read(raw) if r['row_type']=='future'];count=math.ceil(len(rows)*.01)
        selected=sorted(rows,key=lambda r:r['ready_ttft_ms'],reverse=True)[:count]
        inputs.append({'cell':path.parent.name,'raw_sha256':sha})
        for index,row in enumerate(selected,1):
            tails.append({'cell':path.parent.name,'study':row['study'],'model':row['model'],'policy':row['policy'],'rank':index,
              'family':row['family'],'effective_level':row['effective_level'],'source_group':row['source_group'],
              'request_id':row['request_id'],'ready_ttft_ms':row['ready_ttft_ms'],'backend_RPC_ttft_ms':row['ttft_ms'],
              'extra_before_RPC_ms':row['ready_ttft_ms']-row['ttft_ms'],
              'inherited_family_L0':FROZEN_LEVELS[row['model']][row['family']]=='L0'})
        summary.append({'cell':path.parent.name,'top_rank_count':count,'future_count':len(rows),'families':dict(Counter(r['family'] for r in selected)),
            'raw_route_tail_requests':sum(r['effective_level']=='L0' for r in selected),
            'inherited_L0_tail_requests':sum(FROZEN_LEVELS[r['model']][r['family']]=='L0' for r in selected),
            'mean_extra_before_RPC_ms':statistics.fmean(r['ready_ttft_ms']-r['ttft_ms'] for r in selected)})
    a.output.mkdir(parents=True,exist_ok=True)
    write(a.output/'tail_requests_v1.csv',tails)
    result={'schema_version':'tsc-r2.descriptive-tail-attribution.v1','source_cells':inputs,'top_fraction':.01,
      'selection':'Worst ceil(1% * actual futures) by observed readiness TTFT; descriptive, no rows removed from primary metrics',
      'extra_before_RPC_is_controller_wave_wait_and_client_preparation_not_a_separate_GPU_timer':True,
      'summary':summary,'no_causal_claim_from_attribution_alone':True}
    (a.output/'tail_attribution_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([r for r in summary if 'template-fanout' in r['cell'] and 'margin-benefit' in r['cell']]))

if __name__=='__main__':main()
