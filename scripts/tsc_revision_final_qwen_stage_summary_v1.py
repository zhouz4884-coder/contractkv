"""Interim Qwen three-repeat totals from complete, SHA-checked projections."""
from collections import Counter,defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import argparse


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main(study,output):
    assert not output.exists();inputs=[];projections={};metrics={}
    for repeat in (1,2,3):
        prefix='first_repeat' if repeat==1 else f'repeat{repeat}'
        a=study/f'{prefix}_projection_v1.json';b=study/f'{prefix}_small_metrics_v1.json'
        projections[repeat]=read(a);metrics[repeat]=read(b);inputs += [a,b]
    results=[]
    for load in ('common','high'):
        performance=[];all_pairs=[];reasons=Counter();hits=Counter();raw_variants=defaultdict(dict)
        for repeat in (1,2,3):
            q=next(r for r in projections[repeat]['comparisons'] if r['load']==load)
            raw=next(r for r in metrics[repeat]['results'] if r['load']==load and r['policy']=='raw-order')
            ct=next(r for r in metrics[repeat]['results'] if r['load']==load and r['policy']=='risk-tail')
            performance.append(dict(repeat=repeat,raw_wall_s=raw['wall_s'],contract_wall_s=ct['wall_s'],
                direct_wall_ratio=raw['wall_s']/ct['wall_s'],raw_SLO_pass=raw['SLO_compliant'],contract_SLO_pass=ct['SLO_compliant'],
                raw_goodput=raw['absolute_goodput'],contract_goodput=ct['absolute_goodput']))
            all_pairs += [dict(r,repeat=repeat) for r in q['pairs']];reasons.update(q['qualification_reasons']);hits.update(ct['compiled_native_hit_classes'])
            for row in q['pairs']:
                key=row['source_group'],row['session_id'],row['turn']
                raw_variants[key][repeat]=(row['raw_output_token_ids'],row['raw_finish'],row['raw_score'])
        raw_comparison=Counter();by_source=defaultdict(Counter)
        for key,variants in raw_variants.items():
            assert set(variants)=={1,2,3}
            for one,two in itertools.combinations((1,2,3),2):
                a=variants[one];b=variants[two];raw_comparison['pairs']+=1
                raw_comparison['ID_or_finish_changes']+=int(a[:2]!=b[:2])
                raw_comparison['material_up']+=int(b[2]-a[2]>.03);raw_comparison['material_down']+=int(b[2]-a[2]<-.03)
        drops=[r for r in all_pairs if r['material_down']];drop_reproduced=0
        for row in drops:
            variants=raw_variants[row['source_group'],row['session_id'],row['turn']]
            observed=(row['contract_output_token_ids'],row['contract_finish'])
            drop_reproduced+=any(v[:2]==observed for v in variants.values())
        for row in all_pairs:
            c=by_source[row['source_group']];c['pairs']+=1;c['compiled_business']+=row['compiled']
            c['compiled_future']+=row['compiled'] and row['row_type']=='future';c['up']+=row['material_up'];c['down']+=row['material_down']
        raw_clock=sum(r['raw_wall_s'] for r in performance);ct_clock=sum(r['contract_wall_s'] for r in performance)
        raw_pass=sum(r['raw_SLO_pass'] for r in performance);ct_pass=sum(r['contract_SLO_pass'] for r in performance)
        results.append(dict(load=load,paired_processes=3,business_pairs=len(all_pairs),future_pairs=sum(r['row_type']=='future' for r in all_pairs),
            performance_by_repeat=performance,pooled_raw_clock_s=raw_clock,pooled_contract_clock_s=ct_clock,
            pooled_direct_wall_ratio=raw_clock/ct_clock,direct_ratio_range=[min(r['direct_wall_ratio'] for r in performance),max(r['direct_wall_ratio'] for r in performance)],
            raw_SLO_compliant=raw_pass,contract_SLO_compliant=ct_pass,pooled_raw_goodput=raw_pass/raw_clock,pooled_contract_goodput=ct_pass/ct_clock,
            absolute_goodput_change=ct_pass/ct_clock-raw_pass/raw_clock,
            compiled_business=sum(r['compiled'] for r in all_pairs),compiled_future=sum(r['compiled'] and r['row_type']=='future' for r in all_pairs),
            compiled_ID_or_finish_changes=sum(r['compiled'] and r['ID_or_finish_change'] for r in all_pairs),
            all_material_up=sum(r['material_up'] for r in all_pairs),all_material_down=len(drops),
            L0_drop_outputs_also_seen_at_same_position_in_three_Raw_controls=drop_reproduced,
            Raw_repeat_pairwise_counts=dict(raw_comparison),qualification_reasons=dict(reasons),compiled_native_hits=dict(hits),
            by_source={source:dict(c) for source,c in sorted(by_source.items())}))
    value=dict(schema_version='contractkv.qwen-stage-interim-summary.v1',complete_cells=12,results=results,new_GPU_requests=0,
        final_three_model_and_gate_analysis_still_required=True,
        boundary='These actual counts and process ranges are interim; no source-population or causal-background-noise attribution. All load/repeat samples share six sources.',
        inputs=[dict(path=p.name,sha256=sha(p)) for p in inputs],entry_sha256=sha(Path(__file__)))
    with output.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2);handle.write('\n')
    print(json.dumps(value))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.study,a.output)
