"""Combine paired fresh development processes without changing measured policy."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_audit_cell import audit_cell
from scripts.tsc_revision_r4_live_summary import clustered_ci,MODELS
from scripts.tsc_revision_summarize import read,write,first_divergence
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci
from scripts.tsc_revision_r2_select_policy import percentile

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 freeze=json.loads((a.root/'freeze.json').read_text());config=freeze['protocol'];snap=a.root/'source_snapshot';catalog=json.loads((snap/config['selected_catalog']).read_text())
 original=a.root.parent/'development_pilot_v1';oldfreeze=sha(original/'freeze.json');newfreeze=sha(a.root/'freeze.json');audits=[];pairs=[];performance=[];parents=[]
 for target in config['targets']:
  study=target['study'];alias=target['model'];model=MODELS[alias];samples=read(snap/config['input_files'][study]);expected={}
  for s in samples:
   for tenant in range(config['studies'][study]):expected[s['revision_session_id']+(f'-tenant{tenant:02d}' if config['studies'][study]>1 else '')]=s
  rawwall=policywall=0.;multipliers=[];condition=[]
  for rep in (1,2,3):
   base=original if rep==1 else a.root;cells={}
   for policy in config['policies']:
    cell=base/'cells'/f'{study}_{alias}_{policy}_r{rep}'
    audit,summary,rows,manifest=audit_cell(cell,expected,oldfreeze if rep==1 else newfreeze,catalog)
    if rep!=1:audits.append(audit)
    elif audit['errors']:raise ValueError('Original measured cell changed')
    cells[policy]=(summary,rows,manifest)
    parents.append({'cell':cell.as_posix(),'raw_sha256':sha(cell/'raw.jsonl'),'repeat':rep,'original_pilot':rep==1})
   rs,rr,rm=cells['raw-order'];ps,pr,pm=cells['risk-tail']
   if rm['declared_gpu_lane']!=pm['declared_gpu_lane']:raise ValueError('PairedGPU mismatch')
   for field in ('model_artifact_identity_sha256','installed_distribution_versions','native_extensions','numerical_environment'):
    if rm[field]!=pm[field]:raise ValueError('Paired runtime mismatch')
   raw={(r['session_id'],r['turn_id']):r for r in rr if r['row_type']=='future'}
   for r in pr:
    if r['row_type']!='future':continue
    ref=raw[r['session_id'],r['turn_id']]
    if r['effective_level']=='L0' and r['prompt_token_ids']!=ref['prompt_token_ids']:raise ValueError('L0prompt mismatch')
    row={'study':study,'model':model,'repeat':rep,'source_group':r['source_group'],'family':r['family'],'session_id':r['session_id'],'turn_id':r['turn_id'],
         'effective_level':r['effective_level'],'raw_ready_ttft_ms':ref['ready_ttft_ms'],'ready_ttft_ms':r['ready_ttft_ms'],'quality_drop':ref['task_score']-r['task_score'],
         'first_output_ID_divergence':first_divergence(ref['output_token_ids'],r['output_token_ids'])}
    pairs.append(row);condition.append(row)
   rawwall+=rs['wall_s_including_all_setup_and_verification'];policywall+=ps['wall_s_including_all_setup_and_verification'];multipliers.append(rs['wall_s_including_all_setup_and_verification']/ps['wall_s_including_all_setup_and_verification'])
  cohorts={s['revision_source_group']:'wave-'+str(i//2) for i,s in enumerate(samples)}
  cirows=[{**r,'source_group':cohorts[r['source_group']]} for r in condition] if study=='single-session' else condition
  lo,hi=clustered_tail_ci(cirows);ml,mh=clustered_ci(cirows);compiled=[r for r in condition if r['effective_level']!='L0']
  performance.append({'study':study,'model':model,'paired_fresh_process_repeats':3,'pairs':len(condition),'raw_p99_ms':percentile([r['raw_ready_ttft_ms'] for r in condition],.99),
    'policy_p99_ms':percentile([r['ready_ttft_ms'] for r in condition],.99),'p99_reduction_ci95_low':lo,'p99_reduction_ci95_high':hi,
    'ready_mean_reduction_ci95_low':ml,'ready_mean_reduction_ci95_high':mh,'full_wall_goodput_multiplier':rawwall/policywall,'repeat_goodput_multiplier_min':min(multipliers),
    'repeat_goodput_multiplier_max':max(multipliers),'compiled_pairs':len(compiled),'compiled_material_drops':sum(r['quality_drop']>.03 for r in compiled),
    'compiled_any_score_decrease':sum(r['quality_drop']>0 for r in compiled),'fallback_material_drops':sum(r['quality_drop']>.03 and r['effective_level']=='L0' for r in condition)})
 a.output.mkdir(parents=True,exist_ok=True);write(a.output/'combined_performance_v1.csv',performance);write(a.output/'quality_pairs_v1.csv',pairs)
 proof={'schema_version':'tsc-r4.development-repeat-completion.v1','execution_complete':len(audits)==8 and not any(x['errors'] for x in audits),'cases':audits,
        'complete_cells':len(audits),'expected_cells':8,'measured_futures':sum(x['future_requests'] for x in audits),'expected_futures':2232,
        'combined_pairs_with_original_r1':len(pairs),'parent_pilot_archive_sha256':config['original_pilot_archive_sha256'],'parent_inputs':parents,
        'scientific_success_is_separate':True,'policy_unchanged':True,'new50_model_outcomes_used':False}
 if proof['measured_futures']!=2232:proof['execution_complete']=False
 (a.output/'completion_audit_v1.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps({'complete':proof['execution_complete'],'performance':performance}))
 return 0 if proof['execution_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
