"""Source-derived legacy/faithful serving orders; no tokenizer or inference."""
import argparse
from collections import Counter,defaultdict
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def collapse(values):
    result=[]
    for value in values:
        if not result or result[-1]!=value:result.append(value)
    return ' > '.join(result)


def main(root,output,condition):
    assert not output.exists()
    if condition=='legacy_R4':
        study=root/'results/tsc_revision_r4/validation_closed_v1';snapshot=study/'source_snapshot';freeze=read(study/'freeze.json')
        inventory={x['path']:x['sha256'] for x in freeze['files']}
        protocol_path=snapshot/freeze['protocol']['generation_protocol'];inputs=snapshot/freeze['protocol']['input_files']['single-session']
    else:
        study=root/'results/tsc_task_faithful_open_arrival_20261018';snapshot=study/'source_snapshot_v1';freeze=read(study/'raw_calibration_freeze_v1.json')
        inventory={x['path']:x['sha256'] for x in freeze['snapshot_files']}
        protocol_path=root/'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json'
        inputs=study/'inputs_v1/faithful_selected_sessions_v1.jsonl'
        bindings={x['path']:x['sha256'] for x in freeze['files']}
        assert sha(protocol_path)==bindings[protocol_path.relative_to(root).as_posix()]
        assert sha(inputs)==bindings[inputs.relative_to(root).as_posix()]
    if condition=='legacy_R4':
        assert sha(protocol_path)==inventory[protocol_path.relative_to(snapshot).as_posix()]
        assert sha(inputs)==inventory[inputs.relative_to(snapshot).as_posix()]
    sys.path.insert(0,str(snapshot))
    from scripts import tsc_revision_live as original
    from scripts.phase22_llama_layout_ladder import validate_topological_order
    if condition=='faithful_bridge':
        from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter
        context=installed_adapter()
    else:context=nullcontext()
    protocol=read(protocol_path);samples=[json.loads(x) for x in inputs.read_text(encoding='utf-8').splitlines()]
    assert len(samples)==(50 if condition=='legacy_R4' else 6)
    records=[];patterns=defaultdict(Counter);empty=Counter();protected=Counter()
    args=SimpleNamespace(protocol=protocol,experiment='free-generation',model_identity='Qwen3-8B',output_budget=0)
    with context:
        for sample in samples:
            for turn in range(10):
                case,raw,candidate,messages,_=original.make_turn(args,deepcopy(sample),turn)
                by_id={s['segment_id']:s for s in case['segments']}
                assert not validate_topological_order(raw['topological_order'],case['segments'])
                actual=[by_id[s] for s in raw['topological_order']]
                order=collapse(s['segment_type'] for s in actual);patterns[sample['revision_family']][order]+=1
                for s in actual:
                    if not s['text']:empty[s['segment_type']]+=1
                checks=[]
                if condition=='faithful_bridge':
                    for s in sample['segments']:
                        if s['type'] in ('USER_QUERY','CODE_PREFIX'):
                            assert s['text'] in messages[1]['content'];checks.append(s['type']);protected[s['type']]+=1
                assert [m['role'] for m in messages]==['system','user']
                records.append(dict(family=sample['revision_family'],source_group=sample['revision_source_group'],turn=turn,
                    user_body_segment_order=order,outer_chat_roles=['system','user'],
                    messages_sha256=hashlib.sha256(json.dumps(messages,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                    TOOL_OBS_before_context=next(i for i,s in enumerate(actual) if s['segment_type']=='TOOL_OBS')==1,
                    protected_fields_checked=checks))
    imported=[]
    for name,module in list(sys.modules.items()):
        if not name.startswith('scripts.') or not getattr(module,'__file__',None):continue
        path=Path(module.__file__).resolve()
        if path.suffix!='.py':continue
        rel=path.relative_to(snapshot.resolve()).as_posix();assert rel in inventory and sha(path)==inventory[rel],rel
        imported.append(dict(path=rel,sha256=sha(path)))
    result=dict(schema_version='contractkv.serving-order-CPU.v1',condition=condition,sources=len(samples),rendered_requests=len(records),
        input_sha256=sha(inputs),protocol_sha256=sha(protocol_path),imported_frozen_sources=imported,
        family_order_patterns={family:dict(values) for family,values in patterns.items()},empty_node_counts=dict(empty),
        protected_field_text_checks=dict(protected),requests=records,new_GPU_requests=0,
        controlled_TOOL_OBS_not_production_trace=True,no_growing_CHAT_HISTORY_in_this_serving_adapter=True,
        boundary='CPU execution of the archived renderer, no token-count inference or new behavior/hit claim; independent TableI actual history requests are a different protocol.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('requests','imported_frozen_sources')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--condition',choices=['legacy_R4','faithful_bridge'],required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output,args.condition)
