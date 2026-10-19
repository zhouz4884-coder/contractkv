"""Source/task/failure-stage accounting from the complete archived controllers."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def lines(p):
    with p.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root, output):
    assert not output.exists()
    study = root / '.artifacts/tableIII_fullcost_restore_v1/results/tsc_tableIII_fullcost_replay_20261018'
    protocol, state = read(study / 'protocol_v1.json'), read(study / 'execution_state_v1.json')
    controllers, stages, inventory = [], [], []
    for model in protocol['models']:
        samples = {s['phase19b_session_id']: s for s in lines(study / 'inputs' / model['session_file'])}
        for repeat in [1, 2, 3]:
            relative = next(x for x in state['completed_pairs'] if x.startswith('cells/' + model['key'] + '_r' + str(repeat) + '/'))
            cell = study / relative / 'contract'
            path = cell / 'audit/complete_controller_events_v1.jsonl'
            events = lines(path)
            canaries = {r['session_id']: r for r in lines(cell / 'requests.jsonl') if r.get('row_type') == 'canary'}
            inventory.append(dict(path=path.relative_to(root).as_posix(), sha256=sha(path)))
            pending = []
            for event in events:
                if event['event'] in {'generate_raw', 'compact_verify'}:
                    pending.append(event)
                elif event['event'] == 'complete_controller':
                    sid = event['session_id']
                    sample, canary = samples[sid], canaries[sid]
                    common = dict(model=model['model'], repeat=repeat, session_id=sid,
                        dataset=sample['dataset'], task=sample['task'], sample_id=str(sample['sample_id']))
                    for i, call in enumerate(pending):
                        stage = ('Raw_reference_exception' if call['outcome'] == 'exception' else 'Raw_reference_returned') if call['event'] == 'generate_raw' else (
                            'verifier_PASS' if call['certificate_issued'] else 'verifier_non_PASS')
                        stages.append(dict(common, serial_call_index=i, stage=stage, elapsed_ms=call['elapsed_ms'],
                                           actual_event=call))
                    residual = event['controller_ms'] - sum(r['elapsed_ms'] for r in pending)
                    assert residual >= -.01
                    no_rpc = not pending
                    if no_rpc:
                        assert event['decision'] == 'NOT_REQUIRED'
                    controllers.append(dict(common, full_controller_ms=event['controller_ms'],
                        Raw_reference_ms=sum(r['elapsed_ms'] for r in pending if r['event'] == 'generate_raw'),
                        passed_verifier_ms=sum(r['elapsed_ms'] for r in pending if r['event'] == 'compact_verify' and r['certificate_issued']),
                        failed_verifier_ms=sum(r['elapsed_ms'] for r in pending if r['event'] == 'compact_verify' and not r['certificate_issued']),
                        call_count=len(pending), RPC_calls=sum(r['event'] == 'compact_verify' for r in pending),
                        no_RPC_L0_warmup=no_rpc, residual_ms=residual,
                        actual_multilevel_descent=len(event.get('level_attempts', [])) > 1,
                        failure=canary.get('failure_reason', canary.get('error_message', '')),
                        accepted=bool(event['certificate_issued'])))
                    pending = []
            assert not pending
    totals = dict(controllers=len(controllers), actual_verifier_HTTP=sum(r['stage'].startswith('verifier_') for r in stages),
        non_PASS_HTTP=sum(r['stage'] == 'verifier_non_PASS' for r in stages),
        Raw_reference_exceptions=sum(r['stage'] == 'Raw_reference_exception' for r in stages),
        no_RPC_L0_warmups=sum(r['no_RPC_L0_warmup'] for r in controllers),
        full_controller_ms=sum(r['full_controller_ms'] for r in controllers),
        no_RPC_L0_warmup_ms=sum(r['full_controller_ms'] for r in controllers if r['no_RPC_L0_warmup']),
        other_residual_ms=sum(r['residual_ms'] for r in controllers if not r['no_RPC_L0_warmup']),
        stages={s: dict(calls=sum(r['stage'] == s for r in stages), elapsed_ms=sum(r['elapsed_ms'] for r in stages if r['stage'] == s)) for s in sorted({r['stage'] for r in stages})})
    assert (totals['controllers'], totals['actual_verifier_HTTP'], totals['non_PASS_HTTP'], totals['Raw_reference_exceptions'], totals['no_RPC_L0_warmups']) == (525, 453, 155, 30, 60)
    groups = []
    for model, task, stage in sorted({(r['model'], r['task'], r['stage']) for r in stages}):
        rr = [r for r in stages if (r['model'], r['task'], r['stage']) == (model, task, stage)]
        groups.append(dict(model=model, task=task, stage=stage, calls=len(rr), elapsed_ms=sum(r['elapsed_ms'] for r in rr)))
    result = dict(schema_version='contractkv.existing-tableIII-source-stage-audit.v1', new_GPU_requests=0,
        totals=totals, by_model_task_stage=groups, controllers=controllers, serial_stages=stages, inputs=inventory,
        source_sha256=sha(Path(__file__)),
        method='Use the archived analyzer serial-canary grouping: completed_controller closes preceding generate_raw/compact_verify calls. No asynchronous V5 registration grouping is inferred by this rule.',
        conclusion='Most old cost is actual Raw-reference generation and passed/failed verification; 60 no-RPC L0 warmups are not unexplained CPU overhead. V5 already reuses business Raw witnesses, so reference removal is not a new gain. Component sums across independent cells are not a single service critical path; new V5 traces supply actual intervals.')
    with output.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(totals))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    main(a.root.resolve(), a.output.resolve())
