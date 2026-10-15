"""Observed business decode and registration-stage clocks; never additive GPU time."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); groups=defaultdict(lambda:{'future':[],'verification':[]})
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        rows=read(path.parent/'raw.jsonl'); first=next(r for r in rows if r['row_type']=='future')
        for row in rows:
            if row['row_type'] not in ('future','verification'): continue
            for family in ('ALL',row['family']):
                groups[(first['study'],first['model'],first['policy'],family)][row['row_type']].append(row)
    result=[]
    for key,group in sorted(groups.items()):
        future=group['future']; registrations=group['verification']
        if not future: continue
        endpoint=sum(attempt['verification_ms'] for row in registrations for attempt in row['attempts'])
        complete=sum(row['complete_verification_ms'] for row in registrations)
        result.append({'study':key[0],'model':key[1],'policy':key[2],'family':key[3],'future_requests':len(future),
                       'mean_request_latency_ms':statistics.fmean(r['latency_ms'] for r in future),
                       'mean_backend_ttft_ms':statistics.fmean(r['ttft_ms'] for r in future),
                       'mean_after_first_token_ms':statistics.fmean(max(0,r['latency_ms']-r['ttft_ms']) for r in future),
                       'mean_completion_tokens':statistics.fmean(r['completion_tokens'] for r in future),
                       'registration_scopes':len(registrations),'verifier_http_calls':sum(len(r['attempts']) for r in registrations),
                       'summed_complete_registration_ms':complete,'summed_verifier_http_ms':endpoint,
                       'summed_other_registration_ms':max(0,complete-endpoint),
                       'other_registration_ms_per_scope':max(0,complete-endpoint)/len(registrations) if registrations else 0})
    a.output.mkdir(parents=True,exist_ok=True); write(a.output/'observed_cost_stages_v1.csv',result)
    note={'source':'actual client counters and registration records','complete_includes_failed_attempts':True,
          'other_registration':'Difference within each sequential registration: rendering/tokenization/HTTP preparation/control overhead; not a pure CPU or kernel profiler measurement',
          'after_first_token':'Observed response duration after first content token, not a hardware decode-only timer',
          'no_addition_to_measured_wall':'Parallel registration calls and business waves prevent treating these sums as additive end-to-end time',
          'per_family_wall_or_goodput_not_inferred':True}
    (a.output/'observed_cost_stages_manifest_v1.json').write_text(json.dumps(note,indent=2)+'\n'); print(json.dumps(note))


if __name__=='__main__': main()
