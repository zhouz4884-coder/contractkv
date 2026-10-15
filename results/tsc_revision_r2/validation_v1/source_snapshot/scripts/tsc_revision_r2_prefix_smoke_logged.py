"""Logging-only adapter for frozen infrastructure controls, outside measurements."""
import argparse
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r1r_prefix_smoke as original
from scripts.phase17_live_common import digest

def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--evidence',type=Path,required=True);a,rest=p.parse_known_args()
    if a.evidence.exists():raise RuntimeError('Preserve infrastructure-control evidence')
    a.evidence.parent.mkdir(parents=True,exist_ok=True)
    def record(row):
        with a.evidence.open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    generate=original.generate_raw;post=original.post_json
    def observed_generate(*args,**kwargs):
        result=generate(*args,**kwargs);body=result['response'];ids=body.get('prompt_token_ids')
        if not ids or body['usage']['prompt_tokens']!=len(ids):raise RuntimeError('Control actual prompt IDs missing')
        record({'row_type':'control_raw_generation','request_id':body['id'],'prompt_token_ids':ids,'prompt_ids_sha256':digest(ids),'response':body})
        return result
    def observed_post(url,payload,timeout):
        if '/v1/contractkv/verify' not in url:raise ValueError('Unexpected adapted control endpoint')
        record({'row_type':'control_verification_request','request_id':payload['request_id'],'payload':payload,'prompt_ids_sha256':digest(payload['prompt_token_ids']),'request_hash_computed_before_dispatch':True})
        result=post(url,payload,timeout)
        record({'row_type':'control_verification_response','request_id':payload['request_id'],'response':result})
        return result
    original.generate_raw=observed_generate;original.post_json=observed_post
    sys.argv=[sys.argv[0],*rest];return original.main()

if __name__=='__main__':raise SystemExit(main())
