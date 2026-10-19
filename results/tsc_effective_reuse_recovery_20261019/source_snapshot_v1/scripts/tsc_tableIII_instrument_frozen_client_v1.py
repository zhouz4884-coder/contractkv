"""Instrument an archived client in memory, preserving its decisions and inputs.

The timing wrapper is separate from the archived source. It cannot restore a
historical timestamp. All replay results must be labelled as new measurements.
"""
from pathlib import Path
import argparse, ast, hashlib, json, sys, time, traceback

def contains_canary(node):
    return any(isinstance(x,ast.Dict) and any(isinstance(k,ast.Constant) and k.value=='row_type' and
        isinstance(v,ast.Constant) and v.value=='canary' for k,v in zip(x.keys,x.values)) for x in ast.walk(node))

def instrument_tree(source):
    tree=ast.parse(source)
    main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
    loops=[x for x in ast.walk(main) if isinstance(x,ast.For) and contains_canary(x)]
    inner=[x for x in loops if not any(y is not x and y in list(ast.walk(x)) for y in loops)]
    if len(inner)!=1:raise ValueError(f'Expected exactly one canary loop, found {len(inner)}')
    loop=inner[0];oldbody=loop.body
    begin=ast.parse('__audit_controller_started = __audit_begin(sample)').body[0]
    end=ast.parse('__audit_end(__audit_controller_started, sample, locals())').body
    loop.body=[begin,ast.Try(body=oldbody,handlers=[],orelse=[],finalbody=end)]
    return ast.fix_missing_locations(tree)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot-root',type=Path,required=True)
    p.add_argument('--module',choices=['phase19b_end_to_end_live','phase22_llama_broad_live'],required=True)
    p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('driver_args',nargs=argparse.REMAINDER);a=p.parse_args()
    a.audit_dir.mkdir(parents=True,exist_ok=True)
    event_path=a.audit_dir/'complete_controller_events_v1.jsonl'
    if event_path.exists():raise FileExistsError('Partial-cell resume/overwrite is forbidden')
    source_path=a.snapshot_root/'scripts'/(a.module+'.py')
    source=source_path.read_text(encoding='utf-8');tree=instrument_tree(source)
    transformed=ast.unparse(tree)
    (a.audit_dir/'instrumented_client_v1.py').write_text(transformed+'\n',encoding='utf-8')
    def emit(row):
        with event_path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=True,allow_nan=False)+'\n')
    def begin(sample):return time.perf_counter()
    def end(start,sample,state):
        elapsed=(time.perf_counter()-start)*1000
        sid=str(sample['phase19b_session_id']);cert=state.get('certificates',{}).get(sid,{})
        emit({'event':'complete_controller','session_id':sid,'controller_ms':elapsed,
              'certificate_issued':bool(cert.get('certificate_issued')),'decision':cert.get('verify_decision'),
              'level_attempts':cert.get('level_attempts',[]),'raw_finish_reason':cert.get('raw_finish_reason')})
    namespace={'__name__':'frozen_client','__package__':'','__file__':str(source_path),'__audit_begin':begin,'__audit_end':end}
    sys.path.insert(0,str(a.snapshot_root))
    exec(compile(tree,str(source_path),'exec'),namespace)
    # Each raw-reference and verification call is recorded even on exception.
    for name in ['generate_raw','compact_verify']:
        original=namespace[name]
        def wrap(*args,__original=original,__name=name,**kw):
            started=time.perf_counter();outcome='exception';result=None
            try:
                result=__original(*args,**kw);outcome='returned';return result
            finally:
                row={'event':__name,'elapsed_ms':(time.perf_counter()-started)*1000,'outcome':outcome}
                if isinstance(result,dict):
                    for k in ['certificate_issued','verify_decision','verification_ms','verify_endpoint_ms','finish_reason']:
                        if k in result:row[k]=result[k]
                emit(row)
        namespace[name]=wrap
    argv=a.driver_args[1:] if a.driver_args[:1]==['--'] else a.driver_args
    sys.argv=[str(source_path)]+argv
    emit({'event':'source','archived_source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
          'instrumented_source_sha256':hashlib.sha256((transformed+'\n').encode()).hexdigest(),
          'new_measurement_not_historical_recovery':True})
    start=time.perf_counter();status='exception';code=1
    try:
        value=namespace['main']();code=int(value or 0);status='complete' if code==0 else 'failed'
    finally:
        elapsed=time.perf_counter()-start
        record={'status':status,'return_code':code,'complete_client_wall_s':elapsed,
                'server_startup_included':False,'slack_subtracted_from_client_wall':False,
                'full_cost_includes_failed_attempts':True,'source_file':str(source_path)}
        (a.audit_dir/'complete_client_wall_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        emit({'event':'client_finished',**record})
    return code

if __name__=='__main__':raise SystemExit(main())
