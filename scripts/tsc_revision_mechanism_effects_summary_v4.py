"""Report observed behavior/harm denominators without using declared risk labels.

Postprocessing only. Keeps the frozen v3 collector and original analysis intact.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics


def csvrows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def yes(value):return value=='True'
def no(value):return value=='False'
def ratio(a,b):return a/b if b else None


def main(study,analysis,output):
    if output.exists():raise FileExistsError(output)
    state=json.loads((study/'execution_state_v1.json').read_text())
    assert state['status']=='MATRIX_COMPLETE_PENDING_ANALYSIS' and len(state['completed_cells'])==9
    assert json.loads((analysis/'summary_v1.json').read_text())['status']=='complete'
    behavior=csvrows(analysis/'behavior_pairs_v1.csv')
    verifications=csvrows(analysis/'verification_cost_publication_v1.csv')
    vi={(x['cell'],x['case_id']):x for x in verifications}
    assert len(behavior)==180 and len(verifications)==198
    business={}
    for rel in state['completed_cells']:
        p=study/rel/'responses.jsonl'
        with p.open(encoding='utf-8') as f:
            for line in f:
                x=json.loads(line)
                if x['event']=='business':
                    k=(x['cell_id'],x['case_id'],x['condition']);assert k not in business
                    business[k]=x['response']
    groups=defaultdict(list)
    for row in behavior:
        groups[row['model'],row['family']].append(row)
        groups[row['model'],'ALL_FAMILIES'].append(row)
    result=[]
    for (model,family),records in sorted(groups.items()):
        for mode in ('all_observed_candidates','raw_repeat_stable_subset'):
            rr=records if mode=='all_observed_candidates' else [x for x in records if yes(x['raw_repeat_stable'])]
            observed=[x for x in rr if x['unchecked_behavior_changed'] in ('True','False') and x['unchecked_finish_changed'] in ('True','False')]
            changed=[x for x in observed if yes(x['unchecked_behavior_changed']) or yes(x['unchecked_finish_changed'])]
            unchanged=[x for x in observed if no(x['unchecked_behavior_changed']) and no(x['unchecked_finish_changed'])]
            harmed=[x for x in observed if yes(x['unchecked_score_down'])]
            conclusive=lambda x:not yes(vi[x['cell'],x['case_id']]['indeterminate_response'])
            rejected=lambda x:not yes(x['certificate_issued']) and conclusive(x)
            rpc=sum(int(vi[x['cell'],x['case_id']]['verification_calls']) for x in rr)
            reject_tokens=sum(int(vi[x['cell'],x['case_id']]['actual_backend_committed_tokens']) for x in rr if rejected(x))
            cost=[float(vi[x['cell'],x['case_id']]['full_qualification_ms']) for x in rr]
            raw_ms=[];unchecked_ms=[];post_ms=[]
            for x in rr:
                bycond={k[2]:v for k,v in business.items() if k[:2]==(x['cell'],x['case_id'])}
                assert len(bycond)==4
                raw=bycond['raw_witness'];unchecked=bycond['unchecked_same_candidate']
                post=next(v for k,v in bycond.items() if k.startswith('post_decision_'))
                for target,row in ((raw_ms,raw),(unchecked_ms,unchecked),(post_ms,post)):
                    target.append(float(row['latency_ms']))
            result.append(dict(model=model,family=family,population=mode,total_candidates=len(rr),
                successfully_observed_candidate_pairs=len(observed),unavailable_candidate_pairs=len(rr)-len(observed),
                observed_ID_or_finish_changes=len(changed),observed_task_score_decreases=len(harmed),
                observed_task_score_increases=sum(yes(x['unchecked_score_up']) for x in observed),
                behavior_unchanged_candidates=len(unchanged),
                changed_candidates_conclusively_rejected=sum(rejected(x) for x in changed),
                changed_candidate_conclusive_rejection_rate=ratio(sum(rejected(x) for x in changed),len(changed)),
                task_harmed_candidates_conclusively_rejected=sum(rejected(x) for x in harmed),
                task_harmed_candidate_conclusive_rejection_rate=ratio(sum(rejected(x) for x in harmed),len(harmed)),
                unchanged_candidates_admitted=sum(yes(x['certificate_issued']) for x in unchanged),
                unchanged_candidate_admission_rate=ratio(sum(yes(x['certificate_issued']) for x in unchanged),len(unchanged)),
                observed_changed_candidates_admitted=sum(yes(x['certificate_issued']) for x in changed),
                observed_task_harmed_candidates_admitted=sum(yes(x['certificate_issued']) for x in harmed),
                unchanged_candidates_conclusively_rejected=sum(rejected(x) for x in unchanged),
                indeterminate_qualification_responses=sum(not conclusive(x) for x in rr),
                admitted_post_route_ID_divergences=sum(yes(x['certificate_issued']) and yes(x['actual_post_route_ID_difference']) for x in rr),
                admitted_post_route_finish_divergences=sum(yes(x['certificate_issued']) and yes(x['actual_post_route_finish_difference']) for x in rr),
                admitted_post_route_score_decreases=sum(yes(x['certificate_issued']) and yes(x['post_route_score_down']) for x in rr),
                fallback_post_route_ID_divergences=sum(not yes(x['certificate_issued']) and yes(x['actual_post_route_ID_difference']) for x in rr),
                whole_route_score_increases=sum(yes(x['post_route_score_up']) for x in rr),
                whole_route_score_decreases=sum(yes(x['post_route_score_down']) for x in rr),
                raw_repeat_ID_changes=sum(no(x['raw_repeat_stable']) for x in rr),
                positive_raw_task_score_candidates=sum(float(x['raw_score'])>0 for x in rr),
                verification_RPC_attempts=rpc,rejected_actual_published_tokens=reject_tokens,
                rejected_actual_published_full_blocks=reject_tokens//16,
                complete_qualification_ms_sum=sum(cost),complete_qualification_ms_mean=statistics.fmean(cost) if cost else None,
                raw_witness_business_ms_mean=statistics.fmean(raw_ms) if raw_ms else None,
                unchecked_business_ms_mean=statistics.fmean(unchecked_ms) if unchecked_ms else None,
                post_route_business_ms_mean=statistics.fmean(post_ms) if post_ms else None))
    output.mkdir(parents=True)
    with (output/'observed_denominator_effects_v1.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    report=dict(status='observed_effect_denominators_complete',new_GPU_requests=0,behavior_candidates=180,
        result_rows=len(result),input_sha256={p.name:sha(p) for p in [analysis/'behavior_pairs_v1.csv',analysis/'verification_cost_publication_v1.csv']},
        source_sha256=sha(Path(__file__)),model_totals=[x for x in result if x['family']=='ALL_FAMILIES'],
        boundaries=['Declared safe/order-risk labels are not used to define observed harmful or unchanged populations.',
            'Behavior change and task harm are different columns; score increases do not establish behavioral equivalence.',
            'Conservative rejection of an unchanged candidate is an observational false rejection, not automatically an implementation error or an eligible-scope violation.',
            'Cold unchecked differences and actual post-certificate serving differences are separate observations.',
            'Raw-repeat unstable cases remain in whole-case totals and are separately conditioned, not dropped.',
            'Indeterminate responses are not counted as conclusive rejections.',
            'Verification attempts are actual client RPC attempts; not a GPU-kernel count. Diagnostic I/O costs do not establish serving speed.',
            'The frozen code_context family is synthetic Python assignments; it does not close the real RepoBench next-line evidence gap.'])
    with (output/'summary_v1.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    with (output/'analysis_source.py').open('xb') as f:f.write(Path(__file__).read_bytes())
    print(json.dumps(dict(cases=180,rows=len(result),new_GPU_requests=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.study.resolve(),a.analysis.resolve(),a.output.resolve())
