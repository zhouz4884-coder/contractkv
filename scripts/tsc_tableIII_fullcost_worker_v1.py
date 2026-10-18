"""Isolated Linux orchestration for the frozen original-cohort timing replay.

This is infrastructure, not a replacement certification policy. Never start
while another study owns either GPU. No historical file/runtime is modified.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse, csv, hashlib, json, os, re, shutil, signal, socket
import subprocess, sys, time, urllib.request

GPU_UUIDS={'GPU-ef01d441-985f-50b3-6e64-5d4c3e2def3a','GPU-a696ce9a-7137-cf6f-b4d3-deb992a72f28'}
PYTHON='/home/user/miniconda3/envs/contractkv-cu128/bin/python'
DISK=Path('/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9')
STUDY_REL='results/tsc_tableIII_fullcost_replay_20261018'
SERVED={'qwen':'qwen3-8b','mistral':'mistral7b','llama':'llama31-8b','qwen14':'qwen3-14b'}

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8');q.replace(p)
def jsonl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def run(cmd,**kw):return subprocess.run(cmd,check=True,text=True,capture_output=True,**kw).stdout

def resource_snapshot():
    gpu=run(['nvidia-smi','--query-gpu=index,uuid,name,memory.used,utilization.gpu','--format=csv,noheader'])
    proc=run(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'])
    devices=list(csv.reader(gpu.splitlines(),skipinitialspace=True))
    processes=list(csv.reader(proc.splitlines(),skipinitialspace=True)) if proc.strip() else []
    assert {r[1] for r in devices}==GPU_UUIDS,'Unexpected GPU identity'
    assert len(devices)==2 and all('3090' in r[2] for r in devices)
    return {'time_utc':now(),'host':socket.gethostname(),'devices':devices,'processes':processes}

def foreign_pids(snapshot,owned_groups=()):
    unexpected=[]
    for row in snapshot['processes']:
        pid=int(row[0])
        try:owned=os.getpgid(pid) in owned_groups
        except ProcessLookupError:continue
        if not owned:unexpected.append(pid)
    return unexpected

def original_args(root,model,repeat,policy,cell,port):
    study=root/STUDY_REL;key=model['key'];base=f'http://127.0.0.1:{port}/v1'
    args=['--sessions',str(study/'inputs'/model['session_file']),'--base-url',base,
        '--model',SERVED[key],'--model-identity',str(DISK/'models'/model['model']),
        '--concurrency','2','--turns','10','--stable-word-limit',str(model['stable_word_limit']),
        '--max-tokens',str(model['max_tokens']),'--tool-slack-ms',str(model['historical_slack_ms']),
        '--slo-ms',str(2000 if key=='qwen14' else 1500),'--timeout',str(600 if key=='qwen14' else 300),
        '--metrics-events',str(cell/'metrics.jsonl'),'--output',str(cell/'requests.jsonl')]
    if key=='llama':
        manifest=read(study/'inputs'/model['qualification_file'])
        args+=['--mode','raw' if policy=='raw' else 'frozen','--level','L0',
            '--stable-pieces',str(model['stable_pieces']),
            '--layout-ladder',','.join(f'{k}={v}' for k,v in manifest['layout_ladder'].items()),
            '--policy-hash',manifest['qualification_hash'],'--load-tier',f'r{repeat}-'+('raw' if policy=='raw' else 'contract')]
        if policy=='contract':args+=['--qualification-manifest',str(study/'inputs'/model['qualification_file'])]
    else:
        qualification=model['policy_hash']
        if key=='qwen14':qualification=read(study/'inputs'/model['qualification_file'])['qualification_hash']
        args+=['--policy','raw-order' if policy=='raw' else 'contractkv-full',
            '--policy-hash',model['policy_hash'],'--qualification-hash',qualification,
            '--certificate-scope-mode','qualified_session',
            '--load-tier',f'r{repeat}-'+('raw' if policy=='raw' else 'contract') if key=='qwen14' else f'submission-r{repeat}']
    return args

def full_model_registry(root,models,out):
    old=read(root/STUDY_REL/'prior_model_registry_v1.json')
    by_name={m['model']:m for m in old['models']};records=[]
    for model in models:
        folder=DISK/'models'/model['model'];index=read(folder/'model.safetensors.index.json')
        shards=sorted(set(index['weight_map'].values()))
        if model['key']=='qwen14':assert len(shards)==8
        actual={p.name for p in folder.glob('*.safetensors')};assert actual==set(shards),(model['key'],actual,shards)
        names=set(shards)|{'model.safetensors.index.json','config.json','tokenizer_config.json','tokenizer.json','generation_config.json'}
        names.update(p.name for p in folder.iterdir() if p.is_file() and p.suffix in {'.json','.model','.txt','.tiktoken'} and not p.name.startswith('.'))
        files=[];prior={r['file']:r for r in by_name.get(model['model'],{}).get('files',[])}
        for name in sorted(names):
            p=folder/name;before=p.stat();digest=sha(p);after=p.stat()
            assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
            if name in prior:assert digest==prior[name]['sha256'],(model['model'],name,'model changed')
            files.append({'file':name,'bytes':after.st_size,'mtime_ns':after.st_mtime_ns,'sha256':digest})
        records.append({'model':model['model'],'files':files,'compared_to_prior_registry':bool(prior)})
        write(out/'model_registry_progress_v1.json',{'time_utc':now(),'models_completed':records})
    record={'time_utc':now(),'models':records,'new_inference_requests':0,
            'claim':'Fresh full hashes before measurement; Qwen14B is newly registered, not a recovered historical hash.'}
    write(out/'model_registry_v1.json',record)
    return record

def runtime_inventory(folder):
    return [{'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(folder.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and
        (p.suffix in {'.py','.so'} or p.name.endswith('.so'))]

def isolated_runtime(root,kind,preflight):
    source=root/'third_party'/('vllm-contractkv' if kind=='qwen' else 'vllm-contractkv-phase19c')
    dest=preflight/'runtimes'/kind
    if dest.exists():raise FileExistsError('Runtime preflight must use a new attempt directory')
    dest.mkdir(parents=True)
    before=runtime_inventory(source/'vllm')
    shutil.copytree(source/'vllm',dest/'vllm',symlinks=False,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    copied=runtime_inventory(dest/'vllm');assert copied==before,'Runtime copy differs from retained source'
    snap=root/STUDY_REL/'source_snapshot';env=os.environ.copy()
    env['PYTHONPATH']=str(dest)+os.pathsep+str(snap)+os.pathsep+str(root)
    sched=dest/'vllm/v1/core/sched/scheduler.py';changes=[]
    # Historical raw and Contract conditions both used the prefix probe.
    # Historical phase19c also installed the ephemeral shadow hook.
    if kind=='phase19c':
        cmd=[PYTHON,str(snap/'scripts/install_vllm_v1_ephemeral_shadow_hook.py'),'--scheduler',str(sched),'--action','install']
        changes.append({'command':cmd,'output':run(cmd,cwd=snap,env=env).strip()})
    cmd=[PYTHON,str(snap/'scripts/install_vllm_v1_prefix_metrics_probe.py'),'--scheduler',str(sched),'--action','install']
    changes.append({'command':cmd,'output':run(cmd,cwd=snap,env=env).strip()})
    code="import vllm,torch,transformers,json;print(json.dumps({'vllm':vllm.__version__,'file':vllm.__file__,'torch':torch.__version__,'transformers':transformers.__version__}))"
    versions=json.loads(run([PYTHON,'-B','-c',code],cwd=snap,env=env).strip().splitlines()[-1])
    assert versions['vllm']=='0.10.2' and Path(versions['file']).resolve().is_relative_to(dest.resolve())
    assert runtime_inventory(source/'vllm')==before,'Shared runtime changed during preparation'
    record={'source':str(source),'copy':str(dest),'before':before,'after':runtime_inventory(dest/'vllm'),
            'changes':changes,'versions':versions,'shared_runtime_unchanged':True,
            'historical_backend_byte_identity_established':False,
            'claim':'Retained fork copied and historical hooks applied in isolation. New replay, not a byte-identical July execution.'}
    write(preflight/(kind+'_runtime_v1.json'),record)
    return dest

def tokenizer_preflight(root,models,preflight):
    sys.path.insert(0,str(root/STUDY_REL/'source_snapshot'))
    from transformers import AutoTokenizer
    from scripts.phase19b_end_to_end_live import turn_case,messages,compile_layout
    from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger,compile_static_policy
    from scripts.phase22_llama_layout_ladder import expand_stable_segments,layout_for_level,family_key
    results=[]
    for model in models:
        tok=AutoTokenizer.from_pretrained(DISK/'models'/model['model'],local_files_only=True)
        samples=jsonl(root/STUDY_REL/'inputs'/model['session_file']);manifest={}
        if model['key']=='llama':manifest=read(root/STUDY_REL/'inputs'/model['qualification_file'])
        count=0;max_length=0;ledger=[]
        for sample in samples:
            for turn in range(10):
                case=turn_case(sample,turn,model['stable_word_limit'])
                if model['key']=='llama':
                    case=expand_stable_segments(case,model['stable_pieces'])
                    requested=manifest['frozen_family_levels'].get(family_key(sample),'L0')
                    eligible=manifest.get('family_eligible_levels',{}).get(family_key(sample),[])
                    levels=list(dict.fromkeys(['L0',requested]+[l for l in eligible if int(l[1:])<=int(requested[1:])]))
                    layouts=[layout_for_level(case,l,manifest['layout_ladder']) for l in levels]
                else:
                    layouts=[compile_static_policy(case['segments'],'raw-order'),compile_static_policy(case['segments'],'posc'),
                             compile_layout('physical-cache-aware',case,SegmentPrefixLedger(),str(sample['phase19b_session_id']),turn,model['historical_slack_ms'])]
                for layout in layouts:
                    ids=tok.apply_chat_template(messages(case,layout['topological_order']),tokenize=True,add_generation_prompt=True)
                    count+=1;max_length=max(max_length,len(ids))
                    if len(ids)+model['max_tokens']+1>model['max_model_len']:
                        raise ValueError(f"Frozen prompt exceeds window: {model['key']} {sample['phase19b_session_id']} turn {turn}")
                    ledger.append({'session_id':sample['phase19b_session_id'],'turn':turn,'layout':layout.get('layout_level',layout.get('policy')),
                        'prompt_tokens':len(ids),'prompt_ids_sha256':hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()})
        target=preflight/(model['key']+'_input_shapes_v1.json')
        result={'model':model['model'],'checked':count,'maximum_prompt_tokens':max_length,'generation_reserve':model['max_tokens']+1,
                'window':model['max_model_len'],'no_input_modification':True,'ledger':ledger,'inference_requests':0}
        write(target,result);results.append({k:v for k,v in result.items() if k!='ledger'})
    write(preflight/'input_shapes_summary_v1.json',{'models':results,'new_GPU_requests':0})

def endpoint(url):
    with urllib.request.urlopen(url,timeout=5) as r:return r.read().decode('utf-8')

def cell_env(root,runtime,model,cell,gpu):
    env={k:v for k,v in os.environ.items() if not k.startswith(('CONTRACTKV_','VLLM_'))}
    cache=cell/'cache';tmp=cell/'tmp';tmp.mkdir(parents=True)
    policy_hash=model.get('policy_hash')
    if model['key']=='llama':policy_hash=read(root/STUDY_REL/'inputs'/model['qualification_file'])['qualification_hash']
    env.update(PYTHONPATH=str(runtime)+os.pathsep+str(root/STUDY_REL/'source_snapshot')+os.pathsep+str(root),
        CUDA_VISIBLE_DEVICES=gpu,CONTRACTKV_POLICY_HASH=policy_hash,CONTRACTKV_MIN_CANDIDATE_MARGIN='-1000000000',
        CONTRACTKV_MAX_DEGRADATION='1000000000',CONTRACTKV_PREFIX_METRICS='1',CONTRACTKV_PREFIX_INITIAL_ONLY='1',
        CONTRACTKV_PREFIX_METRICS_LOG=str(cell/'metrics.jsonl'),
        TMPDIR=str(tmp),XDG_CACHE_HOME=str(cache/'xdg'),HF_HOME=str(cache/'hf'),
        HF_HUB_CACHE=str(cache/'hf/hub'),TRANSFORMERS_CACHE=str(cache/'hf/transformers'),TORCH_HOME=str(cache/'torch'),
        TRITON_CACHE_DIR=str(cache/'triton'),VLLM_CACHE_ROOT=str(cache/'vllm'),
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
    return env

def stop_own_group(proc):
    # Only the session explicitly created by this worker may be signalled.
    if proc is None:return
    pgid=proc.pid
    try:assert os.getpgid(proc.pid)==pgid,'Unexpected process group; refusing cleanup'
    except ProcessLookupError:pass  # The recorded group can outlive its API parent.
    try:os.killpg(pgid,signal.SIGTERM)
    except ProcessLookupError:return
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        try:os.killpg(pgid,0)
        except ProcessLookupError:return
        time.sleep(.25)
    try:os.killpg(pgid,signal.SIGKILL)
    except ProcessLookupError:pass

def validate_cell(cell,model,policy):
    rr=jsonl(cell/'requests.jsonl');future=[r for r in rr if r.get('row_type')=='future']
    assert len(future)==model['sessions']*9 and all(r.get('success') is True for r in future)
    wall=read(cell/'audit/complete_client_wall_v1.json');assert wall['status']=='complete' and wall['complete_client_wall_s']>0
    events=jsonl(cell/'audit/complete_controller_events_v1.jsonl')
    controllers=[r for r in events if r['event']=='complete_controller']
    canaries=[r for r in rr if r.get('row_type')=='canary']
    assert len(controllers)==len(canaries)
    assert len({r['session_id'] for r in controllers})==len(controllers)
    assert all(r['controller_ms']>0 for r in controllers)
    if policy=='contract':assert len(controllers)==model['sessions']
    if (cell/'completion_v1.json').exists():
        for r in read(cell/'completion_v1.json').get('files',[]):assert sha(cell/r['path'])==r['sha256']
    return {'future_requests':len(future),'controller_count':len(controllers),'controller_total_ms':sum(r['controller_ms'] for r in controllers),
            'raw_reference_calls':sum(r['event']=='generate_raw' for r in events),
            'verification_attempts':sum(r['event']=='compact_verify' for r in events),
            'exception_calls':sum(r.get('outcome')=='exception' for r in events),'client_wall_s':wall['complete_client_wall_s'],
            'completed_business_rows':sum(r.get('success') is True for r in rr if r.get('row_type')!='canary')}

def run_cell(root,runtime,model,repeat,policy,cell,port,gpu,owned_groups):
    if cell.exists():raise FileExistsError(cell)
    cell.mkdir(parents=True);server=None;serverlog=None
    try:
        assert not foreign_pids(resource_snapshot(),owned_groups),'Unrelated GPU task appeared'
        with socket.socket() as s:s.bind(('127.0.0.1',port))
        env=cell_env(root,runtime,model,cell,gpu)
        server_cmd=[PYTHON,'-m','vllm.entrypoints.openai.api_server','--model',str(DISK/'models'/model['model']),
            '--served-model-name',SERVED[model['key']],'--dtype','float16','--tensor-parallel-size',str(model['tp']),
            '--gpu-memory-utilization','.88','--max-model-len',str(model['max_model_len']),'--max-num-seqs','2',
            '--port',str(port),'--enable-prefix-caching']
        client_cmd=[PYTHON,'-B',str(root/'scripts/tsc_tableIII_instrument_frozen_client_v1.py'),
            '--snapshot-root',str(root/STUDY_REL/'source_snapshot'),'--module',model['driver'],'--audit-dir',str(cell/'audit'),'--',
            *original_args(root,model,repeat,policy,cell,port)]
        write(cell/'launch_v1.json',{'time_utc':now(),'model':model['model'],'policy':policy,'repeat':repeat,'gpu_ids':gpu,
            'server_command':server_cmd,'client_command':client_cmd,
            'controlled_environment':{k:v for k,v in env.items() if k.startswith(('CONTRACTKV_','VLLM_')) or k in ['CUDA_VISIBLE_DEVICES','PYTHONPATH']}})
        serverlog=(cell/'server.log').open('wb')
        server=subprocess.Popen(server_cmd,cwd=root/STUDY_REL/'source_snapshot',env=env,stdout=serverlog,stderr=subprocess.STDOUT,start_new_session=True)
        owned_groups.add(server.pid)
        write(cell/'server_process_v1.json',{'pid':server.pid,'process_group':server.pid,'time_utc':now()})
        ready=False;deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            if server.poll() is not None:raise RuntimeError('Fresh server exited during startup; inspect retained server.log')
            try:
                response=json.loads(endpoint(f'http://127.0.0.1:{port}/v1/models'))
                ready=any(r.get('id')==SERVED[model['key']] for r in response.get('data',[]))
            except Exception:pass
            if ready:break
            time.sleep(1)
        if not ready:raise TimeoutError('Server startup timeout')
        write(cell/'ready_v1.json',{'time_utc':now(),'server_pid':server.pid})
        with (cell/'client.log').open('wb') as log:
            result=subprocess.run(client_cmd,cwd=root/STUDY_REL/'source_snapshot',env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'Client failed with code {result.returncode}; full logs preserved')
        check=validate_cell(cell,model,policy)
        # Charge final health/drain observation separately instead of hiding it.
        drain_start=time.monotonic();idle_count=0;metric_text=''
        while time.monotonic()-drain_start<60:
            metric_text=endpoint(f'http://127.0.0.1:{port}/metrics')
            active=[float(m[1]) for m in re.finditer(r'^vllm:num_requests_(?:running|waiting)(?:\{[^\n]*\})?\s+([\d.eE+-]+)$',metric_text,re.M)]
            if not active:raise RuntimeError('Cannot identify native running/waiting gauges for final drain')
            idle_count=idle_count+1 if all(x==0 for x in active) else 0
            if idle_count>=2:break
            time.sleep(.2)
        if idle_count<2:raise RuntimeError('Unfinished backend requests after client completion')
        drain=time.monotonic()-drain_start;(cell/'final_metrics.txt').write_text(metric_text,encoding='utf-8')
        check.update(final_drain_s=drain,service_wall_with_drain_s=check['client_wall_s']+drain)
        assert not foreign_pids(resource_snapshot(),owned_groups),'Concurrent external GPU task invalidates cell'
        files=[cell/'requests.jsonl',cell/'audit/complete_client_wall_v1.json',cell/'audit/complete_controller_events_v1.jsonl',cell/'launch_v1.json']
        write(cell/'completion_v1.json',{'status':'complete','time_utc':now(),'checks':check,
            'files':[{'path':p.relative_to(cell).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in files],
            'new_measurement_not_historical_timer_recovery':True})
        return check
    except BaseException as exc:
        write(cell/'failure_v1.json',{'time_utc':now(),'error_type':type(exc).__name__,'message':str(exc),
            'no_partial_cell_resume':True,'results_excluded_from_complete_pair_until_full_rerun':True})
        raise
    finally:
        stop_own_group(server)
        if server is not None:owned_groups.discard(server.pid)
        if serverlog is not None:serverlog.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--mode',choices=['check','preflight','execute'],default='check')
    p.add_argument('--attempt',type=int,default=1);p.add_argument('--repair-record',type=Path)
    p.add_argument('--preflight-receipt-sha256')
    a=p.parse_args();root=a.root.resolve();study=root/STUDY_REL
    if sys.platform!='linux':raise RuntimeError('Execute orchestration only on the registered Linux host')
    assert root.is_relative_to(DISK) and study.is_relative_to(DISK)
    if a.attempt>1:assert a.repair_record and a.repair_record.is_file(),'Document infrastructure repair before another attempt'
    protocol=read(study/'protocol_v1.json');freeze=read(study/'freeze_v1.json')
    launch=read(study/'launch_addendum_v1.json')
    for entry in freeze['files']+protocol['archived_source_files']+protocol['input_files']+launch['files']:
        assert sha(root/entry['path'])==entry['sha256'],entry['path']
    snap=resource_snapshot();foreign=foreign_pids(snap)
    if foreign:
        write(study/'last_resource_observation_v1.json',{**snap,'waiting_for_foreign_PIDs':foreign,'new_GPU_requests':0})
        print(json.dumps({'status':'WAITING_FOR_EXCLUSIVE_GPUS','foreign_PIDs':foreign}));return 75
    if a.mode=='check':print(json.dumps({'status':'EXCLUSIVE_GPUS_AVAILABLE','snapshot':snap}));return 0
    import fcntl
    lock=(study/'worker.lock').open('a+')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('An existing study worker owns the lock; do not duplicate it')
    state_path=study/'execution_state_v1.json';state=read(state_path)
    state.update(status='PREFLIGHT',formal_worker_pid=os.getpid(),worker_start_utc=now(),worker_attempt=a.attempt)
    write(state_path,state)
    preflight=study/f'launch_attempt{a.attempt}_preflight'
    try:
        receipt=preflight/'preflight_receipt_v1.json'
        if preflight.exists():
            if not receipt.exists():raise FileExistsError('Incomplete preflight: use a documented new infrastructure attempt')
            check=read(receipt)
            assert check['protocol_sha256']==sha(study/'protocol_v1.json')
            assert check['worker_sha256']==sha(Path(__file__))
            for r in check['metadata_files']:assert sha(preflight/r['path'])==r['sha256']
            for model in read(preflight/'model_registry_v1.json')['models']:
                for r in model['files']:
                    stat=(DISK/'models'/model['model']/r['file']).stat()
                    assert (stat.st_size,stat.st_mtime_ns)==(r['bytes'],r['mtime_ns']),'Model changed after preflight'
            for kind in ['qwen','phase19c']:
                inv=read(preflight/(kind+'_runtime_v1.json'))
                assert runtime_inventory(Path(inv['copy'])/'vllm')==inv['after'],'Isolated runtime changed after preflight'
        else:
            preflight.mkdir();write(preflight/'initial_resources_v1.json',snap)
            assert shutil.disk_usage(DISK).free>50*(1<<30),'Less than 50 GiB free on the experiment volume'
            full_model_registry(root,protocol['models'],preflight)
            for kind in ['qwen','phase19c']:isolated_runtime(root,kind,preflight)
            tokenizer_preflight(root,protocol['models'],preflight)
            metadata=[p for p in sorted(preflight.glob('*.json')) if p!=receipt]
            write(receipt,{'time_utc':now(),'protocol_sha256':sha(study/'protocol_v1.json'),'worker_sha256':sha(Path(__file__)),
                'metadata_files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in metadata],
                'GPU_inference_started':False,'models_and_runtime_frozen_before_measurement':True})
        state.update(status='PREFLIGHT_COMPLETE_AWAITING_LAUNCH_FREEZE',runtime_and_model_launch_preflight_complete=True,
                     formal_worker_pid=None,preflight_receipt_sha256=sha(receipt));write(state_path,state)
        if foreign_pids(resource_snapshot()):
            state['status']='WAITING_FOR_EXCLUSIVE_GPUS';write(state_path,state)
            return 75
        if a.mode=='preflight':return 0
        if a.preflight_receipt_sha256!=sha(receipt):
            print(json.dumps({'status':'PREFLIGHT_COMPLETE_AWAITING_LAUNCH_FREEZE','receipt_sha256':sha(receipt)}));return 76
        runtimes={kind:preflight/'runtimes'/kind for kind in ['qwen','phase19c']}
        state['formal_worker_pid']=os.getpid()
        completed=[];owned_groups=set()
        for mi,model in enumerate(protocol['models']):
            for repeat in (1,2,3):
                pair_root=study/'cells'/f"{model['key']}_r{repeat}"
                # Reuse only an entire valid completed pair, never one half or
                # an unfinished cell. Selection is chronological, not by score.
                old_pairs=sorted(pair_root.glob('attempt*/pair_completion_v1.json'),key=lambda p:int(p.parent.name[7:])) if pair_root.exists() else []
                if old_pairs:
                    old_pair=old_pairs[0].parent
                    for policy in ['raw','contract']:validate_cell(old_pair/policy,model,policy)
                    completed.append(str(old_pair.relative_to(study)))
                    state.update(formal_GPU_cells_completed=len(completed)*2,completed_pairs=completed);write(state_path,state)
                    continue
                pair=pair_root/f'attempt{a.attempt}'
                if pair.exists():raise FileExistsError('A pair attempt already exists; no partial resume')
                pair.mkdir(parents=True)
                runtime=runtimes['qwen' if model['key']=='qwen' else 'phase19c']
                state.update(status='RUNNING',formal_GPU_worker_started=True,current_pair=f"{model['key']}_r{repeat}",new_GPU_requests_so_far=None)
                write(state_path,state)
                order=['contract','raw'] if repeat==2 else ['raw','contract']
                checks={};port=8960+mi*10+repeat*2
                if model['tp']==2:
                    for policy in order:checks[policy]=run_cell(root,runtime,model,repeat,policy,pair/policy,port,'0,1',owned_groups)
                else:
                    gpu={'raw':'1' if repeat==2 else '0','contract':'0' if repeat==2 else '1'}
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        left=pool.submit(run_cell,root,runtime,model,repeat,order[0],pair/order[0],port,gpu[order[0]],owned_groups)
                        time.sleep(2)
                        right=pool.submit(run_cell,root,runtime,model,repeat,order[1],pair/order[1],port+1,gpu[order[1]],owned_groups)
                        checks[order[0]]=left.result();checks[order[1]]=right.result()
                assert not foreign_pids(resource_snapshot()),'Unrelated or leaked compute PID after pair cleanup'
                pair_result={'status':'complete','time_utc':now(),'model':model['model'],'repeat':repeat,'cells':checks,
                    'direct_wall_multiplier':checks['raw']['service_wall_with_drain_s']/checks['contract']['service_wall_with_drain_s'],
                    'future_pairs':model['sessions']*9,'claim':'New original-cohort replay, not a recovered historical timestamp.'}
                write(pair/'pair_completion_v1.json',pair_result);completed.append(str(pair.relative_to(study)))
                state.update(formal_GPU_cells_completed=len(completed)*2,completed_pairs=completed);write(state_path,state)
        state.update(status='FROZEN_MATRIX_COMPLETE_PENDING_ANALYSIS',current_pair=None,formal_worker_pid=None,
                     completed_at_utc=now(),formal_GPU_cells_completed=24);write(state_path,state)
        return 0
    except BaseException as exc:
        state.update(status='INFRASTRUCTURE_OR_PROTOCOL_FAILURE',formal_worker_pid=None,error_type=type(exc).__name__,error_message=str(exc),time_utc=now())
        write(state_path,state);raise
    finally:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

if __name__=='__main__':raise SystemExit(main())
