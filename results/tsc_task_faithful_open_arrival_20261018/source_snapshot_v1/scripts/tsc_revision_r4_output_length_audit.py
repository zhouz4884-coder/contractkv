"""Report measured decode demand, including first raw business requests."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Preserve output-length audit version')
 cells=[];groups=defaultdict(list)
 for file in sorted((a.root/'cells').glob('*/summary.json')):
  summary=json.loads(file.read_text(encoding='utf-8'));raw=file.with_name('raw.jsonl')
  if not summary['execution_complete'] or sha(raw)!=summary['raw_file_sha256']:raise ValueError('Incomplete/changed cell')
  rows=[r for r in read(raw) if r['row_type'] in ('warm','future')]
  if any(len(r['output_token_ids'])!=r['completion_tokens'] for r in rows):raise ValueError('Actual output ID/usage mismatch')
  record={'cell':file.parent.name,'study':summary['study'],'model':rows[0]['model'],'policy':summary['policy'],'repeat':summary['repeat'],
          'business_requests':len(rows),'actual_all_business_output_tokens':sum(len(r['output_token_ids']) for r in rows),
          'actual_warm_output_tokens':sum(len(r['output_token_ids']) for r in rows if r['row_type']=='warm'),
          'actual_future_output_tokens':sum(len(r['output_token_ids']) for r in rows if r['row_type']=='future'),'raw_sha256':sha(raw)}
  cells.append(record);groups[record['study'],record['model'],record['policy']].append(record)
 comparison=[]
 for (study,model,policy),rows in groups.items():
  if policy=='raw-order':continue
  refs={r['repeat']:r for r in groups[study,model,'raw-order']}
  if any(r['repeat'] not in refs for r in rows):raise ValueError('Missing paired raw')
  rawtokens=sum(refs[r['repeat']]['actual_all_business_output_tokens'] for r in rows);poltokens=sum(r['actual_all_business_output_tokens'] for r in rows)
  comparison.append({'study':study,'model':model,'policy':policy,'paired_repeats':len(rows),'raw_all_business_output_tokens':rawtokens,
                     'policy_all_business_output_tokens':poltokens,'policy_minus_raw_tokens':poltokens-rawtokens,
                     'policy_to_raw_decode_token_ratio':poltokens/rawtokens})
 result={'schema_version':'tsc-r4.output-length-audit.v1','cells':cells,'comparison':comparison,'includes_initial_raw_and_all_future_requests':True,
         'served_outputs_or_budgets_changed':False,'is_a_causal_prefill_speedup_decomposition':False,'analysis_source_sha256':sha(Path(__file__))}
 a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'comparisons':comparison}))

if __name__=='__main__':main()
