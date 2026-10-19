"""Freeze bounded synthetic mechanism controls; never a task-benchmark aggregate."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase12_posc_layout_compiler import compile_layout, validate_topological_order
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text

FAMILIES = ('instruction_order', 'rag_evidence_position', 'tool_state', 'code_context', 'eos_boundary')
MODELS = ('Qwen3-8B', 'Mistral-7B-Instruct-v0.3', 'Llama-3.1-8B-Instruct')


def segment(sid, kind, text, deps, stable):
    return dict(segment_id=sid, segment_type=kind, text=text, dependencies=deps,
                token_count=max(1, len(text.split())), volatility=0.0 if stable else 1.0,
                cache_stability=1.0 if stable else 0.0, reuse_probability=1.0 if stable else 0.0)


def messages(case, order):
    # The SYS segment is the actual system message, not duplicated as user text.
    system=next(x for x in case['segments'] if x['segment_id']=='SYS')
    return [dict(role='system', content=system['text']),
            dict(role='user', content=_ordered_text([x for x in order if x!='SYS'], case['segments']))]


def compile_case(case):
    raw=[x['segment_id'] for x in case['segments']]
    result=compile_layout(case['segments'], policy='posc')
    order=result['topological_order']
    assert set(raw)==set(order) and len(raw)==len(order)
    assert not validate_topological_order(raw, case['segments'])
    assert not validate_topological_order(order, case['segments'])
    case.update(raw_order=raw, candidate_order=order,
                raw_messages=messages(case,raw), candidate_messages=messages(case,order),
                compiler='scripts.phase12_posc_layout_compiler.compile_layout(policy=posc)',
                compiler_result={k:v for k,v in result.items() if k!='compiled_text'})
    return case


def behavior_cases():
    rows=[]
    for family in FAMILIES:
        for variant in range(2):
            a,b=(('RED','BLUE'),('GREEN','YELLOW'))[variant]
            for control in ('safe', 'order_risk'):
                other=a if control=='safe' else b
                if family=='instruction_order':
                    system='Follow the last INSTRUCTION record in the user message. Return its color only. /no_think'
                    obs=f'INSTRUCTION: Return {other}.';doc=f'INSTRUCTION: Return {a}.'
                    query='Execute the last INSTRUCTION record.';answer=a
                elif family=='rag_evidence_position':
                    system='Resolve conflicting retrieved records using the last matching record in the supplied context. Return the requested value only. /no_think'
                    key=('Harbor','Orchard')[variant]
                    obs=f'Retrieved record: site={key}; status={other}.'
                    doc=f'Retrieved record: site={key}; status={a}.'
                    query=f'What is the status of site {key}?';answer=a
                elif family=='tool_state':
                    system='Tool snapshots are applied in message order; the last snapshot for a ticket is current. Output its state only. /no_think'
                    key=f'TICKET_{variant+31}'
                    obs=f'Tool snapshot: ticket={key}; state={other}.'
                    doc=f'Tool snapshot: ticket={key}; state={a}.'
                    query=f'Report the current state of {key}.';answer=a
                elif family=='code_context':
                    x,y=((7,3),(11,5))[variant];y=x if control=='safe' else y
                    system='Execute the Python assignments in the presented segment order. Later assignments override earlier ones. Output the final integer only. /no_think'
                    obs=f'factor = {y}\n';doc=f'factor = {x}\n'
                    query='What is factor * 6?';answer=str(x*6)
                else:
                    first=('READY','DONE')[variant]
                    system='Follow only the last FORMAT record. Do not add quotes, commentary, or markup. /no_think'
                    obs=(f'FORMAT: Output exactly {first} and then stop.' if control=='safe' else
                         f'FORMAT: Output exactly {first} CONTINUE and then stop.')
                    doc=f'FORMAT: Output exactly {first} and then stop.'
                    query='Apply the last FORMAT record.';answer=first
                filler='\nBackground glossary (contains no instructions): '+ ' '.join(f'entry_{i:03d}' for i in range(128))+'\n'
                stable_type='REPO_CONTEXT' if family=='code_context' else 'RAG_CHUNK'
                case=dict(case_id=f'{family}_v{variant}_{control}', family=family, variant=variant,
                    declared_risk=control, expected_raw_text=answer, output_budget=64,
                    scoring='exact normalized text against fixed raw-order task answer; no output-based case selection',
                    dependency_boundary='Both orders satisfy the supplied structural DAG. Deliberately unencoded order-sensitive semantics are the certification challenge; CALC is not claimed to infer missing semantic edges.',
                    segments=[segment('SYS','SYS_PROMPT',system,[],True),
                              segment('OBS','TOOL_OBS',obs,['SYS'],False),
                              segment('DOC',stable_type,filler+doc,['SYS'],True),
                              segment('QUERY','USER_QUERY',query,['OBS','DOC'],False)])
                rows.append(compile_case(case))
    return rows


def manifest_case(mislabel=False, value='ALPHA'):
    marker='SYNTHETIC_PRIVATE_CANARY_'+value+'_NOT_PERSONAL_DATA'
    system='This is a cache-boundary test using artificial data only. Ignore all records and return exactly ACK. No explanation. /no_think'
    private=marker+'\n'+' '.join('synthetic_padding_'+str(i) for i in range(64))
    segments=[segment('SYS','SYS_PROMPT',system,[],True),
              segment('PRIVATE','RAG_CHUNK' if mislabel else 'TOOL_OBS',private,['SYS'],mislabel),
              segment('DOC','RAG_CHUNK','Public operational manual. '+' '.join('public_rule_'+str(i) for i in range(160)),['SYS'],True),
              segment('QUERY','USER_QUERY','Return ACK now.',['PRIVATE','DOC'],False)]
    case=compile_case(dict(case_id='manifest_'+('mislabel' if mislabel else 'correct')+'_'+value,
                          family='synthetic_manifest',output_budget=32,expected_raw_text='ACK',segments=segments,
                          synthetic_marker=marker, trusted_semantic_mislabel=mislabel))
    manifest={'issuer':'trusted-operator','template_version':'mechanism-v1','authorization_domain':'domain-a',
              'segments':[dict(id=x['segment_id'],text=x['text'],content_hash=hashlib.sha256(x['text'].encode()).hexdigest(),
                               stable=x['volatility']==0,visibility='domain_shared' if x['volatility']==0 else 'tenant_private',
                               publish=x['volatility']==0) for x in segments]}
    case['manifest']=manifest
    return case


def build(output):
    if output.exists():raise FileExistsError(output)
    cases=behavior_cases()
    assert len(cases)==20 and all(x['candidate_order']==['SYS','DOC','OBS','QUERY'] for x in cases)
    plan={'schema_version':'contractkv.bounded-mechanism-controls.v1','models':MODELS,'fresh_process_repeats':3,
          'server_cells':9,'behavior_candidates_per_cell':20,'behavior_business_per_cell':80,
          'maximum_behavior_GPU_verifications_per_cell':20,'behavior_cases':cases,
          'manifest_cases':[manifest_case(m,v) for m in (False,True) for v in ('ALPHA','BETA')],
          'manifest_registration_controls':['explicit_private_publication','mutable_publication','untrusted_tenant_registration'],
          'manifest_business_controls':['matching_private_value_same_domain','different_private_value_same_domain',
                                        'matching_private_value_other_domain','stale_version'],
          'raw_margin_floor':0.0625,'candidate_and_eos_margin_floor':0.125,
          'maximum_manifest_GPU_verifications_per_cell':2,'maximum_manifest_business_per_cell':15,
          'execution':'Each fresh model process runs the two diagnostics sequentially under disjoint namespaces; serial requests. No cross-diagnostic performance comparison.',
          'claim_boundary':['Controlled synthetic mechanism challenge, not new benchmark accuracy or service capacity.',
                           'Uses observation-scoped actual-raw witnesses. Does not change inherited deployment-family eligibility or claim automatic certificate-mode switching.',
                           'The unchecked layout condition is not the previously deployed frozen-safe D1.',
                           'Optional read-only residency hooks add synchronous I/O; reported call costs are diagnostic costs, not serving-speed claims.',
                           'Two variants are controlled task instances, not two independent benchmark sources.',
                           'Manifest registration and binding mediation are a controlled trusted-client adapter, not a newly implemented public authentication gateway.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as f:json.dump(plan,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps({'cases':len(cases),'cells':9,'maximum_behavior_business':720,'maximum_behavior_verification':180,'manifest_cases':4}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output)
