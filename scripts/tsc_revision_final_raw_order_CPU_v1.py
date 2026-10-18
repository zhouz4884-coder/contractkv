"""Extract five-family order from saved real survey requests, without inference."""
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(8<<20),b''):value.update(block)
    return value.hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def collapse(values):
    output=[]
    for value in values:
        if not output or value!=output[-1]:output.append(value)
    return ' > '.join(output)


def main(root,output):
    assert not output.exists(),'Preserve all CPU audit outputs'
    study=root/'results/tsc_tableI_remeasurement_20261018';freeze=read(study/'freeze.json')
    frozen={r['path']:r['sha256'] for r in freeze['files']}
    inputs=study/'inputs_v1/selected_original_sources_v1.jsonl'
    assert sha(inputs)==frozen[inputs.relative_to(root).as_posix()]
    originals=[json.loads(x) for x in inputs.read_text(encoding='utf-8').splitlines()];assert len(originals)==125
    stored=defaultdict(Counter)
    for sample in originals:stored[sample['family']][collapse(s['type'] for s in sample['segments'])]+=1
    requests=[];files=[];patterns=defaultdict(Counter);mutables=defaultdict(Counter)
    stable_after=defaultdict(int);actual_histories=defaultdict(Counter)
    for repeat in (1,2,3):
        cell=study/'cells'/f'raw_native_r{repeat}';completion=read(cell/'completion_v1.json');path=cell/'raw.jsonl.gz'
        assert completion['raw_sha256']==sha(path) and completion['completed_requests']==1250
        files.append(dict(path=path.relative_to(root).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
        with gzip.open(path,'rt',encoding='utf-8') as handle:
            count=0
            for line in handle:
                row=json.loads(line)
                if row['row_type']!='request':continue
                assert row['success'] and row['actual_prompt_token_ids_verified'];count+=1
                messages=row['messages'];spans=row['character_spans'];turn=row['turn'];family=row['family']
                assert messages[0]['role']=='system' and messages[-1]['role']=='user'
                assert len(messages)==2+2*turn
                assert [x['role'] for x in messages[1:-1]]==['user','assistant']*turn
                assert spans==sorted(spans,key=lambda x:x['start'])
                assert all(a['end']<=b['start'] for a,b in zip(spans,spans[1:]))
                pattern=collapse(x['segment_type'] for x in spans)
                mutable=next(x for x in spans if x['category'] in ('query','history'))
                after=sum(x['category']=='stable' and x['start']>=mutable['end'] for x in spans)
                cohort='warm' if turn==0 else 'future'
                patterns[family,cohort][pattern]+=1;mutables[family,cohort][mutable['segment_type']]+=1
                stable_after[family,cohort]+=bool(after);actual_histories[family,cohort][len(messages)-2]+=1
                requests.append(dict(repeat=repeat,family=family,source_group=row['source_group'],turn=turn,cohort=cohort,
                    actual_message_roles=' > '.join(m['role'] for m in messages),
                    collapsed_actual_segment_order=pattern,history_message_count=len(messages)-2,
                    first_declared_mutable_type=mutable['segment_type'],first_declared_mutable_character_start=mutable['start'],
                    stable_body_spans_after_first_declared_mutable=after,actual_native_cached_tokens=row['native_cached_tokens'],
                    prompt_tokens=row['prompt_tokens']))
        assert count==1250
    assert len(requests)==3750 and sum(r['cohort']=='future' for r in requests)==3375
    summary=[]
    for family in ('RULER','HotpotQA','NarrativeQA','Qasper','RepoBench'):
        for cohort in ('warm','future'):
            k=family,cohort;n=sum(patterns[k].values());assert n==(75 if cohort=='warm' else 675)
            summary.append(dict(family=family,cohort=cohort,requests=n,actual_order_patterns=dict(patterns[k]),
                first_declared_mutable_type_counts=dict(mutables[k]),requests_with_later_stable_body=stable_after[k],
                history_message_counts={str(n):count for n,count in sorted(actual_histories[k].items())}))
    output.mkdir(parents=True)
    with (output/'actual_request_orders_v1.csv').open('x',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(requests[0]));writer.writeheader();writer.writerows(requests)
    result=dict(schema_version='contractkv.five-family-actual-order-CPU.v1',requests=len(requests),future_requests=3375,
        families=summary,stored_source_segment_order_patterns={family:dict(patterns) for family,patterns in stored.items()},
        actual_Raw_files=files,source_freeze_sha256=sha(study/'freeze.json'),entry_sha256=sha(Path(__file__)),new_GPU_requests=0,
        actual_saved_character_spans_not_retokenized_inference=True,
        boundary='Independent Oct18 five-family structural survey, not recovered July TableI order or a production frequency survey. Declared mutable location is not a claim that every history byte changes at every turn.')
    with (output/'summary_v1.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('actual_Raw_files',)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output)
