"""Reconstruct stable-content/native-APC accounting from actual raw requests.

This defines new reproducible measurements, not the missing original Table I
provenance. Registered stable body text excludes headers and chat control text.
Every reconstructed prompt must equal the actual logged API token IDs.
"""
import argparse
from collections import defaultdict
from contextlib import nullcontext
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from statistics import mean
from types import SimpleNamespace
for name,value in {'USE_TORCH':'0','USE_TF':'0','HF_HUB_OFFLINE':'1',
                   'TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false','CUDA_VISIBLE_DEVICES':''}.items():
    os.environ[name]=value
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,piece_identity
from transformers import AutoTokenizer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in Path(path).open(encoding='utf-8') if line.strip()]


def merge_ranges(ranges):
    result=[]
    for start,end in sorted(ranges):
        if result and start<=result[-1][1]:result[-1][1]=max(result[-1][1],end)
        else:result.append([start,end])
    return result


def annotated_user(order,segments,faithful):
    by_id={row['segment_id']:row for row in segments};groups=[]
    for sid in order:
        segment=by_id[sid]
        base,index=piece_identity(sid)
        old_base,old_index=piece_identity(groups[-1][-1]['segment_id']) if groups else (None,None)
        if faithful and groups and index is not None and old_index is not None and base==old_base and index==old_index+1 and segment['segment_type']==groups[-1][-1]['segment_type']:
            groups[-1].append(segment)
        else:groups.append([segment])
    content='';spans=[]
    for group in groups:
        if content:content+='\n\n'
        first=group[0];base,index=piece_identity(first['segment_id'])
        heading_id=base if faithful and index==0 else first['segment_id']
        content+=f"[{first['segment_type']}:{heading_id}]\n"
        for row in group:
            start=len(content);content+=row['text']
            stable=(row['cache_stability']==1.0 and row['segment_type'] not in {'USER_QUERY','TOOL_OBS','CHAT_HISTORY','SCRATCHPAD'})
            spans.append({'segment_id':row['segment_id'],'type':row['segment_type'],
                          'body_start_character':start,'body_end_character':len(content),
                          'declared_cache_stability':row['cache_stability'],'counted_stable_body':stable,
                          'text_sha256':hashlib.sha256(row['text'].encode()).hexdigest()})
    return content,spans


