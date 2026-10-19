"""Declared Qwen nonthinking chat-template condition; unchanged frozen scorer."""
import argparse
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r2_business_stream as stream
from scripts import tsc_revision_r2_long_format as original
from scripts.phase17_live_common import api_root,post_json,digest

def template_options(model,messages,explicit_system):
    return {'enable_thinking':False} if model=='qwen3-8b' and messages[0]['content']==explicit_system else None

def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a,_=p.parse_known_args()
    config=json.loads(a.protocol.read_text(encoding='utf-8'));trace=a.output.parent/'native_template_options.jsonl'
    if trace.exists():raise RuntimeError('Preserve native-template condition attempt')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    base_payload=stream.generation_payload;base_generate=stream.business_generate
    def payload(model,messages,budget,seed):
        result=base_payload(model,messages,budget,seed);options=template_options(model,messages,config['explicit_system'])
        if options is not None:result['chat_template_kwargs']=options
        return result
    def tokenize(base,model,messages,add_generation_prompt,timeout):
        body={'model':model,'messages':messages,'add_generation_prompt':add_generation_prompt}
        options=template_options(model,messages,config['explicit_system'])
        if options is not None:body['chat_template_kwargs']=options
        result=post_json(api_root(base)+'/tokenize',body,timeout)
        return [int(x) for x in result['tokens']]
    def generate(args,messages,budget,rid,witness=False,salt=None):
        result=base_generate(args,messages,budget,rid,witness,salt)
        record={'actual_request_id':result['request_id'],'requested_request_id':rid,'chat_template_kwargs':template_options(args.model,messages,config['explicit_system']),
                'prompt_ids_sha256':result.get('prompt_ids_sha256'),'messages_sha256':digest(messages),
                'actual_output_ids_sha256':digest(result['output_token_ids']),'native_condition_is_not_guided_decoding':True}
        with trace.open('a',encoding='utf-8') as out:out.write(json.dumps(record)+'\n')
        return result
    stream.generation_payload=payload;original.business_generate=generate;original.tokenize=tokenize
    return original.main()

if __name__=='__main__':raise SystemExit(main())
