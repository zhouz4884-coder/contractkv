"""Read all prior real-Repo outputs and test task-context syntax, CPU only."""
import ast
import codeop
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r3_output_contract import python_statement_contract

STUDY = Path('results/tsc_authorization_task_repair_20261019')
OLD = Path('results/tsc_real_repobench_mechanism_20261018')


def probe(source):
    try:
        result = codeop.compile_command(source, symbol='exec')
        return dict(state='incomplete_but_extendable' if result is None else 'complete')
    except (SyntaxError, ValueError, OverflowError) as error:
        return dict(state='invalid_or_missing_context', error_type=type(error).__name__,
                    message=str(error), line=getattr(error, 'lineno', None))


def main(root):
    out = root / STUDY / 'repo_contract_CPU_audit_v1.json'
    assert not out.exists()
    archive = root / OLD / 'real_repo_raw_evidence_v1.tar.gz.part01'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'ad1916813dfdebb510d641dcb77edce4e6fbafda5daff3b8716c0df7e466cfdf'
    plan = json.loads((root / OLD / 'protocol_v1.json').read_text(encoding='utf-8'))
    cases = {c['case_id']: c for c in plan['behavior_cases']}
    rows = []
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            if not member.name.endswith('/responses.jsonl'):
                continue
            raw_bytes = tar.extractfile(member).read()
            for line in raw_bytes.decode('utf-8').splitlines():
                row = json.loads(line)
                if row['event'] != 'business' or row['condition'] != 'raw_witness':
                    continue
                case = cases[row['case_id']]
                prefix = ''.join(s['text'] for s in case['segments'] if s['segment_type'] == 'CODE_PREFIX')
                assert hashlib.sha256(prefix.encode()).hexdigest() == case['CODE_PREFIX_sha256']
                first, sep, rest = prefix.partition('\n')
                path_metadata = bool(sep and re.fullmatch(r'[A-Za-z0-9_./\\-]+\.py', first.strip()))
                syntax_prefix = rest if path_metadata else prefix
                response = row['response']
                text = response['output_text']
                guard = python_statement_contract(text)
                context = probe(syntax_prefix + text)
                rows.append(dict(model=row['model'], case_id=row['case_id'], source_group=case['source_group'],
                    condition=case['diagnostic_layout_level'], finish=response['finish_reason'],
                    raw_output_text=text, actual_raw_prompt_token_ids=response['prompt_token_ids'],
                    raw_output_token_ids=response['output_token_ids'], CODE_PREFIX=prefix,
                    first_prefix_line_is_path_metadata=path_metadata, old_statement_guard=guard,
                    prefix_parse=probe(syntax_prefix), prefix_plus_verbatim_output_parse=context,
                    possible_false_rejection=(not guard['passed'] and context['state'] in {'complete', 'incomplete_but_extendable'}),
                    gold_label_used_online=False,
                    label_context_diagnostic_only=probe(syntax_prefix + case['answer']),
                    archive_member=member.name, member_sha256=hashlib.sha256(raw_bytes).hexdigest()))
    assert len(rows) == 18
    out.parent.mkdir(parents=True, exist_ok=True)
    value = dict(schema_version='contractkv.repo-task-contract-audit.v1', new_GPU_requests=0,
                 prior_Raw_witnesses=18, old_guard_rejections=sum(not r['old_statement_guard']['passed'] for r in rows),
                 possible_context_supported_false_rejections=sum(r['possible_false_rejection'] for r in rows),
                 all_prior_sources_and_models_included=True, unchanged_old_guard=True,
                 boundary='Context parsing is syntax evidence only, not semantic correctness; invalid prefixes may lack context. No admission rule is changed by this audit. Gold labels are used only in the separate offline diagnostic.',
                 rows=rows, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with out.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k != 'rows'}))
    for r in rows:
        print(json.dumps({k:r[k] for k in ('model', 'case_id', 'finish', 'raw_output_text', 'old_statement_guard', 'prefix_parse', 'prefix_plus_verbatim_output_parse', 'possible_false_rejection')}, ensure_ascii=False))


if __name__ == '__main__':
    main(Path.cwd())
