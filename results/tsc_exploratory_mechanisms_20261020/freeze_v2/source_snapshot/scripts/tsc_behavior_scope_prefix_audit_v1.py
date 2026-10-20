"""Post-hoc audit: object count, actual stable-prefix IDs, and text invariants."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_template_task_protocol_v2 import prepared
from scripts.tsc_revision_r4_fidelity_adapter_v2 import ordered_text_preserving_segments
from scripts.phase17_live_common import digest

def lines(p):
    with p.open(encoding='utf-8') as f:
        for s in f:
            if s.strip():yield json.loads(s)
def main(root,evidence,output):
    old=Path('results/tsc_template_task_serving_20261019');study=evidence/old
    protocol=json.loads((study/'formal_protocol_v1.json').read_text(encoding='utf-8'))
    samples=list(lines(study/'inputs_validation_v2/sessions_v2.jsonl'));text=[]
    for sample in samples:
        prefixes=set();full=set()
        for tenant in range(8):
            for turn in range(9):
                case,order,messages=prepared(sample,tenant,turn,'L3');stable=[];byid={s['segment_id']:s for s in case['segments']}
                for sid in order:
                    if byid[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}:break
                    stable.append(sid)
                prefixes.add(digest(ordered_text_preserving_segments(stable,case['segments'])))
                full.add(digest(messages))
        assert len(prefixes)==1 and len(full)==72
        text.append(dict(source=sample['revision_source_group'],distinct_stable_text=1,distinct_full_L3_messages=72))
    groups=defaultdict(lambda:dict(objects=0,canonical=set(),RPCs=0));actual=Counter()
    for job in protocol['jobs']:
        records=list(lines(study/'runs'/job['id']/'attempt1/responses.jsonl'))
        regs={r['object_id']:r for r in records if r['row_type']=='registration'}
        for reg in regs.values():
            value=groups[job['model'],job['load'],job['policy']];value['objects']+=1
            value['canonical'].add(reg['plan']['prompt_ids_sha256']);value['RPCs']+=len(reg['certificate']['attempts'])
        for r in records:
            if r['row_type']=='business' and r['compiled']:
                cert=regs[r['certificate_object']]['certificate'];ids=r['result']['prompt_token_ids']
                end=cert['stable_prefix_tokens'];commit=cert['committed_tokens']
                actual['compiled_requests']+=1
                match=digest(ids[:end])==cert['stable_prefix_hash'] and commit%16==0 and 0<commit<=end<len(ids)
                actual['actual_full_stable_prefix_matches_saved_certificate' if match else 'prefix_mismatch']+=1
    summary=[dict(model=k[0],load=k[1],policy=k[2],objects_across_repeats=v['objects'],
                  distinct_canonical_prompt_hashes=len(v['canonical']),actual_RPCs=v['RPCs']) for k,v in groups.items()]
    assert actual['compiled_requests']==actual['actual_full_stable_prefix_matches_saved_certificate']==3456
    result=dict(status='PASS',text_invariants=text,registration_granularity=summary,actual_token_ID_prefix_audit=dict(actual),
        old_inband_actual_prefix_hash_enforced=False,new_GPU_requests=0,
        conclusion='Shared stable prefix is valid; registration objects are not unique prompts. This post-hoc identity result is distinct from in-band enforcement and Raw generation equivalence.',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','actual':dict(actual),'objects':summary}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.evidence,a.output)
