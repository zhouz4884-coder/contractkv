"""CPU audit that final chat-template text retains critical code/query fields."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
for key,value in {'USE_TORCH':'0','USE_TF':'0','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                   'TOKENIZERS_PARALLELISM':'false','CUDA_VISIBLE_DEVICES':''}.items():os.environ[key]=value
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,piece_identity
from scripts.tsc_revision_r4_table_I_reconstruction_v2 import annotated_user
from transformers import AutoTokenizer


def main():
    base=Path('results/tsc_revision_r4');root=base/'input_fidelity_validation_v1'
    output=base/'independent_input_final_chat_field_audit_v1.json'
    assert not output.exists()
    freeze=json.loads((root/'freeze.json').read_text(encoding='utf-8'));config=freeze['protocol']
    samples=[json.loads(line) for line in Path(config['input_files']['template-fanout']).open(encoding='utf-8')]
    generation=json.loads(Path(config['generation_protocol']).read_text(encoding='utf-8'))
    catalog=json.loads(Path(config['selected_catalog']).read_text(encoding='utf-8'))
    registry=json.loads((base/'model_registry_v1.json').read_text(encoding='utf-8'))
    tokenizers={row['model']:AutoTokenizer.from_pretrained(base/'cpu_tokenizer_snapshots_v1'/row['key'],local_files_only=True) for row in registry['models']}
    counts=Counter();examples=[]
    with installed_adapter():
        for model,tokenizer in tokenizers.items():
            for original in samples:
                for tenant in range(10):
                    sample=deepcopy(original);sample['shared_template_id']=sample['revision_session_id'];sample['revision_session_id']+=f'-tenant{tenant:02d}'
                    args=SimpleNamespace(protocol=generation,experiment='free-generation',output_budget=0,model_identity=model,policy_hash='CPU-final-chat-fields')
                    for turn in range(10):
                        case,raw,_,_,_=prepare(args,sample,turn)
                        level=catalog['models'][model]['template-fanout'][sample['revision_family']]['level']
                        for view,selected in [('raw','L0'),('selected_candidate',level)]:
                            order=layout_for_level(case,selected,generation['layout']['ladder'])['topological_order']
                            user,spans=annotated_user(order,case['segments'],True)
                            messages=[raw[0],{'role':'user','content':user}]
                            if selected=='L0':assert messages==raw
                            rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                            if user in rendered:start=rendered.index(user);left=0;right=len(user)
                            else:
                                stripped=user.strip();assert stripped in rendered
                                left=len(user)-len(user.lstrip());right=len(user.rstrip());start=rendered.index(stripped)-left
                            by_id={row['segment_id']:row for row in case['segments']}
                            for span in spans:
                                if span['type'] not in ('CODE_PREFIX','USER_QUERY'):continue
                                lo,hi=span['body_start_character'],span['body_end_character'];original_text=by_id[span['segment_id']]['text']
                                kept_lo=max(lo,left);kept_hi=min(hi,right)
                                if kept_hi<kept_lo:kept_hi=kept_lo
                                removed_prefix=original_text[:max(0,kept_lo-lo)]
                                removed_suffix=original_text[max(0,kept_hi-lo):]
                                assert not (removed_prefix+removed_suffix).strip(),'Critical nonwhitespace field content lost by chat template'
                                if span['type']=='CODE_PREFIX':assert lo>=left and hi<=right,'Code prefix bytes trimmed by final chat template'
                                assert rendered[start+kept_lo:start+kept_hi]==original_text[max(0,kept_lo-lo):max(0,kept_hi-lo)]
                            used_code_groups=set()
                            for segment in sample['segments']:
                                if segment['type']=='CODE_PREFIX':
                                    groups={piece_identity(row['segment_id'])[0] for row in spans if row['type']=='CODE_PREFIX'}
                                    matched=[]
                                    for group in groups-used_code_groups:
                                        pieces=[row for row in spans if row['type']=='CODE_PREFIX' and piece_identity(row['segment_id'])[0]==group]
                                        joined=''.join(by_id[row['segment_id']]['text'] for row in pieces)
                                        if joined==segment['text']:matched.append((group,pieces))
                                    assert matched,'Original CODE_PREFIX body has no matching declared prepared group'
                                    group,pieces=matched[0];used_code_groups.add(group)
                                    first=min(row['body_start_character'] for row in pieces)
                                    assert rendered[start+first:start+first+len(segment['text'])]==segment['text'],'Whole original code prefix not contiguous in final model input'
                                    counts[model+'|'+view+'|complete_CODE_PREFIX']+=1
                            counts[model+'|'+view+'|requests']+=1
                            if left or right<len(user):
                                counts[model+'|'+view+'|user_edge_whitespace_trimmed']+=1
                                if len(examples)<12:examples.append({'model':model,'source_group':sample['revision_source_group'],'turn':turn,'view':view,'leading_whitespace_characters':left,'trailing_whitespace_characters':len(user)-right})
    result={'schema_version':'tsc-r4.final-chat-critical-fields-CPU-audit.v1','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'primary_freeze_sha256':hashlib.sha256((root/'freeze.json').read_bytes()).hexdigest(),
            'all_1800_model_source_tenant_turn_variants_checked_both_raw_and_candidate':True,
            'complete_CODE_PREFIX_bytes_retained_contiguously_after_final_chat_template':True,
            'query_nonwhitespace_characters_unchanged':True,'counts':dict(counts),'edge_trim_examples':examples,
            'new_GPU_requests':0,'this_is_not_actual_API_ID_or_model_quality_evidence':True,
            'actual_service_ID_audit_remains_separate':True}
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'CPU_final_chat_fields':'PASS','variants':1800,'views':3600}))


if __name__=='__main__':main()
