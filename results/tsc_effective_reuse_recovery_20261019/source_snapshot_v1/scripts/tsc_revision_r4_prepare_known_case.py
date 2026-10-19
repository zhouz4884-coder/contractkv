"""Extract actual known-case prompt IDs from sealed logs for controlled replay."""
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]


def main():
    base=Path('results/tsc_revision_r4/known_case_v1')
    if base.exists():raise ValueError('Preserve known-case input version')
    old=Path('results/tsc_revision_r3');sid='r3-heldout-52a55bace8746a75'
    sample=next(x for x in read(old/'inputs/heldout_sealed_sessions_v1.jsonl') if x['revision_session_id']==sid)
    identities=[];sources=[]
    for repeat in (1,2,3):
        cell=old/f'validation_v1/cells/single-session_qwen_margin-benefit_r{repeat}'
        raw=old/f'validation_v1/cells/single-session_qwen_raw-order_r{repeat}'
        rows=read(cell/'raw.jsonl');baseline=read(raw/'raw.jsonl')
        w=next(x for x in rows if x['row_type']=='future' and x['session_id']==sid and x['turn_id']==1)
        future=next(x for x in rows if x['row_type']=='future' and x['session_id']==sid and x['turn_id']==7)
        query=w['query_scope']
        request=next(x for x in rows if x['row_type']=='verification_request' and x['payload']['verify_start_token']>0 and
                     x['reference_prompt_ids_sha256']==w['prompt_ids_sha256'])
        raw7=next(x for x in baseline if x['row_type']=='future' and x['session_id']==sid and x['turn_id']==7)
        identities.append({'raw_t1':w['prompt_token_ids'],'raw_t7':raw7['prompt_token_ids'],
                           'candidate_t1':request['payload']['prompt_token_ids'][:request['payload']['verify_start_token']],
                           'candidate_t7':future['prompt_token_ids']})
        sources.append({'repeat':repeat,'policy_raw_sha256':sha(cell/'raw.jsonl'),'baseline_raw_sha256':sha(raw/'raw.jsonl'),
                        'query_scope':query,'reference_output_ids':w['output_token_ids'],'raw_future_output_ids':raw7['output_token_ids']})
    if not all(x==identities[0] for x in identities):raise ValueError('Historical prompt IDs differ across repeats')
    base.mkdir(parents=True)
    with (base/'sessions.jsonl').open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(sample,ensure_ascii=False)+'\n')
    record={'schema_version':'tsc-r4.known-prompt-identity.v1','session_id':sid,
            'prompt_ids':identities[0],'historical_sources':sources,'all_three_historical_prompt_geometries_equal':True,
            'selection_is_known_failure_development_not_unseen_validation':True}
    (base/'actual_prompt_ids_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'known_source':sample['revision_source_group'],'prompt_tokens':{k:len(v) for k,v in identities[0].items()},
                      'sessions_sha256':sha(base/'sessions.jsonl'),'prompt_evidence_sha256':sha(base/'actual_prompt_ids_v1.json')}))


if __name__=='__main__':main()
