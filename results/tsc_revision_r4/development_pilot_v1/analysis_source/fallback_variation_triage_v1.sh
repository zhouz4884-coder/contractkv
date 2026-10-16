set -euo pipefail
cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
/home/user/miniconda3/envs/contractkv-cu128/bin/python - <<'PY'
from pathlib import Path
import json,hashlib
from scripts.tsc_revision_summarize import read,first_divergence
base=Path('results/tsc_revision_r4/development_pilot_v1');sid='r3-heldout-4a1d9a5f4190d1cb';turn=3
selected={};summaries={}
for policy in ('raw-order','risk-tail','previous-refined'):
 cell=base/f'cells/single-session_mistral_{policy}_r1';rows=read(cell/'raw.jsonl');r=next(r for r in rows if r['row_type']=='future' and r['session_id']==sid and r['turn_id']==turn)
 selected[policy]={k:r[k] for k in ('request_id','output_text','output_token_ids','prompt_ids_sha256','prompt_tokens','effective_level','prefix_hit_tokens','new_prefill_tokens','task_score','finish_reason','query_scope')}
 selected[policy]['prompt_IDs_match_raw']=r['prompt_token_ids']==next((x['prompt_token_ids'] for x in rows if x['row_type']=='future' and x['session_id']==sid and x['turn_id']==turn),[])
 summaries[policy]={'input_raw_file_sha256':hashlib.sha256((cell/'raw.jsonl').read_bytes()).hexdigest(),
                    'scope_verifications':[{'failure_reason':x['failure_reason'],'GPU_calls':len(x['attempts']),'issued':x['certificate_issued']} for x in rows if x['row_type']=='verification' and x['session_id']==sid]}
raw=next(r for r in read(base/'cells/single-session_mistral_raw-order_r1/raw.jsonl') if r['row_type']=='future' and r['session_id']==sid and r['turn_id']==turn)
for policy in ('risk-tail','previous-refined'):
 r=next(r for r in read(base/f'cells/single-session_mistral_{policy}_r1/raw.jsonl') if r['row_type']=='future' and r['session_id']==sid and r['turn_id']==turn)
 selected[policy]['prompt_IDs_match_raw']=r['prompt_token_ids']==raw['prompt_token_ids'];selected[policy]['first_output_ID_divergence']=first_divergence(raw['output_token_ids'],r['output_token_ids'])
sample=next(s for s in read(Path('results/tsc_revision_r4/development_inputs_v1/cold_sessions.jsonl')) if s['revision_session_id']==sid)
result={'schema_version':'tsc-r4.development-fallback-variation-triage.v1','offline_after_outputs_only':True,'source_group':sample['revision_source_group'],'session_id':sid,'turn':turn,
        'gold_answers_for_offline_metric_inspection_only':sample.get('answer'),'outputs':selected,'evidence':summaries,
        'mechanism_cause_status':'unresolved; same prompt IDs are necessary but do not identify numerical/batch/cache cause. No generation or scorer was changed.'}
(base/'fallback_variation_triage_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
PY
