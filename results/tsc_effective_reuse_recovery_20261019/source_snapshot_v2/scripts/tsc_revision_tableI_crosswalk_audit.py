"""Reaggregate frozen token ledgers with separate denominators and cohorts."""
from pathlib import Path
from collections import defaultdict, Counter
import csv
import hashlib
import json
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tsc_revision_evidence_closure_20261017/tableI_crosswalk'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    datasets={
        'bounded_five_family_controls':'table_I_reconstruction_old_R4_control_v2',
        'independent_faithful_six_sources':'table_I_reconstruction_independent_primary_v1',
        'same_four_development_sources_word_cap':'table_I_reconstruction_head_DEV_v1',
        'same_four_development_sources_faithful':'table_I_reconstruction_faithful_DEV_v1'}
    output=[];provenance=[];types={}
    for name,stem in datasets.items():
        base=ROOT/'results/tsc_revision_r4'/stem
        report=json.loads(base.with_suffix('.json').read_text())
        with base.with_suffix('.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        assert sha(base.with_suffix('.csv'))==report['request_csv_sha256']
        assert report['is_original_Table_I_numeric_reproduction'] is False
        assert all(r['actual_IDs_verified']=='True' for r in rows)
        maps=report['one_actual_ID_and_segment_map_per_model_source']
        types[name]={'representative_inputs':len(maps),
            'segment_type_counts':dict(Counter(s['type'] for r in maps for s in r['segment_body_map']))}
        groups=defaultdict(list)
        for r in rows:
            if r['row_type']!='future':continue
            groups[r['model'],r['study'],'ALL'].append(r)
            groups[r['model'],r['study'],r['family']].append(r)
        for (model,study,family),rr in sorted(groups.items()):
            total=sum(int(r['prompt_tokens']) for r in rr)
            stable=sum(int(r['stable_body_tokens']) for r in rr)
            native=sum(int(r['native_prefix_hit_tokens']) for r in rr)
            stable_hit=sum(int(r['stable_body_native_hit_tokens']) for r in rr)
            by_source=defaultdict(list)
            for r in rr:by_source[r['source_group']].append(r)
            macro=statistics.fmean(sum(int(r['stable_body_tokens']) for r in ss)/sum(int(r['prompt_tokens']) for r in ss) for ss in by_source.values())
            item={'cohort':name,'model':model,'study':study,'family':family,
                'future_requests':len(rr),'sources':len(by_source),'all_prompt_tokens':total,
                'stable_body_tokens':stable,'native_total_hit_tokens':native,'stable_body_hit_tokens':stable_hit,
                'stable_body_fraction_pct':100*stable/total,'source_macro_stable_fraction_pct':100*macro,
                'native_total_hit_fraction_pct':100*native/total,
                'stable_body_recovery_pct':100*stable_hit/stable if stable else 0}
            original=next(r for r in report['summaries'] if r['model']==model and r['study']==study and r['family']==family and r['population']=='future')
            for field,key in [('all_prompt_tokens','all_prompt_tokens'),('stable_body_tokens','stable_body_tokens'),('native_total_hit_tokens','native_prefix_hit_tokens'),('stable_body_hit_tokens','stable_body_native_hit_tokens')]:assert item[field]==original[key]
            assert abs(item['stable_body_fraction_pct']/100-original['stable_body_fraction_token_weighted'])<1e-10
            output.append(item)
        provenance.extend({'cohort':name,'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in [base.with_suffix('.json'),base.with_suffix('.csv')])
    assert len([r for r in output if r['cohort']=='bounded_five_family_controls' and r['study']=='single-session' and r['family']!='ALL'])==15
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'crosswalk_future_v1.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
    data={'cohorts':datasets,'rows':output,'source_files':provenance,'representative_segment_types':types,
        'original_85_2_4_reproduced':False,'new_model_calls':0,
        'limits':['These are reaggregations of archived token ledgers, not a rerun of tokenizer-to-prompt-ID alignment.',
                  'The original Table-I cohort/measurement provenance remains unavailable.',
                  'An absence of CHAT_HISTORY in these audited cohorts does not identify an unknown original cohort.',
                  'Total native hits and stable-body native recovery use different denominators and numerators.']}
    (OUT/'crosswalk_audit_v1.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(output),'cohorts':len(datasets),'original_numbers_reproduced':False,
        'CHAT_HISTORY_in_representative_maps':{k:v['segment_type_counts'].get('CHAT_HISTORY',0) for k,v in types.items()}}))


if __name__=='__main__':main()
