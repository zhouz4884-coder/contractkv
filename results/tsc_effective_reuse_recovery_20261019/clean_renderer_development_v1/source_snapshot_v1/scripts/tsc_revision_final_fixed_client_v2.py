"""Faithful fixed-arrival adapter with unchanged query-qualified R4 admission.

Repairs the fixed client's local renderer binding, installs the already checked
incomplete-reference fail-closed catch, and optionally disables economics only
for the separately frozen Gate OFF control. No scheduler is added.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import re
import time
import urllib.request
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



def finish_after_backend_drain(args,fetch=None,clock=None,sleep=None):
    clock=clock or time.perf_counter;sleep=sleep or time.sleep
    endpoint=args.base_url.rstrip('/').removesuffix('/v1')+'/metrics'
    if fetch is None:
        def fetch():
            with urllib.request.urlopen(endpoint,timeout=5) as response:return response.read().decode()
    started=clock();idle=0;observations=[]
    while clock()-started<60:
        text=fetch();gauges={}
        for name in ['num_requests_running','num_requests_waiting']:
            values=[float(x) for x in re.findall(r'^vllm:'+name+r'(?:\{[^\n]*\})?\s+([\d.eE+-]+)$',text,re.M)]
            if not values:raise RuntimeError('Missing backend idle gauge: '+name)
            gauges[name]=sum(values)
        observations.append(gauges)
        idle=idle+1 if all(v==0 for v in gauges.values()) else 0
        if idle>=2:
            ended=clock()
            with (args.output.parent/'measured_backend_drain_v1.json').open('x',encoding='utf-8') as f:
                json.dump(dict(started_monotonic_s=started,ended_monotonic_s=ended,
                    elapsed_ms=(ended-started)*1000,consecutive_zero_observations=idle,observations=observations,
                    backend_request_counters_drained=True,included_in_measured_service_clock=True),f,indent=2)
            return ended
        sleep(.2)
    raise TimeoutError('Backend requests did not drain before the service clock ended')


def measured_main():
    tree=ast.parse(Path(fixed.__file__).read_text(encoding='utf-8'))
    old=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');new=deepcopy(old)
    def assignment(fn):
        rr=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='service_end' for x in n.targets)]
        assert len(rr)==1;return rr[0]
    n=assignment(new);n.value=ast.copy_location(ast.parse('_finish_after_backend_drain(a)',mode='eval').body,n.value)
    a=deepcopy(old);b=deepcopy(new)
    assignment(a).value=ast.Constant(value='FINAL_BACKEND_DRAIN_ONLY');assignment(b).value=ast.Constant(value='FINAL_BACKEND_DRAIN_ONLY')
    assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
    space=fixed.__dict__.copy();space['_finish_after_backend_drain']=finish_after_backend_drain
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),str(fixed.__file__)+'[explicit-final-request-drain]', 'exec'),space)
    return space['main'],dict(only_final_service_end_expression_changed=True,
        all_other_function_AST_identical=True,drain_inside_full_service_wall=True)


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--client-audit',type=Path,required=True)
    parser.add_argument('--cpu-prompt-shapes',type=Path,required=True)
    parser.add_argument('--economic-gate',choices=['ON','OFF'],default='ON')
    own,remaining=parser.parse_known_args()
    assert not own.client_audit.exists(),'Never replace a client execution audit'
    assert fixed._ordered_text is historical_renderer
    original_register=SingleShotRegistrar.register;original_decide=cost.decide
    record=dict(schema_version='contractkv.faithful-fixed-client.v2',result='not_completed',
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
            execute,drain_proof=measured_main()
            record['final_drain_AST_proof']=drain_proof
            code=execute()
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
