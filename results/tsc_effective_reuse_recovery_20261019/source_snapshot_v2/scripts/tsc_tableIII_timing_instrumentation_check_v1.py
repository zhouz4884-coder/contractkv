"""Deterministic CPU check of timer control flow; not a GPU efficacy test."""
from pathlib import Path
import importlib.util,json

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('instrument',ROOT/'scripts/tsc_tableIII_instrument_frozen_client_v1.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def main():
    source='''
def main():
    certificates={}; rows=[]
    for sample in [{'phase19b_session_id':'pass'}, {'phase19b_session_id':'fail'}, {'phase19b_session_id':'exception'}]:
        sid=sample['phase19b_session_id']
        try:
            if sid=='exception':raise RuntimeError('expected')
            certificates[sid]={'certificate_issued':sid=='pass','verify_decision':sid}
        except RuntimeError:
            certificates[sid]={'certificate_issued':False,'verify_decision':'incomplete'}
        rows.append({'row_type':'canary','session_id':sid,'decision':certificates[sid]['verify_decision']})
    return rows
'''
    plain={};exec(source,plain);expected=plain['main']()
    events=[]
    injected={'__audit_begin':lambda s:s['phase19b_session_id'],
              '__audit_end':lambda start,s,local:events.append((start,s['phase19b_session_id'],local['certificates'][s['phase19b_session_id']]['verify_decision']))}
    exec(compile(mod.instrument_tree(source),'<test>','exec'),injected)
    actual=injected['main']()
    assert actual==expected
    assert len(events)==3 and [r[2] for r in events]==['pass','fail','incomplete']
    checked=[]
    snapshot=ROOT/'results/tsc_tableIII_fullcost_replay_20261018/source_snapshot'
    for name in ['phase19b_end_to_end_live','phase22_llama_broad_live']:
        p=snapshot/'scripts'/(name+'.py')
        tree=mod.instrument_tree(p.read_text(encoding='utf-8'));compile(tree,str(p),'exec');checked.append(name)
    record={'status':'PASS','preserved_toy_decisions':True,'timed_pass_fail_exception_paths':3,
            'archived_drivers_AST_compiled':checked,'evidence_type':'CPU control-flow test only; no model calls or latency claims','new_GPU_requests':0}
    target=ROOT/'results/tsc_tableIII_fullcost_replay_20261018/instrumentation_CPU_check_v1.json'
    target.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record))

if __name__=='__main__':main()
