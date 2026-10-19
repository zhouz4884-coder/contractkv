"""Input-driven exact-context clustering addendum; never reselects records."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse
import csv
import hashlib
import json
import random

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableI_remeasurement_20261018'


def context_hash(row):
    value=[{'type':s['type'],'text':s['text']} for s in row['segments']
           if s['type'] not in {'SYS_PROMPT','USER_QUERY','CHAT_HISTORY','TOOL_OBS','SCRATCHPAD'}]
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def source(row):return row['dataset']+':'+row['task']+':'+str(row['metadata']['source_group_id'])


def prepare():
    originals=[json.loads(l) for l in (STUDY/'inputs_v1/selected_original_sources_v1.jsonl').open(encoding='utf-8') if l.strip()]
    prep=json.loads((STUDY/'inputs_v1/input_preparation_v1.json').read_text())
    excluded=set(prep['excluded_source_groups'])
    prior=defaultdict(list);pool_by_id={}
    pool=ROOT/'results/workload/phase14d_full_pool_v2.jsonl'
    assert hashlib.sha256(pool.read_bytes()).hexdigest()==prep['source_pool_sha256']
    for line in pool.open(encoding='utf-8'):
        row=json.loads(line);sid=source(row);pool_by_id.setdefault(sid,row)
        if sid in excluded:prior[context_hash(row)].append(sid)
    rows=[{'record_id':r['source_group'],'family':r['family'],'original_context_sha256':context_hash(r)} for r in originals]
    groups=defaultdict(list)
    for r in rows:groups[r['original_context_sha256']].append(r['record_id'])
    families=[]
    for family in ['RULER','HotpotQA','NarrativeQA','Qasper','RepoBench']:
        rr=[r for r in rows if r['family']==family]
        families.append({'family':family,'registered_record_ids':len(rr),
            'exact_original_context_clusters':len({r['original_context_sha256'] for r in rr}),
            'records_with_context_seen_among_prior_excluded_ids':sum(r['original_context_sha256'] in prior for r in rr)})
    aux=json.loads((STUDY/'auxiliary_existing_six_source_v1.json').read_text())
    old=[context_hash(pool_by_id[s]) for s in aux['independent_source_groups']]
    report={'created_UTC':datetime.now(timezone.utc).isoformat(),
            'reason':'Registered doc:row identifiers do not necessarily identify distinct original documents; exact duplicate contexts were found.',
            'registered_records':len(rows),'exact_original_context_clusters':len(groups),
            'families':families,'record_to_context':rows,
            'duplicate_context_groups':[v for v in groups.values() if len(v)>1],
            'prior_context_overlap_groups':[{'context_sha256':h,'new_record_ids':v,'prior_record_ids':prior[h]} for h,v in groups.items() if h in prior],
            'existing_six_registered_ids':len(old),'existing_six_unique_context_hashes':len(set(old)),
            'new_vs_existing_six_context_hash_overlap':len(set(old)&set(groups)),
            'primary_point_estimator_inputs_or_generation_changed':False,
            'no_records_dropped_or_replaced':True,
            'registered_ID_cluster_intervals_will_be_retained':True,
            'additional_uncertainty_rule':'Within-family 2000-draw bootstrap over original-context SHA256 clusters; keep all questions, repeats and turns of each cluster together; seed20261018; token-pooled point estimates remain identical.',
            'context_uniqueness_does_not_prove_semantic_or_book_level_independence':True,
            'GPU_execution_not_claimed_complete':True,'new_model_requests':0}
    path=STUDY/'context_cluster_addendum_v1.json';assert not path.exists()
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['record_to_context','duplicate_context_groups','prior_context_overlap_groups']}))


def percentile(values,p):
    values=sorted(values);v=(len(values)-1)*p;i=int(v);j=min(i+1,len(values)-1)
    return values[i]+(values[j]-values[i])*(v-i)


def analyze():
    addendum=json.loads((STUDY/'context_cluster_addendum_v1.json').read_text())
    lookup={r['record_id']:r['original_context_sha256'] for r in addendum['record_to_context']}
    registered=json.loads((STUDY/'analysis_v1/summary_v1.json').read_text())
    assert registered['execution_complete']
    with (STUDY/'analysis_v1/requests_v1.csv').open(newline='') as f:records=list(csv.DictReader(f))
    summaries=[]
    for family in ['RULER','HotpotQA','NarrativeQA','Qasper','RepoBench']:
        rows=[r for r in records if r['family']==family and r['population']=='future']
        clusters=defaultdict(list)
        for r in rows:clusters[lookup[r['source_group']]].append(r)
        fields=['prompt_tokens','stable_tokens','native_cached_tokens','stable_cached_tokens']
        values=[[sum(int(r[k]) for r in rr) for k in fields] for rr in clusters.values()]
        def ratio(v):return [100*v[1]/v[0],100*v[3]/v[1],100*v[2]/v[0]]
        total=[sum(v[k] for v in values) for k in range(4)];point=ratio(total)
        old=next(r for r in registered['summaries'] if r['population']=='future' and r['family']==family)
        metrics=['stable_ratio_pct','stable_native_recovery_pct','all_native_hit_pct']
        assert all(abs(point[k]-old[m])<1e-10 for k,m in enumerate(metrics))
        draws=[[],[],[]];rng=random.Random(20261018)
        for _ in range(2000):
            chosen=rng.choices(values,k=len(values));trial=ratio([sum(v[k] for v in chosen) for k in range(4)])
            for k,value in enumerate(trial):draws[k].append(value)
        summaries.append({'family':family,'registered_record_ids':len({r['source_group'] for r in rows}),
            'exact_original_context_clusters':len(clusters),'future_requests':len(rows),
            **dict(zip(metrics,point)),
            'original_context_cluster_95pct':{m:[percentile(draws[k],.025),percentile(draws[k],.975)] for k,m in enumerate(metrics)},
            'registered_ID_cluster_95pct_retained':old['source_cluster_95pct']})
    output=STUDY/'analysis_v1/context_cluster_stats_v1.json';assert not output.exists()
    output.write_text(json.dumps({'reason':addendum['reason'],'point_estimates_unchanged':True,
        'all_registered_records_and_original_intervals_retained':True,
        'sampling_and_generation_parameters_unchanged':True,
        'clustering_addendum_not_part_of_initial_primary_registration':True,
        'summaries':summaries,'new_model_requests':0},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'context_cluster_summaries':len(summaries),'point_estimates_unchanged':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','analyze'],required=True)
    args=parser.parse_args();prepare() if args.stage=='prepare' else analyze()
