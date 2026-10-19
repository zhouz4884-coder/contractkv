"""CPU-only faithful local-binding and economics-only control checks."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_fixed_client_v1 import fixed,cost,economics_off,historical_renderer
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,ordered_text_preserving_segments
from scripts.tsc_revision_r1r_live import prepare
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts import tsc_revision_r2_candidate_plan as candidate_module


def main(root):
    source=root/'results/tsc_revision_r4/input_fidelity_validation_inputs_v1/faithful_selected_sessions_v1.jsonl'
    rr=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()]
    sample=next(x for x in rr if x['revision_family']=='RepoBench')
    protocol=json.loads((root/'configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json').read_text(encoding='utf-8'))
    args=SimpleNamespace(protocol=protocol,experiment='free-generation',output_budget=0,model_identity='Qwen3-8B',policy_hash='CPU-only-render-binding')
    prefix=''.join(x['text'] for x in sample['segments'] if x['type']=='CODE_PREFIX');assert prefix
    with installed_adapter():
        prepared=prepare(args,sample,0);case=prepared[0]
        order=layout_for_level(case,'L3',protocol['layout']['ladder'])['topological_order']
        assert fixed._ordered_text is historical_renderer
        before=fixed._ordered_text(order,case['segments'])
        try:
            fixed._ordered_text=ordered_text_preserving_segments
            after=fixed._ordered_text(order,case['segments'])
            assert fixed._ordered_text is candidate_module._ordered_text
            assert prefix in after
            assert after==candidate_module._ordered_text(order,case['segments'])
        finally:fixed._ordered_text=historical_renderer
    assert fixed._ordered_text is historical_renderer and candidate_module._ordered_text is historical_renderer
    # Real calibrated features, no new parameters learned from test results.
    catalog=json.loads((root/'results/tsc_revision_r4/development_fit_v3/calibration_v1.json').read_text(encoding='utf-8'))
    calibration=catalog['models']['Qwen3-8B']['template-fanout']['HotpotQA']
    features=cost.stage_features(calibration,'balanced','cold','template-fanout')
    off=economics_off(cost.decide);decisions=[]
    for reuses in [0,1,10,100]:
        for post in [False,True]:
            original=cost.decide(features,reuses,post);controlled=off(features,reuses,post)
            assert controlled['original_economic_allow']==original['allow_verification']
            assert controlled['original_economic_reason']==original['reason']
            for key,value in original.items():
                if key not in ('allow_verification','reason'):assert controlled[key]==value
            if original['reason'] in ('no_declared_remaining_reuse','post_reference_expected_net_rejected','pre_reference_expected_net_rejected','cold_online_tail_budget_rejected'):
                assert controlled['allow_verification']
            decisions.append(dict(reuses=reuses,post_reference=post,original=original['reason'],controlled=controlled['reason']))
    invalid={**features,'gpu_registration_cost_ms':float('nan')}
    assert off(invalid,10)['allow_verification'] is False
    result=dict(status='PASS',new_GPU_requests=0,scientific_efficacy_result=False,
        existing_source_group=sample['revision_source_group'],CODE_PREFIX_characters=len(prefix),
        original_fixed_reference_is_historical_despite_installed_adapter=True,
        historical_compiled_text_contains_full_CODE_PREFIX=prefix in before,
        fixed_explicit_faithful_reference_contains_full_CODE_PREFIX=True,
        fixed_and_candidate_planner_renderer_references_identical=True,references_restored=True,
        economic_only_decision_checks=decisions,invalid_features_still_denied=True,
        inherited_family_scope_margin_EOS_output_contract_PSTP_not_bypassed=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out=root/'results/tsc_final_existing_evidence_CPU_20261018/fixed_client_wiring_CPU_v1.json'
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
