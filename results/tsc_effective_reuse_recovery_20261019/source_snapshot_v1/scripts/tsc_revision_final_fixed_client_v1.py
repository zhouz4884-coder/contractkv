"""Faithful fixed-arrival adapter with unchanged query-qualified R4 admission.

Repairs the fixed client's local renderer binding, installs the already checked
incomplete-reference fail-closed catch, and optionally disables economics only
for the separately frozen Gate OFF control. No scheduler is added.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r4_live_fixed as fixed
from scripts import tsc_revision_r4_cost_policy as cost
from scripts.tsc_revision_r4_fidelity_adapter_v2 import installed_adapter,ordered_text_preserving_segments
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text as historical_renderer
from scripts.tsc_revision_r2_admission import SingleShotRegistrar
from scripts.contractkv_verifier import VerificationIncomplete
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register

ECONOMIC_REASONS={'no_declared_remaining_reuse','post_reference_expected_net_rejected',
    'pre_reference_expected_net_rejected','cold_online_tail_budget_rejected'}


def economics_off(original):
    def decide(features,reuses,post_reference=False):
        result=original(features,reuses,post_reference)
        old_allow=result['allow_verification'];old_reason=result['reason']
        if old_reason in ECONOMIC_REASONS:
            result={**result,'allow_verification':True,'reason':'economic_gate_disabled_control'}
        return {**result,'economic_gate_control':'OFF','original_economic_allow':old_allow,'original_economic_reason':old_reason}
    return decide


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--client-audit',type=Path,required=True)
    parser.add_argument('--cpu-prompt-shapes',type=Path,required=True)
    parser.add_argument('--economic-gate',choices=['ON','OFF'],default='ON')
    own,remaining=parser.parse_known_args()
    assert not own.client_audit.exists(),'Never replace a client execution audit'
    assert fixed._ordered_text is historical_renderer
    original_register=SingleShotRegistrar.register;original_decide=cost.decide
    record=dict(schema_version='contractkv.faithful-fixed-client.v1',result='not_completed',
        original_fixed_client_sha256=sha(Path(fixed.__file__)),wrapper_sha256=sha(Path(__file__)),
        economic_gate=own.economic_gate,CPU_prompt_shapes_sha256=sha(own.cpu_prompt_shapes),
        fixed_arrival_scheduler_unchanged=True,shared_wave_barrier_unchanged=True,
        local_fixed_renderer_explicitly_bound=True,incomplete_reference_fail_closed='v5',
        safety_scope_margin_output_contract_and_PSTP_unchanged=True)
    try:
        with installed_adapter():
            fixed._ordered_text=ordered_text_preserving_segments
            SingleShotRegistrar.register=repaired_register(original_register,VerificationIncomplete)
            if own.economic_gate=='OFF':cost.decide=economics_off(original_decide)
            sys.argv=[str(Path(fixed.__file__)),*remaining]
            code=fixed.main()
        # Validate the actual transport IDs, not another inferred prompt length.
        output=Path(remaining[remaining.index('--output')+1])
        shapes={}
        for line in own.cpu_prompt_shapes.read_text(encoding='utf-8').splitlines():
            row=json.loads(line);key=(row['model'],row['source_group'],row['tenant'],row['turn'],row['condition'])
            assert key not in shapes;shapes[key]=row
        checked=0
        for line in output.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['row_type'] not in ('warm','future'):continue
            tenant=int(row['tenant_id'].rsplit('-tenant',1)[1])
            key=(row['model'],row['source_group'],tenant,row['turn_id'],'candidate' if row['effective_level']!='L0' else 'raw')
            expected=shapes[key]
            assert row['prompt_ids_sha256']==expected['prompt_ids_sha256'],'Actual Raw/compiled input differs from the frozen faithful renderer'
            assert len(row['prompt_token_ids'])==expected['prompt_tokens'] and row['output_budget']==expected['output_budget']
            checked+=1
        record.update(result='completed' if code==0 else 'client_failure',client_exit_code=code,
            actual_business_prompt_ID_hashes_checked=checked,all_actual_prompt_IDs_equal_CPU_precheck=True,
            raw_log_sha256=sha(output))
        return code
    except BaseException as error:
        record.update(result='failure_preserved',error_type=type(error).__name__,error_message=str(error));raise
    finally:
        fixed._ordered_text=historical_renderer
        SingleShotRegistrar.register=original_register;cost.decide=original_decide
        own.client_audit.parent.mkdir(parents=True,exist_ok=True)
        with own.client_audit.open('x',encoding='utf-8') as f:json.dump(record,f,indent=2);f.write('\n')


if __name__=='__main__':raise SystemExit(main())
