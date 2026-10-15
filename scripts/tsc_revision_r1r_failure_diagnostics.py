"""Separate compiled regression, raw-route variability and witness-scope changes."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write,first_divergence


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cells={}
    for directory in sorted((a.root/'cells').iterdir()):
        if not (directory/'summary.json').exists(): continue
        rows=read(directory/'raw.jsonl'); future=[r for r in rows if r['row_type']=='future']; first=future[0]
        cells[(first['study'],first['model'],first['repeat'],first['policy'])]=rows
    cases=[]; source_cases=defaultdict(list)
    for (study,model,repeat,policy),rows in cells.items():
        if policy=='raw-order' or (study,model,repeat,'raw-order') not in cells: continue
        refs={(r['session_id'],r['turn_id']):r for r in cells[(study,model,repeat,'raw-order')] if r['row_type']=='future'}
        witnesses={}
        for r in rows:
            if r['row_type'] not in ('warm','future'): continue
            key=(r['certificate_namespace'],r['query_scope'])
            if r.get('scope_first_raw_business'): witnesses.setdefault(key,r)
            if r['row_type']!='future': continue
            ref=refs[(r['session_id'],r['turn_id'])]; drop=ref['task_score']-r['task_score']
            if drop<=.03: continue
            raw_repeats=[]
            for rindex in (1,2,3):
                other=cells.get((study,model,rindex,'raw-order'),[])
                raw_repeats += [x for x in other if x['row_type']=='future' and (x['session_id'],x['turn_id'])==(r['session_id'],r['turn_id'])]
            witness=witnesses.get(key)
            row={'study':study,'model':model,'repeat':repeat,'policy':policy,'source_group':r['source_group'],'family':r['family'],
                 'session_id':r['session_id'],'turn_id':r['turn_id'],'effective_level':r['effective_level'],'query_scope':r['query_scope'],
                 'raw_score':ref['task_score'],'candidate_score':r['task_score'],'quality_drop':drop,
                 'raw_repeat_min_score':min(x['task_score'] for x in raw_repeats),'raw_repeat_max_score':max(x['task_score'] for x in raw_repeats),
                 'raw_repeat_observations':len(raw_repeats),'raw_repeat_coverage_complete':len(raw_repeats)==3,
                 'raw_repeat_score_stable':len(raw_repeats)==3 and max(x['task_score'] for x in raw_repeats)-min(x['task_score'] for x in raw_repeats)<=.03,
                 'witness_available':bool(witness),'witness_turn':witness['turn_id'] if witness else 'unavailable',
                 'witness_score':witness['task_score'] if witness else 'unavailable',
                 'raw_text':ref['output_text'],'candidate_text':r['output_text'],
                 'witness_text':witness['output_text'] if witness else 'unavailable',
                 'candidate_matches_witness_ids':r['output_token_ids']==witness['output_token_ids'] if witness else 'unavailable',
                 'raw_candidate_first_divergence':first_divergence(ref['output_token_ids'],r['output_token_ids'])}
            cases.append(row); source_cases[(study,model,policy,r['source_group'])].append(row)
    grouped=[]
    for key,rs in sorted(source_cases.items()):
        grouped.append({'study':key[0],'model':key[1],'policy':key[2],'source_group':key[3],
                        'material_drop_pairs':len(rs),'compiled_drop_pairs':sum(r['effective_level']!='L0' for r in rs),
                        'distinct_failing_repeats':len({r['repeat'] for r in rs}),'raw_repeat_stable_pairs':sum(r['raw_repeat_score_stable'] for r in rs),
                        'mean_score_drop':statistics.fmean(r['quality_drop'] for r in rs)})
    a.output.mkdir(parents=True,exist_ok=True)
    if cases: write(a.output/'material_drop_cases_v1.csv',cases); write(a.output/'material_drop_source_clusters_v1.csv',grouped)
    result={'material_drop_pairs':len(cases),'compiled_material_drop_pairs':sum(r['effective_level']!='L0' for r in cases),
            'raw_fallback_material_drop_pairs':sum(r['effective_level']=='L0' for r in cases),'source_clusters':len(grouped),
            'diagnostic_only':'No outcome changes admission, source selection or formal quality thresholds.'}
    (a.output/'failure_diagnostics_v1.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
