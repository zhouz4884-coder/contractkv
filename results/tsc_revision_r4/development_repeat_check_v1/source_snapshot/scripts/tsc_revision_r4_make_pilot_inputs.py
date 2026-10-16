"""Observed development inputs only; keep all 50 new validation sources sealed."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path('.');base=root/'results/tsc_revision_r4/development_inputs_v1'
    if base.exists():raise ValueError('Preserve development input version')
    previous=root/'results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl';pool=read(previous)
    cold=[];fan=[];counts=Counter()
    for row in pool:
        if counts[row['revision_family']]<2:cold.append(row)
        if counts[row['revision_family']]<1:fan.append(row)
        counts[row['revision_family']]+=1
    qwen=next(r for r in pool if r['revision_session_id']=='r3-heldout-52a55bace8746a75')
    older=root/'results/tsc_revision_r2/inputs/heldout_sealed_sessions_v1.jsonl'
    llama=next(r for r in read(older) if r['revision_session_id']=='r2-heldout-06af4efee2f5bbd3')
    for row in (qwen,llama):
        if row['revision_source_group'] not in {r['revision_source_group'] for r in cold}:cold.append(row)
    if len(cold)!=12 or len(fan)!=5:raise ValueError('Expected12observedcold and5templates')
    new=read(root/'results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl')
    if {r['revision_source_group'] for r in cold}&{r['revision_source_group'] for r in new}:raise ValueError('Dev overlaps new validation')
    base.mkdir(parents=True);files={}
    for name,rows in [('cold_sessions.jsonl',cold),('fanout_sessions.jsonl',fan)]:
        path=base/name
        with path.open('x',encoding='utf-8',newline='\n') as out:
            for row in rows:out.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        files[name]={'sha256':sha(path),'sources':len(rows),'source_groups':[r['revision_source_group'] for r in rows]}
    (base/'input_commitment_v1.json').write_text(json.dumps({'development_only':True,'all_sources_previously_observed':True,
        'selection':'First2/first1 per family of observedR3; add knownQwen doc99 and observedR2Llama doc181 to cold',
        'source_file_hashes':{previous.as_posix():sha(previous),older.as_posix():sha(older)},'files':files,
        'new_validation_sources_used':False},indent=2)+'\n',encoding='utf-8')
    config={'schema_version':'tsc-r4.development-serving-pilot.v1','development_only':True,
        'models':['qwen','mistral','llama'],'policies':['raw-order','previous-refined','risk-tail'],'repeats':1,
        'studies':{'single-session':1,'template-fanout':10},'expected_cells':18,
        'expected_actual_generations':5580,'expected_future_requests':5022,
        'input_files':{'single-session':(base/'cold_sessions.jsonl').as_posix(),'template-fanout':(base/'fanout_sessions.jsonl').as_posix()},
        'input_sha256':{k:v['sha256'] for k,v in files.items()},
        'selected_catalog':'results/tsc_revision_r4/development_fit_v3/calibration_v1.json',
        'previous_catalog':'configs/tsc_revision_r3_catalog_v1.json','selected_client':'scripts/tsc_revision_r4_live.py',
        'profile':'balanced','generation_protocol':'configs/tsc_revision_r1r_validation_protocol_v1.json',
        'clock':'DEVELOPMENT original shared-wave closed loop. Same scheduling/cost definition for all three controls. Does not establish same-exogenous-arrival p99 superiority.',
        'formal_protocol_requirement':'Freeze exogenous arrival offsets for raw/previous/new before formal forwards; keep shared-wave scheduling unless separately declared. All validation waiting and final drain inside full wall.',
        'metrics':['all-route/compiled/fallback official score and ANY/.01/.03/.05 drops','coverage and early/late rejection reasons','actual GPU calls/failures/full costs','pre/post predicted vs observed labelled outcomes with selective-label boundary','global/predefined-family/template/tenant/request tail latency','actual certified-prefix hits and forecast warm misses'],
        'quality_threshold':.03,'minimum_nonRULER_coverage_required_for_selection':True,
        'one_fresh_service_process_per_cell':True,'policy_order':'Rotate per atomic study/model block; all3 policies on sameGPU',
        'new_validation_model_outcomes_used':False,'no_positive_result_promised':True}
    target=root/'configs/tsc_revision_r4_development_pilot_v1.json'
    if target.exists():raise ValueError('Preserve pilot protocol')
    with target.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(config,indent=2)+'\n')
    print(json.dumps({'cold':12,'fan_templates':5,'cells':18,'business':5580,'futures':5022,
                      'config_sha256':sha(target),'files':{k:v['sha256'] for k,v in files.items()}}))


if __name__=='__main__':main()
