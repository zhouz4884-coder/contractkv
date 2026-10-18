"""Independently check every prompt and aggregate the preregistered survey."""
from pathlib import Path
from collections import defaultdict, Counter
import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import sys

os.environ.update(USE_TORCH='0', USE_TF='0', HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transformers import AutoTokenizer
from scripts.tsc_tableI_survey_common_v1 import digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sums(rows):
    return [sum(r[k] for r in rows) for k in
            ['prompt_tokens','stable_tokens','native_cached_tokens','stable_cached_tokens','history_tokens','query_tokens','framing_tokens']]


def ratios(values):
    prompt, stable, hit, stable_hit, *_ = values
    return [100*stable/prompt, 100*stable_hit/stable, 100*hit/prompt]


def percentile(values, fraction):
    values = sorted(values)
    pos = (len(values)-1)*fraction
    low = int(pos)
    high = min(low+1,len(values)-1)
    return values[low]+(values[high]-values[low])*(pos-low)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--tokenizer', required=True)
    a = p.parse_args()
    out = a.root/'analysis_v1'
    assert not out.exists()
    freeze = json.loads((a.root/'freeze.json').read_text())
    protocol = json.loads((ROOT/freeze['protocol_path']).read_text())
    selected = [json.loads(l) for l in (a.root/'inputs_v1/selected_packed_sources_v1.jsonl').open() if l.strip()]
    eligible = {r['source_group']:r for r in selected if r['sample'] is not None}
    tokenizer = AutoTokenizer.from_pretrained(a.tokenizer, local_files_only=True, trust_remote_code=False)
    checked = {}
    rows = []
    provenance = []
    for repeat in range(1,protocol['fresh_process_repetitions']+1):
        base = a.root/'cells'/f'raw_native_r{repeat}'
        complete = json.loads((base/'completion_v1.json').read_text())
        raw = base/'raw.jsonl.gz'
        assert complete['execution_complete'] and complete['raw_sha256']==sha(raw)
        assert len(complete['session_cache_resets'])==len(eligible)
        provenance.append({'repeat':repeat,'raw_sha256':sha(raw),'completion_sha256':sha(base/'completion_v1.json')})
        seen = set()
        with gzip.open(raw,'rt',encoding='utf-8') as stream:
            for line in stream:
                r = json.loads(line)
                if r['row_type']!='request':
                    assert r['row_type']=='capacity_exclusion'
                    continue
                assert r['success'] and r['actual_prompt_token_ids_verified']
                assert r['source_group'] in eligible and (r['source_group'],r['turn']) not in seen
                seen.add((r['source_group'],r['turn']))
                ids = r['prompt_token_ids']
                assert digest(ids)==r['prompt_ids_sha256'] and digest(r['output_token_ids'])==r['output_ids_sha256']
                key=(r['prompt_ids_sha256'],digest(r['character_spans']))
                if key not in checked:
                    text = tokenizer.apply_chat_template(r['messages'],tokenize=False,
                        add_generation_prompt=True,enable_thinking=False)
                    assert text==r['prompt_text']
                    encoded=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True)
                    assert list(encoded['input_ids'])==ids
                    spans=r['character_spans'];special=set(tokenizer.all_special_ids)
                    stable=[];counts=Counter()
                    # Independent interval-attribution pass over stored input evidence.
                    for token,(left,right) in zip(ids,encoded['offset_mapping']):
                        owners=[s['category'] for s in spans if s['start']<=left<right<=s['end']]
                        assert len(owners)<=1
                        kind=owners[0] if owners and token not in special else 'framing'
                        counts[kind]+=1;stable.append(int(kind=='stable'))
                    checked[key]=(stable,counts)
                stable,counts=checked[key]
                hit=r['native_cached_tokens']
                assert len(ids)==r['prompt_tokens'] and counts['stable']==r['stable_tokens']
                assert sum(stable[:hit])==r['stable_cached_tokens']
                for kind in ['history','query','framing']:
                    assert counts[kind]==r[kind+'_tokens']
                assert 0<=r['stable_cached_tokens']<=hit<len(ids)
                if r['turn']==0:assert hit==0
                rows.append({k:r[k] for k in ['repeat','gpu','source_group','family','turn','population',
                    'prompt_ids_sha256','prompt_tokens','stable_tokens','native_cached_tokens',
                    'stable_cached_tokens','history_tokens','query_tokens','framing_tokens','boundary_tokens',
                    'finish_reason','generation_wall_s']})
                rows[-1]['output_tokens']=len(r['output_token_ids'])
        assert len(seen)==len(eligible)*protocol['turns_per_session']
    out.mkdir()
    with (out/'requests_v1.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    results=[]
    for population in ['future','warm','all_business']:
        for family in protocol['families']+['ALL']:
            rr=[r for r in rows if (population=='all_business' or r['population']==population)
                and (family=='ALL' or r['family']==family)]
            values=sums(rr);rate=ratios(values)
            by_source=defaultdict(list)
            for r in rr:by_source[r['source_group']].append(r)
            source_values=[sums(group) for group in by_source.values()]
            source_ratios=[ratios(v) for v in source_values]
            rng=random.Random(protocol['seed']);draws=[[],[],[]]
            for _ in range(2000):
                sampled=rng.choices(source_values,k=len(source_values))
                trial=ratios([sum(v[k] for v in sampled) for k in range(7)])
                for k,value in enumerate(trial):draws[k].append(value)
            metrics=['stable_ratio_pct','stable_native_recovery_pct','all_native_hit_pct']
            record={'population':population,'family':family,'sources':len(by_source),'requests':len(rr),
                    'prompt_tokens':values[0],'stable_tokens':values[1],'native_cached_tokens':values[2],
                    'stable_cached_tokens':values[3],'history_tokens':values[4],
                    'query_tokens':values[5],'framing_tokens':values[6],
                    **dict(zip(metrics,rate)),
                    'source_macro_pct':dict(zip(metrics,[sum(v[k] for v in source_ratios)/len(source_ratios) for k in range(3)])),
                    'source_cluster_95pct':{name:[percentile(draws[k],.025),percentile(draws[k],.975)] for k,name in enumerate(metrics)},
                    'per_repeat':[{'repeat':rep,**dict(zip(metrics,ratios(sums([r for r in rr if r['repeat']==rep]))))} for rep in range(1,4)]}
            results.append(record)
    primary=[r for r in results if r['population']=='future' and r['family']!='ALL']
    report={'schema':'contractkv.independent-structural-survey.results.v1','execution_complete':True,
            'freeze_sha256':sha(a.root/'freeze.json'),'source_logs':provenance,
            'selected_sources':len(selected),'eligible_sources':len(eligible),
            'capacity_exclusions':[{'family':r['family'],'source_group':r['source_group'],'status':r['status']} for r in selected if r['sample'] is None],
            'all_requests':len(rows),'future_requests':sum(r['population']=='future' for r in rows),
            'all_actual_prompt_IDs_independently_checked':True,'unique_prompt_and_span_checks':len(checked),
            'summaries':results,'unweighted_five_family_future_mean_pct':{k:sum(r[k] for r in primary)/5 for k in ['stable_ratio_pct','stable_native_recovery_pct','all_native_hit_pct']},
            'finish_reasons':dict(Counter(r['finish_reason'] for r in rows)),
            'original_TableI_measurement_lineage_recovered':False,'post_forward_parameter_changes':False,
            'limits':protocol['claim_limits'],'new_GPU_experiments':'Native raw APC only; no ContractKV speed or quality certification claim'}
    (out/'summary_v1.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'complete':True,'requests':len(rows),'future_requests':report['future_requests'],
                      'five_family_future_mean_pct':report['unweighted_five_family_future_mean_pct']}),flush=True)


if __name__=='__main__':
    main()
