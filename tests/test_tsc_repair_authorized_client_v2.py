"""CPU transport wiring only; mocked outputs are never efficacy evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
from scripts import tsc_repair_authorized_client_v2 as client
from scripts.tsc_revision_r2_admission import SingleShotRegistrar
from scripts.contractkv_authorized_requests import AuthorizedRegistrar
from scripts.phase17_live_common import digest


def test_all_frozen_routes_and_counts_with_mocked_transport(tmp_path, monkeypatch):
    ids = list(range(32))
    messages = [{'role':'system','content':'Return ACK'}, {'role':'user','content':'Task'}]
    case = dict(case_id='synthetic_authorized_cache_identity', level='L3', budget=64,
                raw_messages=messages, candidate_messages=messages,
                raw_prompt_token_ids=ids, candidate_prompt_token_ids=ids,
                stable_prefix_end_token=16, stable_content_hash=digest(ids[:16]),
                layout_hash='layout', dependency_graph_hash='dag', query_scope='scope')
    real = [{**case,'case_id':'real-'+str(i),'family':'HotpotQA','source_group':str(i),
             'dataset':'fixture','task':'fixture','answer':'ACK'} for i in range(6)]
    cases = tmp_path/'cases.json';cases.write_text(json.dumps({'Qwen3-8B':dict(synthetic_case=case,real_cases=real)}))
    plan = tmp_path/'plan.json';plan.write_text('{}')
    identity = tmp_path/'identity.json'
    identity.write_text(json.dumps(dict(model_identity='model',model_revision='r',tokenizer='t',chat_template_hash='c',runtime_revision='runtime')))
    seen = []; verification_ids = []
    def generate(args, messages, budget, rid, witness=False, salt=None):
        seen.append((rid,salt))
        return dict(success=True,request_id=rid,output_text='ACK',prompt_token_ids=ids,
                    output_token_ids=[99,2],prompt_ids_sha256=digest(ids),finish_reason='stop',
                    witness_available=True,reference_margins=[1.,2.],ttft_ms=1,latency_ms=2,tpot_ms=1)
    def authorized(authority, identity, args, messages, budget, rid, witness=False):
        return generate(args,messages,budget,rid,witness,authority.require(identity))
    def poster(url,payload,timeout):
        verification_ids.append(payload['request_id'])
        return dict(certificate_issued=True,committed_tokens=16,minimum_margin_guard_passed=True,
                    raw_margin_min=1.,candidate_margin_min=.5,terminal_stop_margin=.5)
    class Legacy(SingleShotRegistrar):
        def __init__(self,*args):super().__init__(*args,poster=poster)
    monkeypatch.setattr(client,'SingleShotRegistrar',Legacy)
    monkeypatch.setattr(client,'AuthorizedRegistrar',lambda a,b,c,d:AuthorizedRegistrar(a,b,c,d,poster=poster))
    monkeypatch.setattr(client,'business_generate',generate)
    monkeypatch.setattr(client,'authorized_business_generate',authorized)
    monkeypatch.setattr(client,'standard_score',lambda *args:(1.,'CPU_mock','CPU_mock'))
    monkeypatch.setattr(client,'tokenize',lambda *args:ids)
    out=tmp_path/'responses.jsonl'
    client.run(SimpleNamespace(output=out,plan=plan,cases=cases,identity=identity,model='qwen3-8b',
                              cell_id='CPU_FIXTURE_ONLY',policy_hash='CPU_policy',source_root=Path.cwd(),
                              base_url='http://127.0.0.1:1/v1',timeout=1))
    rows=[json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert rows[-1]['event']=='repair_cell_complete'
    assert rows[-1]['counts']==dict(business=92,qualification=15,actual_RPC=15,stale_identity_denied=7)
    fixed=[r for r in rows if r['event']=='business' and r['condition'].startswith('authorized_')]
    assert all(r['actual_wire_cache_salt'] for r in fixed)
    assert len(seen)==92

    assert len(verification_ids) == len(set(verification_ids)) == 15
