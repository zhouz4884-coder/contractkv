"""CPU check of one topology-matched historical candidate, not a Table-I recovery.

The candidate is selected because its frozen manifest has 25 source-disjoint
sessions per family, not because of its numeric results. Uses the launcher's
8192-token / 1500-word settings unchanged. Never sends a model request.
"""
from pathlib import Path
from collections import defaultdict, Counter
import argparse
import hashlib
import json
import os
import statistics
import sys

os.environ.update(USE_TORCH='0', USE_TF='0', HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transformers import AutoTokenizer
from scripts.tsc_open_loop_service import make_case, service_messages
from scripts.phase12e_cache_aware_posc import compile_static_policy


def main():
    p=argparse.ArgumentParser();p.add_argument('--sessions',type=Path,required=True)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--tokenizer',required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    samples=[json.loads(l) for l in args.sessions.open(encoding='utf-8') if l.strip()]
    observed=[json.loads(l) for l in args.raw.open(encoding='utf-8') if l.strip()]
    assert len(samples)==125 and len(observed)==1125
    assert set(Counter(r['tsc_family'] for r in samples).values())=={25}
    by_id={r['tsc_session_id']:r for r in samples};tokenizer=AutoTokenizer.from_pretrained(
        args.tokenizer,local_files_only=True,trust_remote_code=False)
    bases={sid:make_case(sample,0,tokenizer,8192,1500) for sid,sample in by_id.items()}
    output=[]
    for record in observed:
        sid=record['session_id'];case=make_case(by_id[sid],int(record['turn_id']),tokenizer,8192,1500,base_case=bases[sid])
        layout=compile_static_policy(case['segments'],'raw-order');order=layout['topological_order']
        messages=service_messages(case,order);rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        user=messages[1]['content'];assert user in rendered;offset=rendered.index(user)
        position=0;ranges=[];by_segment={r['segment_id']:r for r in case['segments']}
        for i,segment_id in enumerate(order):
            segment=by_segment[segment_id]
            if i:position+=2
            position+=len(f"[{segment['segment_type']}:{segment_id}]\n")
            start=position;position+=len(segment['text'])
            if segment['cache_stability']==1 and segment['segment_type'] not in {'USER_QUERY','TOOL_OBS','CHAT_HISTORY','SCRATCHPAD'}:
                ranges.append((offset+start,offset+position))
        encoded=tokenizer(rendered,add_special_tokens=False,return_offsets_mapping=True)
        assert len(encoded['input_ids'])==int(record['prompt_tokens']),sid
        stable=[i for i,(a,b) in enumerate(encoded['offset_mapping']) if b>a and any(x<=a and b<=y for x,y in ranges)]
        hit=int(record['prefix_hit_tokens'])
        output.append({'family':by_id[sid]['tsc_family'],'session_id':sid,'turn':int(record['turn_id']),
            'prompt_tokens':len(encoded['input_ids']),'stable_body_tokens':len(stable),
            'native_prefix_hit_tokens':hit,'stable_native_hit_tokens':sum(i<hit for i in stable)})
    summaries=[]
    for family in sorted({r['family'] for r in output}):
        rows=[r for r in output if r['family']==family]
        n=sum(r['prompt_tokens'] for r in rows);stable=sum(r['stable_body_tokens'] for r in rows)
        summaries.append({'family':family,'requests':len(rows),'sources':len({r['session_id'] for r in rows}),
            'stable_body_ratio_pct':100*stable/n,
            'total_native_hit_ratio_pct':100*sum(r['native_prefix_hit_tokens'] for r in rows)/n,
            'stable_recovery_pct':100*sum(r['stable_native_hit_tokens'] for r in rows)/stable})
    result={'candidate':'Frozen service-locality g1 / Qwen / r1 / 80% load / native APC',
        'selection_reason':'125 sessions: 25 distinct source groups per family, matching the old table sample topology',
        'future_requests':len(output),'prompt_lengths_match_observed':True,
        'actual_full_prompt_IDs_recorded':False,'new_GPU_requests':0,
        'is_original_TableI_reproduction':False,'summaries':summaries,
        'limits':['Offline stable-body attribution is joined to measured prompt lengths and hit counts; full old prompt IDs are unavailable.',
                  'This candidate uses a marker service task and future turns 1-9; it is not silently substituted for the original motivation statistic.'],
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
