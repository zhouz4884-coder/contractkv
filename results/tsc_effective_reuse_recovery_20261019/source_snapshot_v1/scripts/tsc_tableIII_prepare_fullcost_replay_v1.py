"""Freeze original-sample timing replay inputs without starting GPU work."""
from pathlib import Path
import hashlib, importlib.util, io, json, subprocess, tarfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'
REMOTE='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/'

def main():
    commit=subprocess.check_output(['git','rev-parse','dcfa7d2'],cwd=ROOT,text=True).strip()
    snapshot=OUT/'source_snapshot';snapshot.mkdir(parents=True,exist_ok=True)
    archive=subprocess.check_output(['git','archive','--format=tar',commit,'scripts','configs','patches'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(snapshot,filter='data')
    spec=importlib.util.spec_from_file_location('vault',r'C:\Users\LENOVO\.codex\local-tools\contractkv_ssh_credential.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    c=mod.ssh_client();sftp=c.open_sftp()
    rels=['results/end_to_end/phase19b_untouched_sessions_v0.jsonl','results/mistral/heldout_sealed_sessions_v0.jsonl',
          'results/scale_up/qwen3_14b_tp2_v0/frozen_sessions_v0.jsonl','results/scale_up/qwen3_14b_tp2_v0/policy_transfer_manifest_v0.json',
          'results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl',
          'results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json']
    inputs=[]
    for rel in rels:
        before=sftp.stat(REMOTE+rel)
        with sftp.open(REMOTE+rel,'rb') as f:
            f.prefetch(before.st_size);data=f.read()
        after=sftp.stat(REMOTE+rel);assert before.st_size==len(data)==after.st_size and before.st_mtime==after.st_mtime
        p=OUT/'inputs'/rel;p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists():assert p.read_bytes()==data
        else:p.write_bytes(data)
        inputs.append({'path':p.relative_to(ROOT).as_posix(),'remote_path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    sftp.close();c.close()
    hashes=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(snapshot.rglob('*')) if p.is_file()]
    old_manifest=json.loads((OUT/'inputs'/rels[-1]).read_text(encoding='utf-8'))
    protocol={'schema_version':'contractkv.original-sample-fullcost-replay.v1','status':'frozen_before_new_measurement',
        'purpose':'Reviewer 3 original Table III zero-slack cost; new matched frozen-cohort replay, not recovery of missing old timestamps.',
        'historical_client_commit':commit,'input_files':inputs,'archived_source_files':hashes,
        'models':[
          {'key':'llama','model':'Llama-3.1-8B-Instruct','sessions':50,'session_file':rels[4],'qualification_file':rels[5],
           'driver':'phase22_llama_broad_live','max_model_len':16384,'max_tokens':96,'stable_word_limit':1500,'stable_pieces':16,'tp':1,'historical_slack_ms':6000,
           'frozen_family_levels':old_manifest['frozen_family_levels']},
          {'key':'qwen','model':'Qwen3-8B','sessions':50,'session_file':rels[0],'driver':'phase19b_end_to_end_live',
           'max_model_len':8192,'max_tokens':96,'stable_word_limit':2600,'tp':1,'historical_slack_ms':2000,
           'policy_hash':'55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4'},
          {'key':'mistral','model':'Mistral-7B-Instruct-v0.3','sessions':50,'session_file':rels[1],'driver':'phase19b_end_to_end_live',
           'max_model_len':8192,'max_tokens':128,'stable_word_limit':1500,'tp':1,'historical_slack_ms':2000,
           'policy_hash':'f5d99ddf2bb14dc9d3e0a92040f337682cbb9ab93baef4e3be5d43d9106488d8'},
          {'key':'qwen14','model':'Qwen3-14B','sessions':25,'session_file':rels[2],'qualification_file':rels[3],'driver':'phase19b_end_to_end_live',
           'max_model_len':8192,'max_tokens':96,'stable_word_limit':2600,'tp':2,'historical_slack_ms':2000,
           'policy_hash':'55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4'}],
        'repeats':3,'policies':['raw','contract'],'expected_fresh_server_cells':24,'expected_future_pairs':4725,
        'expected_future_pairs_per_repeat':{'qwen':450,'mistral':450,'llama':450,'qwen14':225},
        'turns':10,'client_concurrency':2,'server_max_num_seqs':2,'dtype':'float16','gpu_memory_utilization':.88,
        'generation':'Original driver greedy generation and stop settings; no new margin, level selection, source selection or scoring rule.',
        'frozen_behavior':'Retain original slack CLI values where they participate in policy/scope construction. Measure full costs independently and set slack to zero only in accounting; do not change policy opportunities.',
        'timing':'Full client monotonic wall, every canary controller body including failure/exception, every raw-reference call and verification attempt. Server startup excluded; logging charged; no failed call assigned zero by omission.',
        'runtime_gate':'Fresh full model/tokenizer hashes and isolated serving fork inventory must pass before launch. Copy retained serving sources into a dedicated volume-local overlay; do not modify shared runtime trees.',
        'resource_gate':'Both GPU UUIDs must match and no unrelated compute PID may be present; never terminate another task or mix studies.',
        'process_order':'Llama, Qwen8B, Mistral, Qwen14B; three repeats each. Swap raw/contract GPU assignments and launch order on repeat 2; TP2 uses both GPUs sequentially with reversed policy order on repeat 2.',
        'stop_rules':['No retuning/replacement/exclusion based on quality, coverage or speed.','Infrastructure failures remain archived; rerun entire paired cell after a documented repair, no partial resume.','Unexpected protocol/input/runtime mismatch pauses launch for diagnosis, not silent adaptation.'],
        'claim_boundary':'New timing evidence on original registered task IDs, not an unseen-source study, not historical timer recovery, and not automatic equivalence to a July runtime execution.',
        'GPU_started':False}
    for row in protocol['models']:
        n=sum(bool(l.strip()) for l in (OUT/'inputs'/row['session_file']).read_bytes().splitlines());assert n==row['sessions'],(row['key'],n)
    path=OUT/'protocol_v1.json'
    encoded=json.dumps(protocol,indent=2)+'\n'
    if path.exists():assert path.read_text(encoding='utf-8')==encoded
    else:path.write_text(encoded,encoding='utf-8')
    (OUT/'protocol_sha256.txt').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'\n',encoding='utf-8')
    print(json.dumps({'protocol':str(path),'source_files':len(hashes),'input_files':len(inputs),'future_pairs':4725,'GPU_started':False}))

if __name__=='__main__':main()