def summarize(rows):
    prompt=sum(row['prompt_tokens'] for row in rows);stable=sum(row['stable_body_tokens'] for row in rows)
    hit=sum(row['native_prefix_hit_tokens'] for row in rows);stable_hit=sum(row['stable_body_native_hit_tokens'] for row in rows)
    by_source=defaultdict(list)
    for row in rows:by_source[row['source_group']].append(row)
    source_ratios=[sum(row['stable_body_tokens'] for row in values)/sum(row['prompt_tokens'] for row in values) for values in by_source.values()]
    return {'requests':len(rows),'sources':len(by_source),'all_prompt_tokens':prompt,'stable_body_tokens':stable,
            'native_prefix_hit_tokens':hit,'stable_body_native_hit_tokens':stable_hit,
            'stable_body_fraction_token_weighted':stable/prompt,
            'stable_body_fraction_source_macro':mean(source_ratios),
            'native_hit_fraction_of_all_prompt_tokens':hit/prompt,
            'stable_native_recovery_fraction_of_stable_body_tokens':stable_hit/stable if stable else None,
            'stable_native_recovered_fraction_of_all_prompt_tokens':stable_hit/prompt,
            'stable_boundary_tokens_excluded':sum(row['stable_boundary_tokens_excluded'] for row in rows)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output-prefix',type=Path,required=True)
    parser.add_argument('--tokenizer-root',type=Path,required=True);args=parser.parse_args()
    output=Path(str(args.output_prefix)+'.json');csv_path=Path(str(args.output_prefix)+'.csv')
    assert not output.exists() and not csv_path.exists(),'Preserve all reconstruction attempts'
    primary=json.loads((args.root/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    assert primary['execution_complete']
    freeze=json.loads((args.root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol']
    for item in freeze['files']:assert sha(item['path'])==item['sha256']
    generation=json.loads((args.root/'source_snapshot'/config['generation_protocol']).read_text(encoding='utf-8'))
    inputs={study:{row['revision_session_id']:row for row in read(args.root/'source_snapshot'/path)} for study,path in config['input_files'].items()}
    registry=json.loads(Path('results/tsc_revision_r4/model_registry_v1.json').read_text(encoding='utf-8'))
    tokenizers={row['model']:AutoTokenizer.from_pretrained(args.tokenizer_root/row['key'],local_files_only=True,use_fast=True) for row in registry['models']}
    faithful=config.get('input_adapter')=='task-fidelity-contiguous-segment-text-v2'
    rows=[];provenance=[];representatives={};cache={}
    with installed_adapter() if faithful else nullcontext():
        for summary_path in sorted((args.root/'cells').glob('*/summary.json')):
            summary=json.loads(summary_path.read_text(encoding='utf-8'))
            if summary['policy']!='raw-order':continue
            raw=summary_path.with_name('raw.jsonl');assert summary['execution_complete'] and sha(raw)==summary['raw_file_sha256']
            provenance.append({'cell':summary_path.parent.name,'raw_sha256':sha(raw)})
            for row in read(raw):
                if row['row_type'] not in ('warm','future'):continue
                namespace=row['certificate_namespace'] if config['studies'][row['study']]>1 else row['session_id']
                sample=deepcopy(inputs[row['study']][namespace]);sample['revision_session_id']=row['session_id']
                if config['studies'][row['study']]>1:sample['shared_template_id']=namespace
                ids=row['prompt_token_ids'];id_hash=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
                key=(row['model'],namespace,id_hash)
                if key not in cache:
                    arguments=SimpleNamespace(protocol=generation,experiment='free-generation',output_budget=0,
                                              model_identity=row['model'],policy_hash=sha(args.root/'freeze.json'))
                    case,messages,_,_,_=prepare(arguments,sample,row['turn_id'])
                    order=layout_for_level(case,'L0',generation['layout']['ladder'])['topological_order']
                    user,spans=annotated_user(order,case['segments'],faithful);assert user==messages[1]['content']
                    tokenizer=tokenizers[row['model']]
                    rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                    encoded=tokenizer(rendered,add_special_tokens=False,return_offsets_mapping=True)
                    assert list(encoded['input_ids'])==ids,'Reconstructed tokenizer IDs differ from actual API IDs'
                    user_start=rendered.index(user)
                    stable_ranges=merge_ranges([(span['body_start_character']+user_start,span['body_end_character']+user_start) for span in spans if span['counted_stable_body']])
                    flags=bytearray(len(ids));boundaries=0;special=set(tokenizer.all_special_ids)
                    for i,(start,end) in enumerate(encoded['offset_mapping']):
                        if end<=start or ids[i] in special:continue
                        fully=any(a<=start and end<=b for a,b in stable_ranges)
                        overlap=any(end>a and start<b for a,b in stable_ranges)
                        flags[i]=int(fully);boundaries+=int(overlap and not fully)
                    cache[key]=(flags,boundaries)
                    representative_key=row['model']+'|'+row['source_group']
                    representatives.setdefault(representative_key,{'model':row['model'],'source_group':row['source_group'],
                        'request_id':row['request_id'],'actual_prompt_token_ids':ids,'actual_IDs_sha256':id_hash,
                        'user_start_character_in_chat_template':user_start,'raw_segment_order':order,
                        'segment_body_map':spans,'stable_ranges_in_chat_characters':stable_ranges})
                flags,boundaries=cache[key];hit=row['prefix_hit_tokens']
                assert 0<=hit<=len(ids) and len(flags)==len(ids)
                rows.append({'cell':summary_path.parent.name,'model':row['model'],'study':row['study'],'repeat':row['repeat'],
                             'source_group':row['source_group'],'family':row['family'],'session_id':row['session_id'],
                             'turn_id':row['turn_id'],'row_type':row['row_type'],'request_id':row['request_id'],
                             'actual_prompt_IDs_sha256':id_hash,'prompt_tokens':len(ids),'stable_body_tokens':flags.count(1),
                             'native_prefix_hit_tokens':hit,'stable_body_native_hit_tokens':flags[:hit].count(1),
                             'stable_boundary_tokens_excluded':boundaries,'actual_IDs_verified':True})
    assert rows
    groups=defaultdict(list)
    for row in rows:
        for population in ('all_business',row['row_type']):
            for family in ('ALL',row['family']):groups[(row['model'],row['study'],population,family)].append(row)
    summaries=[{'model':key[0],'study':key[1],'population':key[2],'family':key[3],**summarize(values)} for key,values in sorted(groups.items())]
    output.parent.mkdir(parents=True,exist_ok=True)
    with csv_path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'schema_version':'tsc-r4.TableI-new-reproducible-reconstruction.v1','source_sha256':sha(__file__),
            'root':args.root.as_posix(),'freeze_sha256':sha(args.root/'freeze.json'),'faithful':faithful,
            'input_files_sha256':{path:sha(args.root/'source_snapshot'/path) for path in config['input_files'].values()},
            'cell_provenance':provenance,'request_csv_sha256':sha(csv_path),'summaries':summaries,
            'one_actual_ID_and_segment_map_per_model_source':list(representatives.values()),
            'new_GPU_requests':0,'is_original_Table_I_numeric_reproduction':False,
            'definitions':{'stable':'Registered segment body tokens wholly inside cache_stability==1 text, excluding query/observation/history/scratch, injected headings, outer chat control/system wrapper and boundary-crossing tokens.',
                           'prompt_denominator':'All actual API input IDs, including headers and special tokens.',
                           'native_stable_recovery':'Counted stable body token positions before the actual native prefix-hit boundary, divided by counted stable body tokens.',
                           'warm':'Actual tenant turn-zero business requests, not infrastructure warmup; reported separately.',
                           'source_macro':'Mean of source-specific token-weighted stable fractions; pooled token ratio separately reported.'},
            'limits':['Declared stability is a manifest assumption, not proof that content is public.',
                      'Controlled trace statistics do not measure production frequency.',
                      'These explicit new denominators cannot recover or validate the missing original percentage provenance.']}
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'actual_business_requests_reconstructed':len(rows),'model_source_maps':len(representatives),
                      'summaries':len(summaries),'new_GPU_requests':0}))


if __name__=='__main__':
    main()
