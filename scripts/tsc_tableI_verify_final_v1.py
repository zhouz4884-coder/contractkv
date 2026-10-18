"""Validate retained histories/static content and an offline prefix upper bound.

The upper bound is a diagnostic over measured IDs, never an APC measurement.
It does not change the frozen experiment or its primary statistical analysis.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse
import csv
import gzip
import hashlib
import json


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def lcp(a,b):
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y:return i
    return min(len(a),len(b))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[1]
    freeze=json.loads((a.root/'freeze.json').read_text());receipt=json.loads((a.root/'pre_forward_receipt_v1.json').read_text())
    for r in freeze['files']:assert sha(repo/r['path'])==r['sha256'],r['path']
    assert receipt['freeze_sha256']==sha(a.root/'freeze.json') and receipt['remote_commit_verified']
    protocol=json.loads((repo/freeze['protocol_path']).read_text())
    sources=[json.loads(l) for l in (a.root/'inputs_v1/selected_packed_sources_v1.jsonl').open() if l.strip()]
    sources={r['source_group']:r['sample'] for r in sources if r['sample'] is not None}
    stable_hashes={};counts=Counter();details=[];publication_first=[];turn_groups=defaultdict(list)
    for repeat in range(1,4):
        base=a.root/'cells'/f'raw_native_r{repeat}'
        completion=json.loads((base/'completion_v1.json').read_text())
        assert completion['execution_complete'] and sha(base/'raw.jsonl.gz')==completion['raw_sha256']
        histories=defaultdict(list);prior_sequences=defaultdict(list)
        with gzip.open(base/'raw.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                r=json.loads(line)
                if r['row_type']!='request':continue
                assert r['success'] and r['request_started_epoch']>receipt['created_server_epoch']
                publication_first.append(r['request_started_epoch'])
                sid=r['source_group'];sample=sources[sid];turn=r['turn'];messages=r['messages']
                assert len(histories[sid])==turn and len(messages)==2+2*turn
                for i,(query,answer) in enumerate(histories[sid]):
                    assert messages[1+2*i]=={'role':'user','content':query}
                    assert messages[2+2*i]=={'role':'assistant','content':answer}
                base_question='\n'.join(s['text'] for s in sample['segments'] if s['type']=='USER_QUERY')
                query=protocol['query_wrappers'][turn].format(query=base_question)
                assert query in messages[-1]['content']
                for segment in sample['segments']:
                    if segment['type'] not in {'SYS_PROMPT','USER_QUERY'}:
                        assert segment['text'] in messages[-1]['content']
                        assert segment['text'] in r['prompt_text']
                    elif segment['type']=='SYS_PROMPT':
                        assert segment['text'] in messages[0]['content']
                        assert segment['text'] in r['prompt_text']
                stable_text=[r['prompt_text'][s['start']:s['end']] for s in r['character_spans'] if s['category']=='stable']
                stable_hash=canonical(stable_text)
                assert stable_hashes.setdefault(sid,stable_hash)==stable_hash
                ids=r['prompt_token_ids']
                upper=min(len(ids)-1,max([lcp(ids,old) for old in prior_sequences[sid]] or [0]))
                upper=upper//protocol['block_size']*protocol['block_size']
                assert r['native_cached_tokens']<=upper
                counts['requests']+=1
                if turn:
                    counts['future_requests']+=1
                    counts['future_native_hits_equal_unbounded_prefix_bound']+=int(r['native_cached_tokens']==upper)
                else:assert r['native_cached_tokens']==0
                details.append({'repeat':repeat,'source_group':sid,'family':r['family'],'turn':turn,
                    'actual_native_cached_tokens':r['native_cached_tokens'],
                    'offline_unbounded_prefix_upper_tokens':upper,
                    'native_matches_upper':r['native_cached_tokens']==upper})
                turn_groups[(r['family'],turn)].append(r)
                turn_groups[('ALL',turn)].append(r)
                prior_sequences[sid].append(ids+r['output_token_ids'])
                histories[sid].append((query,r['output_text']))
    assert counts['requests']==len(sources)*10*3
    output=a.root/'analysis_v1/independent_integrity_v1.json';assert not output.exists()
    report={'status':'PASS','requests':counts['requests'],'future_requests':counts['future_requests'],
            'stable_source_bodies_identical_across_turns_and_repeats':True,
            'all_histories_use_exact_prior_generated_answers':True,
            'all_current_packed_contexts_and_CODE_PREFIX_preserved':True,
            'all_source_requests_after_verified_publication_receipt':True,
            'first_source_request_epoch':min(publication_first),
            'publication_receipt_epoch':receipt['created_server_epoch'],
            'future_native_hits_equal_unbounded_prefix_bound':counts['future_native_hits_equal_unbounded_prefix_bound'],
            'offline_bound_is_not_an_empirical_APC_counter':True,'offline_prefix_checks':details,
            'frozen_primary_method_or_inputs_changed':False,'new_model_requests':0}
    output.write_text(json.dumps(report,indent=2)+'\n')
    profile=[]
    for (family,turn),rows in sorted(turn_groups.items()):
        prompt=sum(r['prompt_tokens'] for r in rows)
        stable=sum(r['stable_tokens'] for r in rows)
        profile.append({'family':family,'turn':turn,'requests':len(rows),
            'source_groups':len({r['source_group'] for r in rows}),
            'stable_ratio_pct':100*stable/prompt,
            'stable_native_recovery_pct':100*sum(r['stable_cached_tokens'] for r in rows)/stable,
            'all_native_hit_pct':100*sum(r['native_cached_tokens'] for r in rows)/prompt,
            'history_fraction_pct':100*sum(r['history_tokens'] for r in rows)/prompt})
    with (a.root/'analysis_v1/turn_profiles_v1.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(profile[0]));writer.writeheader();writer.writerows(profile)
    print(json.dumps({k:v for k,v in report.items() if k!='offline_prefix_checks'}),flush=True)


if __name__=='__main__':main()
