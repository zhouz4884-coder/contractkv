"""Select the earliest accepted primary case and its first compiled future.

The compact plotting bundle carries exact selected records and upstream file/
line identities. Re-extraction from the archived full logs remains possible.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CELL='results/tsc_revision_r4/input_fidelity_validation_v1/cells/template-fanout_qwen_risk-tail_r1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def check(excerpt):
    records={x['role']:x['record'] for x in excerpt['selected_records']}
    for x in excerpt['selected_records']:assert digest(x['record'])==x['canonical_record_sha256']
    w,p,v,c,f,m=[records[k] for k in ('raw_witness','verification_request','verification_response',
                                     'certificate_record','first_compiled_future','future_native_metric')]
    p=p['payload'];v=v['response']
    assert w['witness_requested'] and w['witness_available'] and w['finish_reason']=='stop'
    assert p['reference_answer_ids']+[p['terminal_stop_token_id']]==w['output_token_ids']
    assert v['verify_decision']=='PASS' and v['txn_state']=='COMMITTED' and v['certificate_issued']
    assert c['certificate_issued'] and c['query_scope']==w['query_scope']==f['query_scope']
    assert w['certificate_namespace']==c['certificate_namespace']==f['certificate_namespace']
    n=v['committed_tokens'];assert n>0 and n==v['committed_full_blocks']*m['block_size']
    stable=c['stable_prefix_tokens'];assert stable>=n
    assert digest(p['prompt_token_ids'][:stable])==c['stable_prefix_hash']
    assert p['prompt_token_ids'][:stable]==f['prompt_token_ids'][:stable]
    assert f['effective_level']!='L0' and w['output_token_ids']==f['output_token_ids']
    assert m['request_id']==f['request_id'] and m['initial_prefill_observation']
    assert m['prefix_hit_tokens']==f['prefix_hit_tokens']>=n
    assert digest(w['prompt_token_ids'])==w['prompt_ids_sha256']
    assert digest(f['prompt_token_ids'])==f['prompt_ids_sha256']
    return {'model':w['model'],'source_group':w['source_group'],'query_scope':w['query_scope'],
            'raw_request_id':w['request_id'],'verification_request_id':v['request_id'],
            'future_request_id':f['request_id'],'raw_turn':w['turn_id'],'future_turn':f['turn_id'],
            'output_token_ids':w['output_token_ids'],'output_ID_count':len(w['output_token_ids']),
            'output_ID_SHA256':digest(w['output_token_ids']),
            'verification_decision':v['verify_decision'],'txn_state':v['txn_state'],
            'committed_tokens':n,'committed_full_blocks':v['committed_full_blocks'],
            'later_native_hit_tokens':m['prefix_hit_tokens'],'actual_identical_output_IDs':True,
            'certificate_hash':v['certificate_hash'],
            'publication_evidence':'Live verifier COMMITTED response, positive committed block count, and later matching-prefix native hit; no standalone BlockStored event claimed.'}


def extract(output):
    raw=ROOT/CELL/'raw.jsonl';metrics=ROOT/CELL/'metrics.jsonl'
    if not raw.exists():
        assert output.exists(),'Restore archived full logs or the exact trace excerpt from plot_sources_v7.zip'
        e=json.loads(output.read_text(encoding='utf-8'));return e,check(e)
    raw_lines=raw.read_bytes().splitlines(keepends=True)
    metric_lines=metrics.read_bytes().splitlines(keepends=True)
    rows=[(i+1,json.loads(line),line) for i,line in enumerate(raw_lines) if line.strip()]
    ms=[(i+1,json.loads(line),line) for i,line in enumerate(metric_lines) if line.strip()]
    c=next(x for x in rows if x[1]['row_type']=='verification' and x[1]['certificate_issued'])
    rid=c[1]['request_id']
    p=next(x for x in rows if x[1]['row_type']=='verification_request' and x[1]['request_id']==rid)
    v=next(x for x in rows if x[1]['row_type']=='verification_response' and x[1]['request_id']==rid)
    w=next(x for x in rows if x[1]['row_type'] in ('warm','future') and x[1]['witness_requested']
           and x[1]['certificate_namespace']==c[1]['certificate_namespace'] and x[1]['query_scope']==c[1]['query_scope'])
    f=next(x for x in rows if x[1]['row_type']=='future' and x[1]['effective_level']!='L0'
           and x[1]['certificate_namespace']==c[1]['certificate_namespace'] and x[1]['query_scope']==c[1]['query_scope'])
    m=next(x for x in ms if x[1]['request_id']==f[1]['request_id'] and x[1]['initial_prefill_observation'])
    assert w[0]<p[0]<v[0]<=c[0]<f[0]
    selected=[]
    for role,item,name in [('raw_witness',w,'raw.jsonl'),('verification_request',p,'raw.jsonl'),
                          ('verification_response',v,'raw.jsonl'),('certificate_record',c,'raw.jsonl'),
                          ('first_compiled_future',f,'raw.jsonl'),('future_native_metric',m,'metrics.jsonl')]:
        selected.append({'role':role,'source_path':CELL+'/'+name,'line_1_based':item[0],
                         'original_line_sha256':hashlib.sha256(item[2]).hexdigest(),
                         'canonical_record_sha256':digest(item[1]),'record':item[1]})
    e={'schema_version':'contractkv.figure-measured-trace.v7',
       'selection':'First issued certificate in file order; its first raw witness and first compiled future in that same namespace/query scope. No selection on score or output equality.',
       'upstream_files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,
                          'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (raw,metrics)],
       'selected_records':selected,'is_new_GPU_run':False}
    data=(json.dumps(e,ensure_ascii=False,indent=2)+'\n').encode()
    if output.exists():assert output.read_bytes()==data,'Preserve existing trace extraction'
    else:output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
    return e,check(e)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Paper/figures/revision_20261017_v7/trace_log_excerpt_v7.json')
    a=p.parse_args();_,summary=extract(a.output)
    print(json.dumps({k:summary[k] for k in ('output_ID_count','committed_full_blocks','later_native_hit_tokens','actual_identical_output_IDs')}))


if __name__=='__main__':main()
