"""Post-output literal-reference availability, quality and routing audit.

This descriptive proxy uses reference labels only after generation. It does
not infer semantic answerability, alter grading or select/replace test inputs.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase20a_official_quality import references, standard_score
from scripts.tsc_revision_r1r_live import prepare


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def normalized(text):
    return ' '.join(text.casefold().split())


def presence(answers, text):
    normalized_text = normalized(text)
    return [bool(normalized(answer)) and normalized(answer) in normalized_text for answer in answers]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-partial', action='store_true')
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Preserve availability audit version')
    freeze_path = a.root / 'freeze.json'
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    protocol = freeze['protocol']
    if not a.allow_partial:
        audit = json.loads((a.root / 'analysis/completion_audit_v1.json').read_text())
        if not audit['execution_complete']:
            raise ValueError('Complete primary evidence required')
    renderer_sources = [
        'scripts/tsc_revision_r1r_live.py', 'scripts/tsc_revision_live.py',
        'scripts/phase13b_fresh_policy_quality_replay.py',
        'scripts/phase22_llama_layout_ladder.py',
        'scripts/phase12f_real_vllm_caposc_replay.py',
        'scripts/phase20a_official_quality.py',
    ]
    commitments = {r['path']: r['sha256'] for r in freeze['files']}
    for path in renderer_sources:
        if sha(Path(path)) != commitments[path]:
            raise ValueError('Current CPU renderer differs from this study freeze')
    generation_path = a.root / 'source_snapshot' / protocol['generation_protocol']
    generation = json.loads(generation_path.read_text(encoding='utf-8'))
    samples = {}
    source_studies = defaultdict(set)
    original_paths = []
    for study, path in protocol['input_files'].items():
        source_path = a.root / 'source_snapshot' / path
        original_paths.append({'path': source_path.as_posix(), 'sha256': sha(source_path)})
        samples[study] = {s['revision_source_group']: s for s in read(source_path)}
        for source in samples[study]:
            source_studies[source].add(study)
    source_records = {}
    for study, mapping in samples.items():
        for source, sample in mapping.items():
            if source in source_records:
                continue
            answers = references(sample.get('answer', ''))
            stored = '\n'.join(str(s.get('text', '')) for s in sample['segments']
                               if s.get('type') not in ('SYS_PROMPT', 'USER_QUERY'))
            case = build_case(sample, generation['layout']['stable_word_limit'])
            retained = '\n'.join(s['text'] for s in case['segments']
                                 if s['segment_type'] not in ('SYS_PROMPT', 'USER_QUERY', 'TOOL_OBS', 'CHAT_HISTORY', 'SCRATCHPAD'))
            in_stored = presence(answers, stored)
            in_retained = presence(answers, retained)
            source_records[source] = {
                'source_group': source, 'namespace': sample['revision_session_id'],
                'family': sample['revision_family'], 'studies': sorted(source_studies[source]),
                'reference_count': len(answers),
                'reference_answers_sha256': hashlib.sha256(json.dumps(answers, ensure_ascii=False).encode()).hexdigest(),
                'stored_context_words': len(stored.split()),
                'retained_context_words': len(retained.split()),
                'stored_context_sha256': hashlib.sha256(stored.encode()).hexdigest(),
                'retained_context_sha256': hashlib.sha256(retained.encode()).hexdigest(),
                'reference_literals_in_stored_context': in_stored,
                'reference_literals_in_retained_context': in_retained,
                'any_reference_literal_stored': any(in_stored),
                'any_reference_literal_retained': any(in_retained),
                'literal_loss_after_cap': any(in_stored) and not any(in_retained),
            }
    measured = []
    cell_provenance = []
    rendered_cache = {}
    for path in sorted((a.root / 'cells').glob('*/summary.json')):
        summary = json.loads(path.read_text(encoding='utf-8'))
        raw_path = path.with_name('raw.jsonl')
        if not summary['execution_complete'] or sha(raw_path) != summary['raw_file_sha256']:
            raise ValueError('Changed/incomplete measured cell')
        rows = read(raw_path)
        final = {(r['certificate_namespace'], r['query_scope']): r for r in rows if r['row_type'] == 'verification'}
        plans = {(r['certificate_namespace'], r['query_scope']): r for r in rows if r['row_type'] == 'prospective_plan'}
        business = [r for r in rows if r['row_type'] in ('warm', 'future')]
        for row in business:
            source = row['source_group']
            static = source_records[source]
            sample = deepcopy(samples[summary['study']][source])
            score, metric, _ = standard_score(sample['dataset'], sample['task'], row['output_text'], sample.get('answer', ''))
            if abs(score - row['task_score']) > 1e-12:
                raise ValueError('Frozen task score mismatch')
            render_key = summary['study'], row['session_id'], row['turn_id']
            if render_key not in rendered_cache:
                sample['revision_session_id'] = row['session_id']
                if summary['tenants_per_template'] > 1:
                    sample['shared_template_id'] = row['certificate_namespace']
                args = SimpleNamespace(protocol=generation, experiment='free-generation',
                                       output_budget=0, model_identity=row['model'],
                                       policy_hash=sha(freeze_path))
                _, messages, _, _, _ = prepare(args, sample, row['turn_id'])
                rendered_cache[render_key] = any(presence(references(sample.get('answer', '')), messages[1]['content']))
            scope = row['certificate_namespace'], row['query_scope']
            decision = final.get(scope)
            plan = plans.get(scope)
            measured.append({
                'cell': path.parent.name, 'study': summary['study'], 'model': row['model'],
                'policy': summary['policy'], 'repeat': summary['repeat'],
                'source_group': source, 'family': row['family'], 'session_id': row['session_id'],
                'turn_id': row['turn_id'], 'row_type': row['row_type'],
                'query_scope': row['query_scope'], 'effective_level': row['effective_level'],
                'task_metric': metric, 'task_score': score,
                'metric_full_score': score >= 1 - 1e-12, 'metric_positive_score': score > 0,
                'actual_prompt_IDs_sha256': row['prompt_ids_sha256'],
                'reconstructed_raw_user_prompt_any_reference_literal': rendered_cache[render_key],
                'retained_context_any_reference_literal': static['any_reference_literal_retained'],
                'literal_loss_after_cap': static['literal_loss_after_cap'],
                'scope_final_issued': bool(decision and decision['certificate_issued']),
                'scope_final_reason': decision['failure_reason'] if decision else (plan['reason'] if plan else 'raw-order_no_qualification'),
                'finish_reason': row['finish_reason'],
                'output_tokens': len(row['output_token_ids']),
                'actual_prefix_hit_tokens': row['prefix_hit_tokens'],
            })
        cell_provenance.append({'cell': path.parent.name, 'summary_sha256': sha(path), 'raw_sha256': sha(raw_path)})
    groups = defaultdict(list)
    for row in measured:
        groups[row['study'], row['model'], row['policy'], row['family'], row['retained_context_any_reference_literal']].append(row)
    summaries = []
    for key, group in sorted(groups.items()):
        summaries.append(dict(zip(('study', 'model', 'policy', 'family', 'literal_retained'), key),
                              business_requests=len(group), sources=len({r['source_group'] for r in group}),
                              mean_frozen_task_score=statistics.fmean(r['task_score'] for r in group),
                              full_metric_score_count=sum(r['metric_full_score'] for r in group),
                              positive_metric_score_count=sum(r['metric_positive_score'] for r in group),
                              compiled_requests=sum(r['effective_level'] != 'L0' for r in group),
                              final_scope_reasons=dict(Counter(r['scope_final_reason'] for r in group))))
    result = {
        'schema_version': 'tsc-r4.literal-evidence-availability.v1', 'partial': a.allow_partial,
        'all_frozen_source_inputs_audited': len(source_records), 'complete_measured_cells_read': len(cell_provenance),
        'source_sha256': sha(Path(__file__)), 'freeze_sha256': sha(freeze_path),
        'renderer_sources': [{'path': path, 'sha256': commitments[path]} for path in renderer_sources],
        'input_provenance': original_paths, 'cell_provenance': cell_provenance,
        'source_input_records': list(source_records.values()),
        'quality_routing_summaries': summaries, 'measured_business_records': measured,
        'new_GPU_requests': 0, 'input_policy_or_scorer_changed': False,
        'interpretation_limits': [
            'Literal presence uses Unicode casefold and whitespace normalization only. It is a descriptive proxy, not semantic evidence availability or an answerability test.',
            'An absent reference string may still be inferable, especially for abstractive QA; an incidental present string need not provide sufficient evidence.',
            'Full metric score and positive metric score refer only to the frozen metric, not an independent semantic correctness judgment.',
            'The raw user prompt is reconstructed with frozen renderer source bytes, not newly tokenized. Actual prompt ID hashes remain linked to measured logs and primary identity audits.',
            'Raw-order rows assess raw task quality. Risk-tail rows can be compiled or L0; their task scores are policy outputs and must not all be labelled raw.',
            'Reference labels are used only after the frozen generations, never for admission, input replacement, threshold selection or exclusion.',
            'Truncation, task quality and rejection associations do not identify causality. Rejected candidates and alternative evidence-preserving inputs were not run.',
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'frozen_sources': len(source_records), 'cells': len(cell_provenance),
                      'measured_business_rows': len(measured),
                      'sources_with_literal_loss_after_cap': sum(r['literal_loss_after_cap'] for r in source_records.values()),
                      'new_GPU_requests': 0, 'partial': a.allow_partial}))


if __name__ == '__main__':
    main()
