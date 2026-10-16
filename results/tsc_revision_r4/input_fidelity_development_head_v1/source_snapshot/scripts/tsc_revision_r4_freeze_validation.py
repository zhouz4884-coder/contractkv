"""Freeze both new-source protocols together before either sees model outcomes."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r2_freeze_scope import freeze_scope
from scripts.tsc_revision_r4_arrival_protocol import load_arrivals


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def csvread(path):return list(csv.DictReader(path.open(encoding='utf-8')))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();r4=root/'results/tsc_revision_r4'
    pilot=r4/'development_pilot_v1';clock=r4/'clock_smoke_v1'
    for base,count in [(pilot,18),(clock,2)]:
        audit=json.loads((base/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
        if not audit['execution_complete'] or audit['complete_cells']!=count:raise ValueError('Complete development and burst-clock audits first')
    qualities=csvread(pilot/'analysis/quality_summary_v1.csv');risk=[r for r in qualities if r['policy']=='risk-tail' and r['family']=='ALL']
    if len(risk)!=6 or any(int(r['compiled_material_drops']) for r in risk):raise ValueError('Balanced development has material compiled loss; retain and diagnose before new validation')
    nonruler=[r for r in qualities if r['policy']=='risk-tail' and r['family'] not in ('ALL','RULER')]
    if not any(int(r['compiled_pairs']) for r in nonruler):raise ValueError('No non-RULER development coverage')
    gate=json.loads((pilot/'analysis/strata_calibration_audit_v1.json').read_text(encoding='utf-8'))
    if gate['errors']:raise ValueError('Development admission audit failed')
    repeatcheck=r4/'development_repeat_check_v1'
    repeataudit=json.loads((repeatcheck/'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not repeataudit['execution_complete'] or repeataudit['complete_cells']!=8:raise ValueError('Complete the exactly2 extra paired development repeats for flagged tails first')
    repeatperformance=csvread(repeatcheck/'analysis/combined_performance_v1.csv')
    if any(int(r['compiled_material_drops']) for r in repeatperformance):raise ValueError('Repeat development material compiled loss requires diagnosis')
    parent=json.loads((repeatcheck/'freeze.json').read_text(encoding='utf-8'))
    for row in parent['files']:
        if sha(root/row['path'])!=row['sha256']:raise ValueError('Parent frozen bytes changed: '+row['path'])
    commitment=json.loads((r4/'inputs/input_commitment_v1.json').read_text(encoding='utf-8'))
    if commitment['excluded_sources']!=462 or commitment['selection_uses_model_outputs_or_scores']:raise ValueError('New source boundary')
    inputs={'single-session':'results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl','template-fanout':'results/tsc_revision_r4/inputs/heldout_fanout_v1.jsonl'}
    for path in inputs.values():
        if sha(root/path)!=commitment['cohorts'][Path(path).name]['sha256']:raise ValueError('Sealed input changed')
    lengthpath=r4/'formal_input_length_preflight_v1.json';lengthproof=json.loads(lengthpath.read_text(encoding='utf-8'))
    if not lengthproof['execution_complete'] or not lengthproof['all_fit'] or not lengthproof['all_known_API_IDs_match'] or lengthproof['requests_checked']!=4500:raise ValueError('Complete CPU tokenizer context preflight first; do not drop heldout sources')
    if not lengthproof['no_weights_loaded_no_model_forward'] or lengthproof['new50_model_outcomes_used']:raise ValueError('Tokenizer preflight boundary')
    if lengthproof['analysis_source_sha256']!=sha(root/'scripts/tsc_revision_r4_input_lengths.py'):raise ValueError('Tokenizer preflight code provenance')
    if lengthproof['generation_protocol_sha256']!=sha(root/'configs/tsc_revision_r1r_validation_protocol_v1.json') or lengthproof['model_registry_sha256']!=sha(r4/'model_registry_v1.json'):raise ValueError('Tokenizer/model binding')
    if any(lengthproof['input_sha256'][study]!=sha(root/path) for study,path in inputs.items()):raise ValueError('Tokenizer input binding')
    arrivalroot=r4/'arrivals_v2';arrivals=json.loads((arrivalroot/'arrival_commitment_v2.json').read_text(encoding='utf-8'))
    if not arrivals['only_observed_development_raw_timings'] or arrivals['new_validation_model_outcomes_used'] or arrivals['offered_load']!=.8 or not arrivals['model_specific_nominal_load']:raise ValueError('Arrival selection boundary')
    if set(arrivals['files'])!=set(inputs):raise ValueError('Arrival study coverage')
    if arrivals['generator_sha256']!=sha(root/'scripts/tsc_revision_r4_make_arrivals_v2.py') or arrivals['base_trace_generator_sha256']!=sha(root/'scripts/tsc_revision_r4_make_arrivals.py'):raise ValueError('Arrival generator provenance')
    for study,models in arrivals['files'].items():
        sessions=root/inputs[study];samples=[json.loads(x) for x in sessions.read_text(encoding='utf-8').splitlines()];tenants=1 if study=='single-session' else 10
        ids=[s['revision_session_id']+(f'-tenant{t:02d}' if tenants>1 else '') for s in samples for t in range(tenants)]
        if set(models)!={'Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'}:raise ValueError('Arrival model coverage')
        for model,records in models.items():
            if set(records)!={'1','2','3'}:raise ValueError('Arrival repeat coverage')
            for rep,record in records.items():
                path=root/record['path'];_,digest,trace=load_arrivals(path,sha(sessions),ids,tenants,2)
                if digest!=record['sha256'] or trace['model_identity']!=model or trace['nominal_offered_load']!=.8 or trace['repeat']!=int(rep):raise ValueError('Arrival hash/runtime binding')
                if not trace['common_across_policies_within_model'] or trace['seed']!=10672134+int(rep):raise ValueError('Arrival pairing/seed binding')
    for path in (r4/'validation_closed_v1',r4/'validation_arrival_v1'):
        if path.exists():raise ValueError('Preserve formal result directory; no post-test selection')
    comparison=csvread(pilot/'analysis/performance_comparison_v1.csv')
    overrides={(r['study'],r['model']):r for r in repeatperformance}
    demonstrated_tail_worsening=[r for r in comparison if r['policy']=='risk-tail' and
        float(overrides.get((r['study'],r['model']),{}).get('p99_reduction_ci95_high',r['p99_reduction_cluster_repeat_ci95_high']))<0]
    if demonstrated_tail_worsening:raise ValueError('Prespecified development rule requires resolving demonstrated tail worsening before formal freeze: '+json.dumps(demonstrated_tail_worsening))
    selection={'timestamp':datetime.now(timezone.utc).isoformat(),'selected_profile':'balanced','development_pilot_freeze_sha256':sha(pilot/'freeze.json'),
               'clock_smoke_freeze_sha256':sha(clock/'freeze.json'),'development_audit_sha256':sha(pilot/'analysis/completion_audit_v1.json'),
               'development_repeat_check_freeze_sha256':sha(repeatcheck/'freeze.json'),'development_repeat_check_audit_sha256':sha(repeatcheck/'analysis/completion_audit_v1.json'),
               'original_single_process_tail_rows_preserved':comparison,'targeted_three_process_tail_check':repeatperformance,
               'development_gate_audit_sha256':sha(pilot/'analysis/strata_calibration_audit_v1.json'),
               'selection_reason':'Retain the prespecified balanced profile with measured early screening, no material compiled development loss and non-RULER coverage. Preserve all full-wall/tail tradeoffs; no uniform tail gain or probability guarantee is assumed.',
               'other_profiles':'Conservative remains a declared unmeasured alternative; no claim that it was live tested.',
               'observed_performance_rows':comparison,'no_formal_model_outcomes_used':True,
               'both_protocols_frozen_before_first_new_forward':True,'distinct_new_sources':50,
               'matrix':'Closed raw+risk36 cells; fixed-arrival raw+previous+risk54 cells. Same50 sources, fanout first10, three paired fresh-process repeats; not100 independent sources.'}
    selectionpath=r4/'formal_selection_v1.json'
    with selectionpath.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(selection,indent=2)+'\n')
    configs={}
    for mode,policies,count,business in [('closed',['raw-order','risk-tail'],36,27000),('arrival',['raw-order','previous-refined','risk-tail'],54,40500)]:
        config={'schema_version':'tsc-r4.frozen-validation.v1','development_only':False,'models':['qwen','mistral','llama'],'policies':policies,'repeats':3,
                'studies':{'single-session':1,'template-fanout':10},'expected_cells':count,'expected_actual_generations':business,'expected_future_requests':business*9//10,
                'input_files':inputs,'selected_catalog':'results/tsc_revision_r4/development_fit_v3/calibration_v1.json','previous_catalog':'configs/tsc_revision_r3_catalog_v1.json',
                'generation_protocol':'configs/tsc_revision_r1r_validation_protocol_v1.json','profile':'balanced',
                'inherited_generation_fields_used':['runtime','layout','free_generation.budgets'],
                'admission_override':'One fixed candidate level per scope and at most one GPU attempt; inherited legacy descent text is not used by the selected R4 clients.',
                'CPU_input_length_preflight':'results/tsc_revision_r4/formal_input_length_preflight_v1.json',
                'input_adaptation':{'stable_word_limit':1500,'stable_pieces':16,'raw_layout':'agent-like tool observation before context',
                    'text_processing':'Inherited renderer collapses context whitespace while applying the word cap; these are benchmark-derived controlled inputs, not an exact author benchmark reproduction.'},
                'metric_boundary':'Preserve the frozen LongBench-style QA F1, RULER substring matching and legacy SequenceMatcher-based RepoBench edit-similarity implementation. No scorer is changed; no exact author RepoBench reproduction or semantic-correctness guarantee is claimed.',
                'selected_client':'scripts/tsc_revision_r4_live'+('_fixed' if mode=='arrival' else '')+'.py',
                'clock':('Frozen exogenous wave arrivals, identical across policies within model/repeat at model-specific nominal .8 development-raw load; shared two-request barrier; all planned idle, queueing, qualification and final drain included. Fixed-load result is not capacity.' if mode=='arrival' else 'Original closed-loop shared-wave readiness; all planning and synchronous qualification included in wall; paired throughput capacity measurement.'),
                'full_cost_boundary':'Server startup/pre-measurement infrastructure checks excluded identically; every actual business/controller/GPU qualification/failed attempt included. Audit/flush after drain reported separately.',
                'source_cluster_units':'Cold two-source shared-wave cohort; fanout source template with all tenants. Three paired fresh process repeats, not IID queries.',
                'policy_order':{'1':policies,'2':policies[1:]+policies[:1],'3':policies[2:]+policies[:2]},
                'score_thresholds':[0,.01,.03,.05],'latency_strata':['global','predefined family','template','tenant','request'],
                'nonuniform_tail_results_retained':True,'no_test_retuning':True,'reuse_hints_not_production_repetition_measurements':True,
                'cost_forecast_limits':'Development bootstrap predictors estimate early eligibility and qualification issuance, not post-certificate application-error probability. They are empirical, not formal risk bounds. The gate credits only currently observed issued-prefix warmth, not speculative future qualifications warming other query scopes. False negatives and capacity/tail tradeoffs are retained.',
                'dynamic_scope_boundary':{'key':'authorized template namespace and exact query digest; stable compiled prefix hash must match',
                    'digest_binds':'query text, full system message, stable segments, model, output budget, seed14014, temperature0, policy hash and renderer version',
                    'observation_schema':'[PRIVATE_TOOL_OBS] revision_session=<alnum_or_underscore_or_hyphen>; turn=<digits>; status=ready|completed|idle; no additional answer evidence. All fields must match the complete regex; CHAT_HISTORY/SCRATCHPAD are unqualified.',
                    'first_occurrence':'actual raw business output with complete answer/EOS witness before one single-shot qualification',
                    'query_shared_eligibility':'short nonabstaining answer; literal stable-context span or nonliteral raw minimum strictly above .125; backend raw .0625 and candidate/EOS .125 floors retained',
                    'nonshareable':'References failing the normalized <=16-word, nonabstaining, literal-or-margin eligibility receive exact-observation-only classification with no declared exact reuse and therefore L0. This is a structural heuristic, not a semantic detector of every free-form answer; it imposes no separate hard token-length limit.',
                    'scope_invalidation':'new query digest/namespace or changed stable content cannot reuse the old qualification; inherited dependency/layout eligibility remains required',
                    'changing_observation':'only the declared benchmark sessions are empirically audited. Reference eligibility is a heuristic; first-path qualification does not prove all future observation variants preserve free-generation behavior.'},
                'new_sources':50,'prior_sources_excluded':462,'no_positive_result_promised':True}
        if mode=='arrival':
            config['arrival_files']={study:{model:{rep:record['path'] for rep,record in records.items()} for model,records in models.items()} for study,models in arrivals['files'].items()}
            config['arrival_load_boundary']='Same frozen relative offsets across policies within model/repeat; nominal .8 of each model own observed development raw mean family service. Absolute rates differ across models; no achieved production utilization claim.'
        configpath=root/f'configs/tsc_revision_r4_validation_{mode}_v1.json'
        with configpath.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(config,indent=2)+'\n')
        configs[mode]=configpath
    seeds={r['path'] for r in parent['files']}
    seeds.update([selectionpath.relative_to(root).as_posix(),*(p.relative_to(root).as_posix() for p in configs.values()),
                  'scripts/tsc_revision_r4_freeze_validation.py','scripts/run_tsc_revision_r4_validation.sh','scripts/tsc_revision_r4_live_summary.py',
                  'scripts/tsc_revision_r4_input_lengths.py','results/tsc_revision_r4/formal_input_length_preflight_v1.json',
                  'scripts/tsc_revision_r4_audit_cell.py','scripts/tsc_revision_r4_strata_calibration.py','scripts/tsc_revision_r4_output_length_audit.py','scripts/tsc_revision_r4_make_arrivals.py','scripts/tsc_revision_r4_make_arrivals_v2.py',
                  'tests/test_tsc_revision_r4_make_arrivals.py','tests/test_tsc_revision_r4_model_arrivals.py','tests/test_tsc_revision_r1r_query_scope.py'])
    seeds.update(p.relative_to(root).as_posix() for p in arrivalroot.glob('*.json'))
    results={}
    for mode,configpath in configs.items():
        config=json.loads(configpath.read_text(encoding='utf-8'));base=r4/f'validation_{mode}_v1';base.mkdir();rows=[];index=0
        for study in config['studies']:
            for repeat in range(1,4):
                for model in config['models']:
                    for policy in config['policy_order'][str(repeat)]:rows.append({'cell':f'{study}_{model}_{policy}_r{repeat}','gpu_lane':index%2})
                    index+=1
        assign=base/'launcher_gpu_assignment_v1.csv'
        with assign.open('w',newline='',encoding='utf-8') as out:
            writer=csv.DictWriter(out,fieldnames=('cell','gpu_lane'));writer.writeheader();writer.writerows(rows)
        results[mode]=freeze_scope(root,base,configpath,seeds|{assign.relative_to(root).as_posix()},
            {'new50_model_outcomes_unused_at_freeze':True,'both_protocols_precommitted':True,'same_input_pool_between_protocols':True,'profile':'balanced'})
    print(json.dumps(results))


if __name__=='__main__':main()
