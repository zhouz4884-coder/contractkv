"""Trace shared historical input adaptation and reconstruct word-stage losses.

Historical launchers/committed inputs are evidence of declared pipelines, not
retroactively recorded prompt IDs. Identity-only historical digests are labelled.
"""
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase20a_official_quality import references
from scripts.phase20d_build_fresh_split import digest_rows


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return ' '.join(text.casefold().split())


def read(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def main():
    output = Path('results/tsc_revision_r4/historical_input_audit_v1.json')
    if output.exists():
        raise ValueError('Preserve historical audit version')
    cohorts = [
        ('original_global_qwen8', 'results/end_to_end/phase19b_untouched_sessions_v0.jsonl', 2600, 'scripts/run_submission_repeats.sh'),
        ('original_global_mistral', 'results/mistral/heldout_sealed_sessions_v0.jsonl', 1500, 'scripts/run_submission_repeats.sh'),
        ('original_global_llama', 'results/tsc_revision_r4/historical_input_snapshots_v1/original_llama_sealed.jsonl', 1500, 'scripts/run_phase22r_llama_broad.sh'),
        ('original_global_qwen14', 'results/tsc_revision_r4/historical_input_snapshots_v1/original_qwen14_sealed.jsonl', 2600, 'scripts/run_phase23_qwen14_scaleup.sh'),
        ('original_task_service_templates', 'results/tsc_revision_r4/historical_input_snapshots_v1/original_service_quality.jsonl', 1500, 'scripts/run_tsc_service_template_quality.sh'),
        ('revision_R1_common_Hotpot', 'configs/tsc_revision_hotpot_heldout_sessions_v1.jsonl', 1500, 'configs/tsc_major_revision_r1_protocol.json'),
        ('revision_R1_free_generation', 'configs/tsc_revision_free_generation_sessions_v1.jsonl', 1500, 'configs/tsc_major_revision_r1_protocol.json'),
        ('revision_R1R', 'results/tsc_revision_r1r/validation/source_snapshot/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl', 1500, 'results/tsc_revision_r1r/validation/freeze_v1.json'),
        ('revision_R2', 'results/tsc_revision_r2/validation_v1/source_snapshot/results/tsc_revision_r2/inputs/heldout_sealed_sessions_v1.jsonl', 1500, 'results/tsc_revision_r2/validation_v1/freeze.json'),
        ('revision_R3', 'results/tsc_revision_r3/validation_v1/source_snapshot/results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl', 1500, 'results/tsc_revision_r3/validation_v1/freeze.json'),
        ('revision_R4', 'results/tsc_revision_r4/validation_closed_v1/source_snapshot/results/tsc_revision_r4/inputs/heldout_sealed_sessions_v1.jsonl', 1500, 'results/tsc_revision_r4/validation_closed_v1/freeze.json'),
    ]
    renderer = Path('scripts/phase13b_fresh_policy_quality_replay.py')
    historical_blob = subprocess.check_output(['git', 'show', '1e7f633:' + renderer.as_posix()])
    if hashlib.sha256(historical_blob).hexdigest() != sha(renderer):
        raise ValueError('Historical July renderer is not byte-identical')
    identities = []
    for name, path, commitment, field, kind in [
        ('original_llama', cohorts[2][1], 'results/cross_model/llama_broad_generalization_r3/split_commitment_v0.json', 'heldout_sha256', 'sample_and_group_identity_only'),
        ('original_qwen14', cohorts[3][1], 'results/scale_up/qwen3_14b_tp2_v0/split_commitment_v0.json', 'sessions_sha256', 'sample_and_group_identity_only'),
        ('original_task_service', cohorts[4][1], 'results/tsc_service/tsc_service_quality_trace_commitment_v0.json', 'sessions_sha256', 'canonical_full_rows'),
    ]:
        values = read(Path(path))
        measured = digest_rows(values) if kind == 'sample_and_group_identity_only' else hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        expected = json.loads(Path(commitment).read_text(encoding='utf-8'))[field]
        if measured != expected:
            raise ValueError('Recovered original input identity mismatch: ' + name)
        identities.append({'cohort': name, 'input_path': path, 'input_file_sha256_now': sha(Path(path)),
                           'commitment_path': commitment, 'commitment_sha256': sha(Path(commitment)),
                           'identity_hash_kind': kind, 'measured_identity_hash': measured, 'matches': True})
    records = []
    for name, filename, cap, declaration in cohorts:
        path = Path(filename)
        raw_rows = read(path)
        unique = {}
        for row in raw_rows:
            identity = json.dumps([row.get('dataset'), row.get('task'), row.get('sample_id'), row['segments']], ensure_ascii=False, sort_keys=True)
            unique.setdefault(identity, row)
        source_records = []
        for sample in unique.values():
            dataset, task = sample.get('dataset', ''), sample.get('task', '')
            family = ('RULER' if dataset == 'RULER' else 'RepoBench' if dataset == 'RepoBench' else
                      {'hotpotqa': 'HotpotQA', 'narrativeqa': 'NarrativeQA', 'qasper': 'Qasper'}.get(task, task))
            case = build_case(sample, cap)
            original = [r for r in sample['segments'] if r['type'] not in ('SYS_PROMPT', 'USER_QUERY')]
            retained = [r for r in case['segments'] if r['segment_type'] not in ('SYS_PROMPT', 'USER_QUERY', 'TOOL_OBS')]
            if len(original) != len(retained):
                raise ValueError('Unexpected historical segment alignment')
            full = norm('\n'.join(r['text'] for r in original))
            kept = norm('\n'.join(r['text'] for r in retained))
            refs = [norm(r) for r in references(sample.get('answer', '')) if norm(r)]
            original_literal = any(r in full for r in refs)
            retained_literal = any(r in kept for r in refs)
            code = []
            for before, after in zip(original, retained):
                if before['type'] != after['segment_type']:
                    raise ValueError('Segment type mismatch')
                if before['type'] == 'CODE_PREFIX':
                    n, k = len(before['text'].split()), len(after['text'].split())
                    code.append({'original_words': n, 'retained_words': k,
                                 'status': 'empty' if n and not k else 'partial' if k < n else 'all_words',
                                 'original_newlines': before['text'].count('\n'), 'retained_newlines': after['text'].count('\n')})
            query = next((r['text'] for r in sample['segments'] if r['type'] == 'USER_QUERY'), '')
            case_query = next(r['text'] for r in case['segments'] if r['segment_type'] == 'USER_QUERY')
            source_records.append({'family': family, 'sample_id': sample.get('sample_id'),
                                   'source_group': sample.get('revision_source_group', sample.get('metadata', {}).get('source_group_id')),
                                   'any_literal_in_stored_context': original_literal,
                                   'any_literal_in_retained_context': retained_literal,
                                   'literal_loss_after_word_cap': original_literal and not retained_literal,
                                   'original_query_preserved_by_build_case': query == case_query,
                                   'CODE_PREFIX': code})
        family_records = []
        for family in sorted({r['family'] for r in source_records}):
            group = [r for r in source_records if r['family'] == family]
            code = [c for r in group for c in r['CODE_PREFIX']]
            family_records.append({'family': family, 'unique_source_inputs': len(group),
                                   'literal_stored': sum(r['any_literal_in_stored_context'] for r in group),
                                   'literal_retained': sum(r['any_literal_in_retained_context'] for r in group),
                                   'literal_lost_after_cap': sum(r['literal_loss_after_word_cap'] for r in group),
                                   'original_query_preserved': sum(r['original_query_preserved_by_build_case'] for r in group),
                                   'CODE_PREFIX_retention': dict(Counter(r['status'] for r in code)),
                                   'CODE_PREFIX_newline_loss': sum(r['original_newlines'] > 0 and r['retained_newlines'] == 0 for r in code)})
        records.append({'cohort': name, 'input_path': path.as_posix(), 'input_sha256_now': sha(path),
                        'word_cap': cap, 'input_rows_including_tenant_copies': len(raw_rows),
                        'distinct_coherent_source_inputs': len(unique),
                        'declared_launch_or_freeze': declaration, 'declaration_sha256': sha(Path(declaration)),
                        'family_records': family_records, 'source_records': source_records})
    result = {
        'schema_version': 'tsc-r4.historical-input-lineage.v1', 'new_GPU_requests': 0,
        'source_sha256': sha(Path(__file__)), 'renderer_sha256': sha(renderer),
        'renderer_byte_identical_to_git_commit': '1e7f633',
        'recovered_original_identity_checks': identities, 'cohorts': records,
        'Table_I_exact_numeric_lineage': 'Not yet located; current manuscript literals alone are not independent evidence for 82.4/2.1 or 85.0/2.4.',
        'marker_service_separation': 'tsc_open_loop_service.make_case deliberately replaces the original query and target with PRIVATE_TOOL_OBS marker retrieval. Its real service/cache measurements are controlled marker-task evidence, not official QA/code-completion utility.',
        'limits': [
            'These are CPU reconstructions of the word-cap stage using committed/recovered source inputs and the shared historical function. They are not retroactively logged actual prompts or new model measurements.',
            'Some older split commitments bind sample/group identity only. Their match does not itself authenticate all historical text bytes; current recovered byte hashes and that weaker boundary are retained.',
            'Token-window fitting in pipelines that additionally call _retokenize_case may remove more input. The counts here do not undo or fully quantify that subsequent stage.',
            'Literal presence is not semantic answerability. Code-prefix retention is distinct from next-line reference presence; full words still lose newline/indentation formatting.',
            'Declared historical launch settings and byte-identical repository source do not establish the source identity of every old executing process when per-cell source manifests are absent.',
            'Application-quality and representativeness claims need reassessment where inputs lose evidence/cursor structure. This does not automatically invalidate measured cache work, service wall or transaction-state invariants.',
        ],
    }
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cohorts': len(records), 'shared_renderer_sha256': sha(renderer), 'old_identity_checks_pass': len(identities), 'new_GPU_requests': 0}))


if __name__ == '__main__':
    main()
