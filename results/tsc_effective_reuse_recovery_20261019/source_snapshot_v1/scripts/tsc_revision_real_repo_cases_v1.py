"""Freeze real RepoBench L0-identity/L3 cases from blind packed inputs, CPU only."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,ordered_text_preserving_segments
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.phase12_posc_layout_compiler import validate_topological_order


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root):
    study=root/'results/tsc_real_repobench_mechanism_20261018'
    inputs=study/'inputs_v1/faithful_selected_sessions_v1.jsonl'
    metadata=json.loads((study/'inputs_v1/preparation_record_v1.json').read_text(encoding='utf-8'))
    for x in metadata['data_files']:assert sha(root/x['path'])==x['sha256']
    source_rows=[json.loads(x) for x in inputs.read_text(encoding='utf-8').splitlines()]
    assert len(source_rows)==3 and len({x['revision_source_group'] for x in source_rows})==3
    generation=root/'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json'
    protocol=json.loads(generation.read_text(encoding='utf-8'));assert protocol['free_generation']['budgets']['RepoBench']==384
    args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity='Qwen3-8B',policy_hash='CPU-frozen-real-repo')
    cases=[]
    for row in source_rows:
        sample=deepcopy(row);sample['shared_template_id']=row['revision_session_id'];sample['revision_session_id']+='-tenant00'
        case,raw,_,budget,_=prepare(args,sample,0)
        assert budget==384
        prefix=''.join(x['text'] for x in row['segments'] if x['type']=='CODE_PREFIX');assert prefix and prefix in raw[1]['content']
        for level in ['L0','L3']:
            order=layout_for_level(case,level,protocol['layout']['ladder'])['topological_order']
            assert not validate_topological_order(order,case['segments'])
            candidate=[raw[0],dict(role='user',content=ordered_text_preserving_segments(order,case['segments']))]
            assert prefix in candidate[1]['content']
            if level=='L0':assert candidate==raw
            byid={x['segment_id']:x for x in case['segments']};stable=[]
            for sid in order:
                if byid[sid]['segment_type']=='USER_QUERY' or byid[sid]['volatility']>=.5:break
                stable.append(sid)
            stable_messages=[raw[0],dict(role='user',content=ordered_text_preserving_segments(stable,case['segments']))]
            cases.append(dict(case_id='real_repo_'+hashlib.sha256(row['revision_source_group'].encode()).hexdigest()[:12]+'_'+level,
                source_group=row['revision_source_group'],family='real_RepoBench_next_line',diagnostic_layout_level=level,
                declared_risk='identity_control' if level=='L0' else 'dependency_legal_unassessed_candidate',
                dataset=row['dataset'],task=row['task'],answer=row.get('answer',''),output_budget=budget,
                segments=case['segments'],raw_order=layout_for_level(case,'L0',protocol['layout']['ladder'])['topological_order'],
                candidate_order=order,raw_messages=raw,candidate_messages=candidate,candidate_prefix_messages=stable_messages,
                CODE_PREFIX_characters=len(prefix),CODE_PREFIX_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
                output_contract='one_python_statement',scope='exact raw messages + actual candidate IDs + output budget',
                scorer='unchanged scripts.phase20a_official_quality.standard_score RepoBench edit similarity'))
    plan=dict(schema_version='contractkv.real-repobench-mechanism.v1',models=['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct'],
        fresh_process_repeats=1,server_cells=3,behavior_cases=cases,raw_margin_floor=.0625,candidate_and_eos_margin_floor=.125,
        behavior_candidates_per_cell=6,business_per_cell=24,total_business=72,maximum_qualification_RPCs=18,
        input_preparation_sha256=sha(study/'inputs_v1/preparation_record_v1.json'),packed_input_sha256=sha(inputs),
        CPU_prompt_shapes_sha256=sha(study/'inputs_v1/CPU_prompt_shapes_v1.jsonl'),
        generation_protocol_sha256=sha(generation),builder_source_sha256=sha(Path(__file__)),
        candidate_selection='All three new blind-selected sources, both predeclared layouts, all three models; no model result used.',
        production_inherited_family_eligibility_unchanged=True,
        claim_boundary=['Controlled private diagnostic, not a production Mistral/Llama RepoBench eligibility override.',
            'L0 certified identity is a diagnostic control; it is not compiled production L0 routing or an acceleration claim.',
            'Exact observation reuse, unchanged one_python_statement guard. Fragmentary next-line answers may be rejected.',
            'All labels used only for task scoring; online scope, margin, syntax and publication do not inspect gold.',
            'One model process each and three repositories; no large-sample or three-repeat guarantee.'])
    path=study/'protocol_v1.json'
    with path.open('x',encoding='utf-8') as f:json.dump(plan,f,ensure_ascii=False,indent=2);f.write('\n')
    extra=study/'source_extra';extra.mkdir()
    guard=root/'scripts/tsc_revision_r3_output_contract.py'
    with (extra/guard.name).open('xb') as f:f.write(guard.read_bytes())
    print(json.dumps(dict(cases=len(cases),protocol_sha256=sha(path),real_sources=3,new_GPU_requests=0,unchanged_output_contract_source_sha256=sha(guard))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    with installed_adapter():main(p.parse_args().root.resolve())
