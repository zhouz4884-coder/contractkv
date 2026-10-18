"""Tokenizer/window/ownership checks only; synthetic histories are not results."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

os.environ.update(USE_TORCH='0',USE_TF='0',HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from transformers import AutoTokenizer
from scripts.tsc_tableI_survey_common_v1 import tokenize_request


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--tokenizer',required=True);a=p.parse_args()
    protocol=json.loads((ROOT/'configs/tsc_tableI_remeasurement_20261018_v1.json').read_text())
    selected=[json.loads(l) for l in (a.root/'inputs_v1/selected_packed_sources_v1.jsonl').open() if l.strip()]
    tokenizer=AutoTokenizer.from_pretrained(a.tokenizer,local_files_only=True,trust_remote_code=False)
    rows=[]
    for value in selected:
        if value['sample'] is None:continue
        sample=value['sample'];history=[]
        for turn in range(9):
            r=tokenize_request(tokenizer,sample,history,turn,protocol)
            if turn==0:
                assert r['token_categories'].count('history')==0
                first=len(r['prompt_token_ids'])
            history.append({'query':r['wrapped_query'],'answer':' cache'*64})
        last=tokenize_request(tokenizer,sample,history,9,protocol)
        assert len(last['prompt_token_ids'])+protocol['max_new_tokens']<=protocol['model_window']
        assert last['token_categories'].count('stable')>0 and last['token_categories'].count('history')>0
        for segment in sample['segments']:
            if segment['type']=='CODE_PREFIX':assert segment['text'] in last['messages'][-1]['content']
        rows.append({'source_group':value['source_group'],'first_prompt_tokens':first,
                     'synthetic_9_turn_history_prompt_tokens':len(last['prompt_token_ids']),
                     'CODE_PREFIX_unchanged':True})
    output=a.root/'inputs_v1/CPU_preflight_v1.json'
    assert not output.exists()
    report={'sources_checked':len(rows),'requests_tokenized':10*len(rows),
            'shape_control_histories_are_synthetic_not_experimental_answers':True,
            'actual_survey_histories_will_use_real_generated_outputs':True,
            'all_checked_windows_and_role_ownership_pass':True,'source_checks':rows,
            'new_model_forwards':0}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_checks'}),flush=True)


if __name__=='__main__':main()
