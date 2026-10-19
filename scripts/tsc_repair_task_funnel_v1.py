"""Post-hoc CPU task-contract diagnostics; never changes admission or labels."""
import argparse
from collections import Counter
import codeop
import hashlib
import json
from pathlib import Path
import re
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r3_output_contract import python_statement_contract


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]
def probe(s):
    try:return 'incomplete_but_extendable' if codeop.compile_command(s,symbol='exec') is None else 'complete'
    except (SyntaxError,ValueError,OverflowError):return 'invalid_or_missing_context'
def normalized_code(text):
    value=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    if value.startswith('```') and value.endswith('```'):
        value=re.sub(r'^```(?:python|py)?\s*','',value);value=value[:-3].strip()
    return value


def main(root,output):
    assert not output.exists();study=root/'results/tsc_authorization_task_repair_20261019'
    state=read(study/'execution_state_v2.json');assert len(state['completed_cells'])==9
    prepared=read(study/'inputs_v1/cases_by_model_v1.json')
    packed=rows(study/'inputs_v1/faithful_selected_sessions_v1.jsonl')
    sources={s['revision_source_group']:s for s in packed}
    model_names={'qwen3-8b':'Qwen3-8B','mistral-7b':'Mistral-7B-Instruct-v0.3','llama-3.1-8b':'Llama-3.1-8B-Instruct'}
    data=[]
    for rel in state['completed_cells']:
        cell=study/rel;rr=rows(cell/'responses.jsonl');model=rr[0]['model']
        cases={c['case_id']:c for c in prepared[model_names[model]]['real_cases']}
        quals={(r['case_id'],r['phase']):r for r in rr if r['event']=='qualification'}
        business={(r['case_id'],r['condition']):r for r in rr if r['event']=='business'}
        for case in cases.values():
            sample=sources[case['source_group']]
            for phase in ('legacy','authorized'):
                raw=business[case['case_id'],phase+'_raw_witness']['response']
                repeat=business[case['case_id'],phase+'_raw_repeat']['response']
                qual=quals[case['case_id'],phase]['result']
                syntax=None;context=None;verbatim_context=None;single_line=None;no_wrapper_change=None
                if case['family']=='RepoBench':
                    syntax=python_statement_contract(raw['output_text'])
                    prefix=''.join(s['text'] for s in sample['segments'] if s['type']=='CODE_PREFIX')
                    first,sep,rest=prefix.partition('\n')
                    if sep and re.fullmatch(r'[A-Za-z0-9_./\\-]+\.py',first.strip()):prefix=rest
                    code=normalized_code(raw['output_text'])
                    context=probe(prefix+code)
                    verbatim_context=probe(prefix+raw['output_text'])
                    no_wrapper_change=raw['output_text'].strip()==code
                    single_line=sum(bool(s.strip()) for s in code.splitlines())==1
                margins=raw.get('reference_margins') or []
                raw_gate=bool(raw.get('witness_available') and margins and min(margins)>=.0625 and raw['finish_reason']=='stop')
                stable=bool(raw['success'] and repeat['success'] and raw['output_token_ids']==repeat['output_token_ids'] and raw['finish_reason']==repeat['finish_reason'])
                data.append(dict(cell=cell.parent.name,model=model,phase=phase,source_group=case['source_group'],
                    family=case['family'],inherited_level=case['level'],raw_natural_stop=raw['finish_reason']=='stop',
                    old_syntax_guard=syntax,normalized_output_nonblank_single_line=single_line,
                    prefix_plus_normalized_code_syntax=context,raw_margin_and_stop_gate_pass=raw_gate,
                    prefix_plus_verbatim_output_syntax=verbatim_context,normalization_only_whitespace=no_wrapper_change,
                    exact_Raw_repeat_observed=stable,issued=bool(qual.get('certificate_issued')),
                    failure_reason=qual.get('failure_reason',''),actual_RPCs=len(qual.get('attempts',[])),
                    plausible_single_line_context_false_rejection=bool(syntax is not None and not syntax['passed'] and single_line and no_wrapper_change and verbatim_context in {'complete','incomplete_but_extendable'}),
                    inherited_L0_with_Raw_evidence_but_candidate_untested=bool(case['family']=='RepoBench' and case['level']=='L0' and syntax['passed'] and raw_gate and stable),
                    gold_reference_used_in_admission_probe=False))
    assert len(data)==108
    summary=[]
    for model in model_names:
        subset=[r for r in data if r['model']==model]
        repo=[r for r in subset if r['family']=='RepoBench']
        summary.append(dict(model=model,witness_conditions=len(subset),RepoBench_witness_conditions=len(repo),
            inherited_Repo_L0=sum(r['inherited_level']=='L0' for r in repo),
            Repo_Raw_syntax_pass=sum(r['old_syntax_guard']['passed'] for r in repo),
            plausible_single_line_context_false_rejections=sum(r['plausible_single_line_context_false_rejection'] for r in repo),
            L0_Raw_evidence_opportunities_candidate_still_untested=sum(r['inherited_L0_with_Raw_evidence_but_candidate_untested'] for r in repo),
            actual_qualification_reasons=dict(Counter(r['failure_reason'] or 'PASS' for r in subset))))
    result=dict(schema_version='contractkv.task-funnel-posthoc.v1',new_GPU_requests=0,
        post_hoc_diagnostic_not_a_new_admission_rule=True,all_new_Raw_witness_conditions=108,
        summary=summary,rows=data,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        boundary='Syntax and Raw-margin evidence cannot establish that an untested candidate preserves behavior. A context-supported single line is a possible false-rejection diagnosis, not semantic correctness or authority to bypass the frozen family scope. No held-out source/threshold/rule changed.')
    with output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result['summary']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
