set -euo pipefail
cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
/home/user/miniconda3/envs/contractkv-cu128/bin/python - <<'PY'
import json
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_summarize import read
base=Path('results/tsc_revision_r4/development_pilot_v1');cfg=json.loads((base/'freeze.json').read_text())['protocol']
samples={s['revision_session_id']:s for s in read(Path(cfg['input_files']['template-fanout']))};protocol=json.loads(Path(cfg['generation_protocol']).read_text())
out=[]
for name in ('qwen','llama'):
 rows=read(base/f'cells/template-fanout_{name}_risk-tail_r1/raw.jsonl');plans={(r['certificate_namespace'],r['query_scope']):r for r in rows if r['row_type']=='prospective_plan'}
 first={};last={}
 for r in rows:
  if r['row_type'] in ('warm','future') and r['scope_first_decision_business']:
   key=r['certificate_namespace'],r['query_scope'];first.setdefault(key,r);last[key]=r
 counts={'non_L0_plans':0,'first_owner_case_matches':0,'last_owner_case_matches':0,'only_tool_observation_diff':0}
 for key,plan in plans.items():
  if 'scope_case' not in plan:continue
  counts['non_L0_plans']+=1
  def case(row):
   sample=deepcopy(samples[row['certificate_namespace']]);sample['revision_session_id']=row['session_id'];sample['shared_template_id']=row['certificate_namespace']
   args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity=row['model'],policy_hash='irrelevant_for_case')
   return {'segments':prepare(args,sample,row['turn_id'])[0]['segments']}
  a=case(first[key]);b=case(last[key]);stored=plan['scope_case']
  counts['first_owner_case_matches']+=stored==a;counts['last_owner_case_matches']+=stored==b
  counts['only_tool_observation_diff']+=stored!=b and [s for s in stored['segments'] if s['segment_type']!='TOOL_OBS']==[s for s in b['segments'] if s['segment_type']!='TOOL_OBS']
 out.append({'model':name,**counts})
print(json.dumps(out))
PY
