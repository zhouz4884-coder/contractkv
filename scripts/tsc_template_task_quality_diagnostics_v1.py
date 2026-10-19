"""Post-hoc CPU diagnosis of frozen outcomes; no scoring or admission changes."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics

STUDY = Path('results/tsc_template_task_serving_20261019')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_hash(ids):
    return hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()


def first_difference(left, right):
    for position, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return position
    return min(len(left), len(right)) if len(left) != len(right) else None


def main(workspace, evidence, output):
    proof = read(workspace / STUDY / 'formal_local_independent_recompute_v1.json')
    restore = read(workspace / STUDY / 'formal_local_archive_verification_v1.json')
    assert proof['status'] == restore['status'] == 'PASS'
    assert Path(restore['restore_root']).resolve() == evidence
    assert not output.exists()
    study = evidence / STUDY
    protocol = read(study / 'formal_protocol_v1.json')
    primary = read(study / 'formal_analysis_v1/summary_v1.json')
    samples = {r['revision_source_group']: r for r in lines(study / 'inputs_validation_v2/sessions_v2.jsonl')}
    indexed, references = {}, defaultdict(list)
    group_salts, terminations, physical = defaultdict(set), defaultdict(Counter), defaultdict(Counter)
    scope_errors = 0
    for job in protocol['jobs']:
        cell = study / 'runs' / job['id'] / 'attempt1'
        native = {r['request_id']: r for r in lines(cell / 'metrics.jsonl')
                  if r.get('event') == 'prefix_cache_request_observation' and r.get('initial_prefill_observation')}
        registered = {}
        for row in lines(cell / 'responses.jsonl'):
            if row['row_type'] == 'registration':
                registered[row['object_id']] = row['certificate']
            elif row['row_type'] == 'reference_generation':
                value = row['result']
                references[job['model'], job['load'], job['repeat'], job['policy'], row['source_group']].append(
                    (tuple(value['output_token_ids']), value['finish_reason']))
        for row in lines(cell / 'responses.jsonl'):
            if row['row_type'] != 'business':
                continue
            value = row['result']
            key = job['model'], job['load'], job['repeat'], job['policy'], row['source_group'], row['tenant'], row['turn']
            assert key not in indexed
            scope_errors += len(row['scope_binding_errors'])
            group_salts[job['model'], row['source_group']].add(value['actual_wire_cache_salt'])
            family_key = job['model'], job['policy'], row['family']
            terminations[family_key]['requests'] += 1
            terminations[family_key][str(value['finish_reason'])] += 1
            limit = 128 if row['family'] == 'HotpotQA' else 384
            terminations[family_key]['at_budget_tokens'] += len(value['output_token_ids']) >= limit
            event = native[value['request_id']]
            if row['compiled']:
                commit = registered[row['certificate_object']]['committed_tokens']
                hit = event['prefix_hit_tokens']
                physical[job['model'], job['policy']]['full' if hit >= commit else 'partial' if hit else 'zero'] += 1
            indexed[key] = dict(IDs=value['output_token_ids'], text=value['output_text'], finish=value['finish_reason'],
                actual_prompt_ids_hash=ids_hash(value['prompt_token_ids']), prompt_tokens=len(value['prompt_token_ids']),
                score=row['task_score'], compiled=row['compiled'], family=row['family'],
                native_hit=event['prefix_hit_tokens'], file=(cell / 'responses.jsonl').relative_to(evidence).as_posix(),
                request_id=value['request_id'], source=row['source_group'])
    assert len(indexed) == 10368
    with (study / 'formal_analysis_v1/paired_quality_v1.csv').open(encoding='utf-8', newline='') as stream:
        pairs = list(csv.DictReader(stream))
    down, up, fallback_changes = [], [], []
    raw_variants = defaultdict(set)
    raw_input_variants = defaultdict(set)
    for key, value in indexed.items():
        model, load, repeat, policy, source, tenant, turn = key
        if policy == 'Raw-authorized':
            coordinate = model, source, tenant, turn
            raw_variants[coordinate].add((tuple(value['IDs']), value['finish']))
            raw_input_variants[coordinate].add(value['actual_prompt_ids_hash'])
    for row in pairs:
        model, load, repeat, policy, source = (row[k] for k in ['model', 'load', 'repeat', 'policy', 'source'])
        repeat, tenant, turn = int(repeat), int(row['tenant']), int(row['turn'])
        raw_key = model, load, repeat, 'Raw-authorized', source, tenant, turn
        selected_key = model, load, repeat, policy, source, tenant, turn
        raw, selected = indexed[raw_key], indexed[selected_key]
        assert raw['score'] == float(row['Raw_score']) and selected['score'] == float(row['score'])
        if not selected['compiled']:
            assert raw['actual_prompt_ids_hash'] == selected['actual_prompt_ids_hash']
        changed = (raw['IDs'], raw['finish']) != (selected['IDs'], selected['finish'])
        assert changed == (row['IDs_and_finish_equal'] == 'False')
        example = dict(model=model, load=load, repeat=repeat, policy=policy, source=source, tenant=tenant, turn=turn,
            compiled=selected['compiled'], Raw_score=raw['score'], score=selected['score'], delta=selected['score']-raw['score'],
            reference_answer=samples[source].get('answer', ''),
            first_output_ID_difference=first_difference(raw['IDs'], selected['IDs']),
            Raw_finish=raw['finish'], policy_finish=selected['finish'], Raw_tokens=len(raw['IDs']), policy_tokens=len(selected['IDs']),
            Raw_text=raw['text'], policy_text=selected['text'], Raw_native_hit=raw['native_hit'], policy_native_hit=selected['native_hit'],
            Raw_file=raw['file'], policy_file=selected['file'], Raw_request_id=raw['request_id'], policy_request_id=selected['request_id'],
            candidate_matches_registered_compiled_witness=(tuple(selected['IDs']), selected['finish']) in references[model, load, repeat, policy, source],
            Raw_prompt_hash=raw['actual_prompt_ids_hash'], policy_prompt_hash=selected['actual_prompt_ids_hash'])
        if row['score_down'] == 'True':
            down.append(example)
        if row['score_up'] == 'True':
            up.append(example)
        if changed and not selected['compiled']:
            coordinate = model, source, tenant, turn
            example['Raw_repeats_have_same_actual_input'] = len(raw_input_variants[coordinate]) == 1
            example['Raw_repeats_have_output_variation'] = len(raw_variants[coordinate]) > 1
            other = [v for k, v in indexed.items() if k[0] == model and k[3] == 'Raw-authorized'
                     and (k[4], k[5], k[6]) == (source, tenant, turn) and (k[1], k[2]) != (load, repeat)]
            example['policy_output_matches_another_Raw_execution'] = any((v['IDs'], v['finish']) == (selected['IDs'], selected['finish']) for v in other)
            fallback_changes.append(example)
    compiled_down = [r for r in down if r['compiled']]
    assert len(compiled_down) == primary['compiled_score_down'] and len(down) == primary['all_route_score_down']
    assert len(up) == primary['all_route_score_up']
    source_quality = []
    for key in sorted({(r['model'], r['source'], r['policy']) for r in pairs}):
        rr = [r for r in pairs if (r['model'], r['source'], r['policy']) == key]
        source_quality.append(dict(model=key[0], source=key[1], policy=key[2], requests=len(rr),
            compiled=sum(r['compiled'] == 'True' for r in rr), ID_finish_changes=sum(r['IDs_and_finish_equal'] == 'False' for r in rr),
            score_down=sum(r['score_down'] == 'True' for r in rr), score_up=sum(r['score_up'] == 'True' for r in rr),
            Raw_mean=statistics.fmean(float(r['Raw_score']) for r in rr), policy_mean=statistics.fmean(float(r['score']) for r in rr)))
    result = dict(status='POSTHOC_CPU_DIAGNOSIS_FROM_INDEPENDENTLY_VERIFIED_ARCHIVE', new_GPU_requests=0,
        changes_to_admission_scoring_SLO_sources_or_inclusion=False, archive_sha256=proof['archive_sha256'],
        analysis_source_sha256=proof['analysis_source_sha256'], source_sha256=sha(Path(__file__)),
        actual_business=10368, paired_business=len(pairs), compiled_score_down=len(compiled_down), all_route_score_down=len(down),
        all_route_score_up=len(up), compiled_down_source_clusters=sorted({r['source'] for r in compiled_down}),
        compiled_down_unique_coordinates=[dict(model=k[0], source=k[1], tenant=k[2], turn=k[3])
            for k in sorted({(r['model'], r['source'], r['tenant'], r['turn']) for r in compiled_down})],
        scope_binding_error_count=scope_errors,
        actual_business_group_counts=[dict(model=k[0], source=k[1], distinct_wire_salts=len(v)) for k,v in sorted(group_salts.items())],
        actual_group_identity_equal_across_policies_repeats_loads=all(len(v) == 1 for v in group_salts.values()),
        compiled_native_hit_classes=[dict(model=k[0], policy=k[1], **v) for k,v in sorted(physical.items())],
        terminations=[dict(model=k[0], policy=k[1], family=k[2], **v) for k,v in sorted(terminations.items())],
        source_quality=source_quality, compiled_down_events=compiled_down, all_down_events=down,
        fallback_output_changes=fallback_changes,
        raw_repeat_variation=[dict(model=k[0], source=k[1], tenant=k[2], turn=k[3], input_hashes=len(raw_input_variants[k]), output_variants=len(v))
            for k,v in sorted(raw_variants.items()) if len(v) > 1],
        boundary='Post-hoc description and diagnosis only. Repeated tenant/turn events are not independent sources. Another Raw execution matching a policy output does not prove absence of a policy effect.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], compiled_down=len(compiled_down), all_down=len(down),
        down_clusters=result['compiled_down_source_clusters'], unique_down_coordinates=len(result['compiled_down_unique_coordinates']),
        identical_business_group_identity=result['actual_group_identity_equal_across_policies_repeats_loads'],
        output=str(output), new_GPU_requests=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['workspace', 'evidence-root', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    main(args.workspace.resolve(), args.evidence_root.resolve(), args.output.resolve())
