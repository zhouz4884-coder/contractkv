"""Trace visible file reads before the original Table-I insertion.

Only tool requests/results and public manuscript text are inspected/exported.
Thinking blocks and full conversations are never exported.
"""
from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json
import re

CUT = '2026-07-19T10:58:14.283Z'
ROOT = Path(__file__).resolve().parents[1]


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(text_content(v) for v in value)
    if isinstance(value, dict) and value.get('type') == 'text':
        return value.get('text', '')
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=ROOT/'results/tsc_tableI_remeasurement_20261018/upstream_v2')
    args = parser.parse_args()
    base = Path.home()/'.qoderworkcn/projects/C--Users-LENOVO--qoderworkcn-workspace-mri0jcwxlbhztija'
    calls = {}
    results = {}
    visible_numeric_mentions = []
    logs = []
    main_name = '6d0a87bc-7882-47e5-9d08-242d26a8a181.jsonl'
    for path in sorted(base.rglob('*.jsonl')):
        logs.append({'file': path.relative_to(base).as_posix(),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for number, line in enumerate(path.open(encoding='utf-8'), 1):
            row = json.loads(line)
            stamp = row.get('timestamp', '')
            if not isinstance(stamp, str) or not stamp.startswith('2026-') or stamp >= CUT:
                continue
            message = row.get('message', {})
            blocks = message.get('content', []) if isinstance(message, dict) else []
            for block in blocks if isinstance(blocks, list) else []:
                if not isinstance(block, dict):
                    continue
                kind = block.get('type')
                meta = {'log': path.relative_to(base).as_posix(), 'line': number,
                        'timestamp_UTC': stamp, 'main_writer': path.name == main_name}
                if kind == 'tool_use':
                    data = block.get('input', {})
                    tool = block.get('name', '')
                    if tool == 'Read':
                        file = str(data.get('file_path', ''))
                        if 'contract kv' in file.lower():
                            calls[block['id']] = {**meta, 'tool_id': block['id'],
                                'tool': tool, 'path': file, 'offset': data.get('offset'),
                                'limit': data.get('limit')}
                    elif tool == 'Bash':
                        command = data.get('command', '')
                        # Path mentions are discovery evidence, not proof of a read.
                        mentions = sorted(set(re.findall(
                            r'(?:results|docs|submission|configs)[/\\][\w./\\-]+\.(?:csv|jsonl?|ya?ml|md|py)', command)))
                        if mentions:
                            calls[block['id']] = {**meta, 'tool_id': block['id'],
                                'tool': tool, 'path_mentions_only': mentions}
                elif kind == 'tool_result':
                    content = text_content(block.get('content', ''))
                    results[block.get('tool_use_id')] = {**meta,
                        'text': content, 'is_error': block.get('is_error', False)}
                elif kind == 'text':
                    # Public user/assistant text; no reasoning/thinking blocks.
                    content = block.get('text', '')
                    if re.search(r'(?<![\d.])(?:91\.2|82\.4|78\.6|84\.1|88\.7|85\.0)(?!\d)', content):
                        visible_numeric_mentions.append({**meta, 'role': message.get('role'),
                            'text_sha256': hashlib.sha256(content.encode()).hexdigest(),
                            'has_all_five_values': all(s in content for s in ['91.2','82.4','78.6','84.1','88.7']),
                            'metric_context': bool(re.search(r'stable|recovery|prefix|稳定|前缀', content, re.I))})
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    evidence = []
    for key, call in sorted(calls.items(), key=lambda item: item[1]['timestamp_UTC']):
        result = results.get(key)
        content = result['text'] if result else ''
        terms = ['stable_ratio', 'native_recovery', 'stable_tokens', 'stable_token',
                 'raw_prefix', 'prefix_hit', 'CHAT_HISTORY', 'rho_s', 'rho_p']
        row = {**call, 'result_found': result is not None,
               'result_is_error': result['is_error'] if result else None,
               'result_text_sha256': hashlib.sha256(content.encode()).hexdigest(),
               'result_characters': len(content),
               'result_log_line': result['line'] if result else None,
               'metric_terms': {term: content.lower().count(term.lower()) for term in terms},
               'contains_five_target_values': all(s in content for s in ['91.2','82.4','78.6','84.1','88.7'])}
        # Save actual result text only for project experimental/data/report reads.
        file = call.get('path', '')
        selected_names = {'contractkv_manuscript.md', 'claim_evidence_map.md',
                          'terminology_ledger.md', 'tsc_service_evaluation_extension_report.md',
                          'tsc_service_evaluation_protocol.yaml'}
        if call['tool'] == 'Read' and call['main_writer'] and Path(file).name in selected_names:
            name = f"{len(evidence):03d}_"+Path(file).name+'.txt'
            snapshot = out/'visible_read_results'/name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_text(content, encoding='utf-8')
            row['historical_read_result'] = snapshot.relative_to(out).as_posix()
        evidence.append(row)
    report = {'cutoff_UTC': CUT, 'source_logs': logs,
              'reads_and_path_discoveries': evidence,
              'project_Read_calls': sum(r['tool']=='Read' for r in evidence),
              'project_Read_results_found': sum(r['tool']=='Read' and r['result_found'] for r in evidence),
              'public_numeric_mentions': visible_numeric_mentions,
              'complete_vector_before_insertion': [r for r in evidence if r['contains_five_target_values']],
              'new_model_calls': 0,
              'limits': ['Tool reads establish access, not a causal proof of how text was composed.',
                         'Path mentions in Bash are not promoted to file reads.',
                         'No hidden reasoning or complete conversations are exported.',
                         'Absence in these logs does not prove no external source ever existed.']}
    (out/'read_dependency_audit_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'project_Read_calls': report['project_Read_calls'],
                      'found_results': report['project_Read_results_found'],
                      'complete_vectors': len(report['complete_vector_before_insertion']),
                      'main_writer_project_reads': [r.get('path') for r in evidence if r['main_writer'] and r['tool']=='Read'],
                      'public_numeric_mentions': visible_numeric_mentions}, ensure_ascii=True))


if __name__ == '__main__':
    main()
