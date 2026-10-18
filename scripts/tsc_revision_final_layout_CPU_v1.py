"""Offline layout ladder on frozen faithful inputs, with actual-ID anchors.

No model forward, candidate admission, counterfactual cache hit or speed claim.
Token displacement matches only tokens wholly inside unchanged segment text by
(segment, character offsets, token ID); headers and boundary retokenization are
explicitly excluded from that displacement metric.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(ids): return hashlib.sha256(json.dumps(ids).encode()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def quantile(a,q):
    a=sorted(a)
    if not a:return None
    p=(len(a)-1)*q;i=int(p);return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(p-i)


def render_spans(order,segments,piece_identity,renderer):
    by_id={x['segment_id']:x for x in segments};groups=[]
    for sid in order:
        seg=by_id[sid];base,index=piece_identity(sid)
        prev=groups[-1][-1] if groups else None
        pb,pi=piece_identity(prev['segment_id']) if prev else (None,None)
        if prev and index is not None and pi is not None and base==pb and index==pi+1 and seg['segment_type']==prev['segment_type']:
            groups[-1].append(seg)
        else:groups.append([seg])
    body='';spans={}
    for group in groups:
        if body:body+='\n\n'
        first=group[0];base,index=piece_identity(first['segment_id'])
        body+=f"[{first['segment_type']}:{base if index==0 else first['segment_id']}]\n"
        for seg in group:
            start=len(body);body+=seg['text'];spans[seg['segment_id']]=(start,len(body))
    assert body==renderer(order,segments),'Span reconstruction must equal the archived renderer exactly'
    return body,spans


def main(root,output):
    if output.exists():raise FileExistsError('Do not overwrite an analysis')
    os.environ['CUDA_VISIBLE_DEVICES']=''
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    faithful=root/'results/tsc_revision_r4/input_fidelity_validation_v1'
    snapshot=faithful/'source_snapshot';freeze=read(faithful/'freeze.json')
    frozen={x['path']:x['sha256'] for x in freeze['files']}
    sys.path.insert(0,str(snapshot))
    from scripts import tsc_revision_live as original
    from scripts.tsc_revision_r1r_live import prepare
    from scripts.phase22_llama_layout_ladder import layout_for_level, VOLATILE_TYPES
    from scripts.phase12_posc_layout_compiler import validate_topological_order
    from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter, piece_identity, ordered_text_preserving_segments
    from transformers import AutoTokenizer

    source_inventory={}
    for name,module in list(sys.modules.items()):
        if name.startswith('scripts.') and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            if path.suffix!='.py':continue
            rel=path.relative_to(snapshot).as_posix()
            assert rel in frozen and sha(path)==frozen[rel],f'Unfrozen imported source {name}'
            source_inventory[rel]=sha(path)
    protocol=read(snapshot/freeze['protocol']['generation_protocol'])
    input_path=snapshot/freeze['protocol']['input_files']['template-fanout']
    assert sha(input_path)==frozen[input_path.relative_to(snapshot).as_posix()]
    samples=[json.loads(x) for x in input_path.read_text(encoding='utf-8').splitlines() if x.strip()]
    assert len(samples)==6
    records=[];segment_records=[];anchors=[];tokenizer_inventory={}
    for model,identity in [('qwen','Qwen3-8B'),('mistral','Mistral-7B-Instruct-v0.3'),('llama','Llama-3.1-8B-Instruct')]:
        runtime=read(faithful/'cells'/f'template-fanout_{model}_raw-order_r1/runtime_manifest.json')
        tokenizer_path=root/'results/tsc_revision_r4/cpu_tokenizer_snapshots_v1'/model
        for entry in runtime['tokenizer_and_generation_files']:
            assert sha(tokenizer_path/entry['file'])==entry['sha256']
        tokenizer_inventory[model]=runtime['tokenizer_and_generation_files']
        tok=AutoTokenizer.from_pretrained(str(tokenizer_path),local_files_only=True)
        assert tok.is_fast,'Offset metric needs the actual fast tokenizer'
        actual={}
        p=faithful/'cells'/f'template-fanout_{model}_raw-order_r1/raw.jsonl'
        with p.open(encoding='utf-8') as f:
            for line in f:
                row=json.loads(line)
                if row['row_type'] in ('warm','future') and row['session_id'].endswith('-tenant00'):
                    actual[row['session_id'],int(row['turn_id'])]=row['prompt_token_ids']
        assert len(actual)==60
        args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,
                             model_identity=identity,policy_hash=runtime['freeze_sha256'])
        with installed_adapter():
            for source_sample in samples:
                sample=deepcopy(source_sample)
                sample['shared_template_id']=sample['revision_session_id']
                sample['revision_session_id']+='-tenant00'
                for turn in range(10):
                    case,raw_messages,maximum,budget,scope=prepare(args,sample,turn)
                    by_id={x['segment_id']:x for x in case['segments']}
                    raw_token_map=None;raw_segment_positions=None
                    for level in ('L0','L1','L2','L3'):
                        layout=layout_for_level(case,level,protocol['layout']['ladder'])
                        order=layout['topological_order'];violations=validate_topological_order(order,case['segments'])
                        body,spans=render_spans(order,case['segments'],piece_identity,ordered_text_preserving_segments)
                        messages=[raw_messages[0],dict(role='user',content=body)]
                        ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
                        text=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                        encoded=tok(text,add_special_tokens=False,return_offsets_mapping=True)
                        assert encoded['input_ids']==ids,'Offsets must correspond to actual chat-template IDs'
                        trim_left=trim_right=0
                        if text.count(body)==1:
                            body_start=text.index(body)
                        else:
                            stripped=body.strip()
                            assert stripped and text.count(stripped)==1,(model,sample['revision_source_group'],turn,level,'user body is not an exact or whitespace-trimmed substring')
                            trim_left=len(body)-len(body.lstrip());trim_right=len(body)-len(body.rstrip())
                            body_start=text.index(stripped)-trim_left
                        offsets=encoded['offset_mapping'];starts=[x[0] for x in offsets]
                        assert starts==sorted(starts),'Non-monotonic offsets need explicit handling'
                        stable=[]
                        for sid in order:
                            if by_id[sid]['segment_type'] in VOLATILE_TYPES:break
                            stable.append(sid)
                        prefix_messages=[raw_messages[0],dict(role='user',content=ordered_text_preserving_segments(stable,case['segments']))]
                        prefix=tok.apply_chat_template(prefix_messages,tokenize=True,add_generation_prompt=False,return_dict=False)
                        end=0
                        for a,b in zip(ids,prefix):
                            if a!=b:break
                            end+=1
                        token_map={};segment_positions={}
                        for sid,(left,right) in spans.items():
                            left+=body_start;right+=body_start
                            for i in range(bisect_left(starts,left),len(starts)):
                                a,b=offsets[i]
                                if a>=right:break
                                if b>a and a>=left and b<=right:
                                    key=(sid,a-left,b-left,ids[i]);assert key not in token_map
                                    token_map[key]=i
                                    segment_positions.setdefault(sid,[]).append(i)
                        if level=='L0':
                            assert ids==actual[sample['revision_session_id'],turn], 'L0 must match archived served Prompt IDs'
                            anchors.append(dict(model=model,source=sample['revision_source_group'],turn=turn,prompt_tokens=len(ids),sha256=digest(ids)))
                            raw_token_map=token_map;raw_segment_positions=segment_positions
                        matched=set(token_map)&set(raw_token_map)
                        displacement=[token_map[k]-raw_token_map[k] for k in matched]
                        moved=[x for x in displacement if x]
                        for sid in order:
                            own=[k for k in matched if k[0]==sid]
                            dd=[token_map[k]-raw_token_map[k] for k in own]
                            segment_records.append(dict(model=model,source=sample['revision_source_group'],turn=turn,level=level,
                                segment_id=sid,segment_type=by_id[sid]['segment_type'],raw_segment_index=case['segments'].index(by_id[sid]),
                                new_segment_index=order.index(sid),raw_interior_tokens=len(raw_segment_positions.get(sid,[])),
                                candidate_interior_tokens=len(segment_positions.get(sid,[])),exact_matched_interior_tokens=len(own),
                                mean_signed_displacement_tokens=statistics.fmean(dd) if dd else None,
                                mean_absolute_displacement_tokens=statistics.fmean(abs(x) for x in dd) if dd else None))
                        records.append(dict(model=model,family=sample['revision_family'],source=sample['revision_source_group'],turn=turn,
                            level=level,level_fraction=protocol['layout']['ladder'][level],dependency_legal=not violations,
                            inherited_maximum=maximum,within_inherited_maximum=int(level[1:])<=int(maximum[1:]),
                            prompt_tokens=len(ids),output_budget=budget,within_16K=len(ids)+budget<=16384,
                            chat_template_user_leading_trim_chars=trim_left,chat_template_user_trailing_trim_chars=trim_right,
                            rendered_stable_prefix_tokens=end,block_aligned_prefix_ceiling_tokens=(end//16)*16,
                            prefix_ceiling_full_blocks=end//16,raw_segment_text_interior_tokens=len(raw_token_map),
                            exact_matched_interior_tokens=len(matched),matched_tokens_moved=len(moved),
                            mean_absolute_displacement_tokens=statistics.fmean(abs(x) for x in displacement),
                            p95_absolute_displacement_tokens=quantile([abs(x) for x in displacement],.95),
                            prompt_ids_sha256=digest(ids),scope_digest=scope))
    assert len(records)==720 and len(anchors)==180
    output.mkdir(parents=True)
    for name,data in [('layout_metrics_v1.csv',records),('segment_displacement_v1.csv',segment_records)]:
        with (output/name).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    groups=defaultdict(list)
    for row in records:groups[row['model'],row['family'],row['level']].append(row)
    aggregate=[]
    for (model,family,level),rs in sorted(groups.items()):
        aggregate.append(dict(model=model,family=family,level=level,source_count=len({x['source'] for x in rs}),
            prompts=len(rs),dependency_legal=sum(x['dependency_legal'] for x in rs),
            eligible_family_maximum_count=sum(x['within_inherited_maximum'] for x in rs),
            within_16K_count=sum(x['within_16K'] for x in rs),
            mean_stable_prefix_tokens=statistics.fmean(x['rendered_stable_prefix_tokens'] for x in rs),
            mean_full_prefix_blocks=statistics.fmean(x['prefix_ceiling_full_blocks'] for x in rs),
            mean_absolute_displacement_tokens=statistics.fmean(x['mean_absolute_displacement_tokens'] for x in rs)))
    result=dict(status='complete_CPU_only',new_GPU_requests=0,actual_raw_prompt_ID_anchors=len(anchors),layout_prompts=len(records),
        source_count=6,source_count_per_family=3,models=3,turns_per_source=10,ladder=protocol['layout']['ladder'],
        faithful_freeze_sha256=sha(faithful/'freeze.json'),input_sha256=sha(input_path),source_inventory=source_inventory,
        tokenizer_inventory=tokenizer_inventory,aggregates=aggregate,anchors=anchors,
        exclusions='Headers, chat controls and tokens crossing segment text boundaries are excluded from the displacement metric; full rendered prefix lengths use all actual prompt IDs.',
        boundary='Offline structural opportunities only, not candidate qualification, actual prefix residency/hits or GPU performance. R4 online uses one inherited candidate, not this four-level descent. Levels beyond inherited family maximum remain unauthorized.')
    with (output/'summary_v1.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(layouts=len(records),actual_ID_anchors=len(anchors),segments=len(segment_records),output=str(output))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
