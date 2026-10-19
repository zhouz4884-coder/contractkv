"""Phase-three diagnosis from sealed R3 evidence, without new model inference."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r1r_live import prepare
from scripts.tsc_revision_r2_select_policy import percentile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def write(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve this diagnostic version')
    base = args.root / 'results/tsc_revision_r3/validation_v1'
    audit = json.loads((base / 'analysis/completion_audit_v1.json').read_text(encoding='utf-8'))
    if not audit['execution_complete']:
        raise ValueError('Sealed complete R3 evidence required')
    scopes, inputs, tails, qwen = [], [], [], []
    for directory in sorted((base / 'cells').glob('*_margin-benefit_r*')):
        rawdir = directory.with_name(directory.name.replace('_margin-benefit_', '_raw-order_'))
        rows, raw = read(directory / 'raw.jsonl'), read(rawdir / 'raw.jsonl')
        for folder in (directory, rawdir):
            digest = sha(folder / 'raw.jsonl')
            closed = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
            if digest != closed['raw_file_sha256'] or not closed['execution_complete']:
                raise ValueError('Changed or incomplete raw source')
            inputs.append({'cell': folder.name, 'raw_sha256': digest})
        baseline = {(r['session_id'], r['turn_id']): r for r in raw if r['row_type'] in ('warm', 'future')}
        witnesses, plans, business = {}, {}, defaultdict(list)
        for r in rows:
            if r['row_type'] in ('warm', 'future'):
                key = r['certificate_namespace'], r['query_scope']
                business[key].append(r)
                if r['scope_first_raw_business']:
                    witnesses[key] = r
            elif r['row_type'] == 'prospective_plan':
                plans[r['certificate_namespace'], r['query_scope']] = r
        for r in rows:
            if r['row_type'] != 'verification':
                continue
            key = r['certificate_namespace'], r['query_scope']; witness = witnesses.get(key); plan = plans[key]
            compiled = [x for x in business[key] if x['effective_level'] != 'L0']
            gains = [baseline[x['session_id'], x['turn_id']]['ttft_ms'] - x['ttft_ms'] for x in compiled]
            scopes.append({'cell': directory.name, 'study': rows[-1].get('study', business[key][0]['study']),
                           'model': business[key][0]['model'], 'repeat': business[key][0]['repeat'],
                           'source_group': business[key][0]['source_group'], 'family': r['family'],
                           'query_scope': key[1], 'declared_remaining_reuse_hint': plan['declared_remaining_reuse_hint'],
                           'prospective_allowed': plan['allow_verification'],
                           'predicted_saved_ms': plan['estimated_saved_ms'], 'predicted_cost_ms': plan['estimated_cost_ms'],
                           'actual_GPU_calls': len(r['attempts']), 'issued': r['certificate_issued'],
                           'failure_reason': r['failure_reason'], 'complete_controller_ms': r['complete_verification_ms'],
                           'compiled_business_requests': len(compiled),
                           'observed_backend_ttft_difference_sum_ms': sum(gains),
                           'observed_backend_ttft_difference_mean_ms': statistics.fmean(gains) if gains else None,
                           'raw_witness_tokens': len(witness['output_token_ids']) if witness else None,
                           'raw_min_margin': min(witness['reference_margins']) if witness else None,
                           'raw_witness_latency_difference_from_baseline_ms': witness['latency_ms'] - baseline[witness['session_id'], witness['turn_id']]['latency_ms'] if witness else None})
        future = [r for r in rows if r['row_type'] == 'future']
        frozen_l0 = {'Qwen3-8B': set(), 'Mistral-7B-Instruct-v0.3': {'Qasper', 'RepoBench'},
                     'Llama-3.1-8B-Instruct': {'Qasper', 'RepoBench'}}[future[0]['model']]
        fixed = [r for r in future if r['family'] in frozen_l0]
        zero_other = [r['ready_ttft_ms'] if r['family'] in frozen_l0 else 0.0 for r in future]
        tails.append({'cell': directory.name, 'model': future[0]['model'], 'study': future[0]['study'],
                      'actual_global_p99_ms': percentile([r['ready_ttft_ms'] for r in future], .99),
                      'fixed_L0_only_p99_ms': percentile([r['ready_ttft_ms'] for r in fixed], .99) if fixed else None,
                      'conditional_global_p99_if_every_other_request_zero_ms': percentile(zero_other, .99),
                      'tail_top1pct_fixed_L0_count': sum(r['family'] in frozen_l0 for r in sorted(future, key=lambda x:x['ready_ttft_ms'], reverse=True)[:max(1, len(future)//100)]),
                      'counterfactual_boundary': 'Arithmetic with observed fixed-L0 latencies held constant, not a new serving measurement or immutable hardware lower bound.'})
        if directory.name.startswith('single-session_qwen_'):
            chosen = [r for r in rows if r['row_type'] in ('warm', 'future') and r['session_id'] == 'r3-heldout-52a55bace8746a75']
            one, seven = next(r for r in chosen if r['turn_id']==1), next(r for r in chosen if r['turn_id']==7)
            raw1, raw7 = baseline[one['session_id'], 1], baseline[one['session_id'], 7]
            qwen.append({'cell': directory.name, 'same_raw_prompt_length': len(raw1['prompt_token_ids']) == len(raw7['prompt_token_ids']),
                         'raw_prompt_token_changes': [{'position':i, 't1':a, 't7':b} for i,(a,b) in enumerate(zip(raw1['prompt_token_ids'],raw7['prompt_token_ids'])) if a != b],
                         'raw_reference_margin_at_first_output_divergence_24': one['reference_margins'][24],
                         'raw_reference_minimum_positions': [i for i,x in enumerate(one['reference_margins']) if x == min(one['reference_margins'])],
                         'first_reference_text': one['output_text'], 'raw_future_text':raw7['output_text'],
                         'compiled_future_identical_to_reference':one['output_token_ids']==seven['output_token_ids']})
    grouped = defaultdict(list)
    for r in scopes:grouped[r['study'],r['model'],r['family']].append(r)
    summary = []
    for (study,model,family),group in sorted(grouped.items()):
        called = [r for r in group if r['actual_GPU_calls']]
        issued = [r for r in group if r['issued']]
        summary.append({'study':study,'model':model,'family':family,'source_units':len({r['source_group'] for r in group}),
                        'plans':len(group),'prospective_rejected':sum(not r['prospective_allowed'] for r in group),
                        'GPU_calls':len(called),'issued':len(issued),'p_pass_given_GPU_call':len(issued)/len(called) if called else None,
                        'qualification_complete_p95_ms':percentile([r['complete_controller_ms'] for r in called],.95) if called else None,
                        'issued_backend_saving_mean_ms':statistics.fmean(r['observed_backend_ttft_difference_mean_ms'] for r in issued if r['compiled_business_requests']) if any(r['compiled_business_requests'] for r in issued) else None,
                        'failed_qualification_complete_sum_ms':sum(r['complete_controller_ms'] for r in called if not r['issued'])})
    protocol = json.loads((args.root/'configs/tsc_revision_r1r_validation_protocol_v1.json').read_text(encoding='utf-8'))
    sample = next(r for r in read(args.root/'results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl') if r['revision_session_id']=='r3-heldout-52a55bace8746a75')
    namespace = SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity='Qwen3-8B',policy_hash=sha(base/'freeze.json'))
    a,b = prepare(namespace,sample,1),prepare(namespace,sample,7)
    segment_diff = [{'segment_id':x['segment_id'],'type':x['segment_type'],'t1':x['text'],'t7':y['text']} for x,y in zip(a[0]['segments'],b[0]['segments']) if x['text']!=y['text']]
    result = {'schema_version':'tsc-r4.prior-evidence-diagnosis.v1','new_inference_requests':0,
              'source_cells':inputs,'Qwen_known_failure':qwen,'actual_changed_segments':segment_diff,
              'same_query_scope':a[4]==b[4],'task_evidence_changed':any(r['type']!='TOOL_OBS' for r in segment_diff),
              'observed_development_only':True,'analysis_source_sha256':sha(Path(__file__)),
              'boundary':'Backend TTFT differences, LP witness latency differences and fixed-L0 arithmetic are descriptive paired diagnostics, not replacement full-wall service results. Repeated sources and queries are correlated.'}
    args.output.mkdir(parents=True)
    write(args.output/'scope_costs_v1.csv', scopes);write(args.output/'family_diagnosis_v1.csv',summary);write(args.output/'conditional_tail_floor_v1.csv',tails)
    (args.output/'diagnosis_v1.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scopes':len(scopes),'prospective_rejected':sum(not r['prospective_allowed'] for r in scopes),
                      'Qwen_changed_segments':segment_diff,'same_query_scope':a[4]==b[4],
                      'Qwen_raw_margin_at_divergence':[r['raw_reference_margin_at_first_output_divergence_24'] for r in qwen]}))


if __name__=='__main__':main()
