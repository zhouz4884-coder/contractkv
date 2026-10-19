"""Locate only the artificial marker using the exact registered tokenizers."""
import os
for k,v in dict(CUDA_VISIBLE_DEVICES='',USE_TORCH='0',USE_TF='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1').items():os.environ[k]=v
import argparse
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer


def main(root):
    study=root/'results/tsc_authorization_task_repair_20261019'
    output=study/'marker_token_positions_v1.json';assert not output.exists()
    cases=json.loads((study/'inputs_v1/cases_by_model_v1.json').read_text(encoding='utf-8'))
    registry=json.loads((root/'results/tsc_revision_mechanism_controls_20261018/preflight_v3/model_asset_registry_v1.json').read_text(encoding='utf-8'))
    model_records={m['model']:m for m in registry['models']}
    disk=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')
    results=[]
    for model,group in cases.items():
        path=disk/'models'/model;assets=[]
        for a in model_records[model]['files']:
            if a['file'].startswith(('tokenizer','special_tokens','vocab','merges')):
                assert hashlib.sha256((path/a['file']).read_bytes()).hexdigest()==a['sha256'];assets.append(a)
        tok=AutoTokenizer.from_pretrained(str(path),local_files_only=True)
        case=group['synthetic_case'];marker=case['synthetic_marker']
        for mode in ('raw','candidate'):
            text=tok.apply_chat_template(case[mode+'_messages'],tokenize=False,add_generation_prompt=True)
            assert text.count(marker)==1
            start=text.index(marker);end=start+len(marker)
            encoded=tok(text,add_special_tokens=False,return_offsets_mapping=True)
            assert encoded['input_ids']==case[mode+'_prompt_token_ids']
            indices=[i for i,(a,b) in enumerate(encoded['offset_mapping']) if b>start and a<end]
            assert indices
            results.append(dict(model=model,mode=mode,marker_start_character=start,marker_end_character=end,
                marker_first_token=min(indices),marker_token_end_exclusive=max(indices)+1,
                complete_prompt_ids_match_frozen_CPU_and_actual_server_check=True,
                marker_token_ids=encoded['input_ids'][min(indices):max(indices)+1],tokenizer_assets=assets))
    value=dict(rows=results,new_GPU_requests=0,artificial_marker_only=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cases_sha256=hashlib.sha256((study/'inputs_v1/cases_by_model_v1.json').read_bytes()).hexdigest())
    with output.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS',marker_positions=len(results),new_GPU_requests=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    main(p.parse_args().root.resolve())
