"""Audit causal query routing and summarize real repair-study outputs."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.summarize_submission_supplement import percentile


def route_audit(rows):
    approved={}; bad=[]; compiled=0; read_tokens=0; rejected_pub=0; new_raw=0
    for r in rows:
        key=(r.get('certificate_namespace',r['session_id']),r.get('query_scope'))
        if r['row_type']=='verification':
            for attempt in r['attempts']:
                if not attempt['certificate_issued']:
                    rejected_pub+=int(attempt['committed_tokens'])
                read_tokens+=int(attempt.get('cached_prefix_read_tokens',0))
            if r['certificate_issued']: approved[key]=r['selected_level']
        elif r['row_type'] in {'warm','future'}:
            if r['effective_level']!='L0':
                compiled+=1
                if approved.get(key)!=r['effective_level']: bad.append((key,r['turn_id']))
            if r.get('scope_first_raw_business'):
                new_raw+=1
                if r['effective_level']!='L0': bad.append((key,'unknown_scope_not_raw'))
    return {'scope_invalid_admissions':len(bad),'compiled_business_requests':compiled,
            'first_scope_raw_business_requests':new_raw,'rejected_published_tokens':rejected_pub,
            'actual_cached_prefix_read_tokens':read_tokens}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cells={}; table=[]; audits=[]
    for path in sorted((a.root/'cells').glob('*/summary.json')):
        summary=json.loads(path.read_text()); raw=path.parent/'raw.jsonl'
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=summary['raw_file_sha256']: raise ValueError('Changed raw cell')
        rows=read(raw); future=[r for r in rows if r['row_type']=='future']; first=future[0]
        key=(first['model'],first['repeat'],first['policy']); cells[key]=rows
        audit=route_audit(rows); audits.append({'cell':path.parent.name,**audit})
        ready=[r['ready_ttft_ms'] for r in future]; backend=[r['ttft_ms'] for r in future]
        table.append({'cell':path.parent.name,'model':key[0],'repeat':key[1],'policy':key[2],
                      'requests':len(future),'completed':sum(r['success'] for r in future),'compiled_futures':sum(r['effective_level']!='L0' for r in future),
                      'mean_ready_ttft_ms':statistics.fmean(ready),'p95_ready_ttft_ms':percentile(ready,.95),
                      'p99_ready_ttft_ms':percentile(ready,.99),'mean_backend_ttft_ms':statistics.fmean(backend),
                      'new_prefill_tokens_mean':statistics.fmean(r['new_prefill_tokens'] for r in future),
                      'wall_s':summary['wall_s_including_all_setup_and_verification'],
                      'full_wall_goodput_rps':len(future)/summary['wall_s_including_all_setup_and_verification'],
                      'ready_1500ms_slo_goodput_rps':sum(r['success'] and r['ready_ttft_ms']<=1500 for r in future)/summary['wall_s_including_all_setup_and_verification'],
                      'verification_ms_total':summary['verification_ms_total'],'verification_calls':summary['verification_calls'],**audit})
    pairs=[]
    for (model,repeat,policy),rows in cells.items():
        if policy=='raw-order' or (model,repeat,'raw-order') not in cells: continue
        refs={(r['session_id'],r['turn_id']):r for r in cells[(model,repeat,'raw-order')] if r['row_type']=='future'}
        for r in rows:
            if r['row_type']!='future': continue
            ref=refs[(r['session_id'],r['turn_id'])]
            pairs.append({'model':model,'repeat':repeat,'policy':policy,'session_id':r['session_id'],'turn_id':r['turn_id'],
                          'family':r['family'],'effective_level':r['effective_level'],'raw_score':ref['task_score'],'candidate_score':r['task_score'],
                          'quality_drop':ref['task_score']-r['task_score'],'first_diverging_token':first_divergence(ref['output_token_ids'],r['output_token_ids'])})
    groups=defaultdict(list)
    for r in pairs:
        groups[(r['model'],r['policy'],'ALL')].append(r); groups[(r['model'],r['policy'],r['family'])].append(r)
    quality=[]
    for k,rs in sorted(groups.items()):
        quality.append({'model':k[0],'policy':k[1],'family':k[2],'pairs':len(rs),'compiled_pairs':sum(r['effective_level']!='L0' for r in rs),
                        'material_drops_gt_0_03':sum(r['quality_drop']>.03 for r in rs),
                        'material_drops_on_compiled':sum(r['quality_drop']>.03 and r['effective_level']!='L0' for r in rs),
                        'mean_quality_drop':statistics.fmean(r['quality_drop'] for r in rs),
                        'raw_mean_score':statistics.fmean(r['raw_score'] for r in rs),'candidate_mean_score':statistics.fmean(r['candidate_score'] for r in rs)})
    a.output.mkdir(parents=True,exist_ok=True)
    write(a.output/'performance_by_cell_v1.csv',table); write(a.output/'query_route_audit_v1.csv',audits)
    write(a.output/'quality_pairs_v1.csv',pairs); write(a.output/'quality_summary_v1.csv',quality)
    result={'schema_version':'tsc-r1r.summary.v1','completed_cells':len(cells),'paired_quality_requests':len(pairs),
            'scope_invalid_admissions':sum(r['scope_invalid_admissions'] for r in audits),
            'rejected_published_tokens':sum(r['rejected_published_tokens'] for r in audits),
            'source_scope':'development or heldout is determined by immutable input/cell manifests, not this summarizer',
            'goal_complete':False}
    (a.output/'summary_manifest_v1.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
