"""Locate visible Table-I writing actions without treating prose as measurements.

Only code/tool actions and table excerpts are exported. Private reasoning blocks
and complete conversation histories are never copied into the research artifact.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=Path('results/tsc_revision_evidence_closure_20261017/tableI_lineage'))
    args = p.parse_args()
    home = Path.home()
    task = home / '.qoderworkcn/projects/C--Users-LENOVO--qoderworkcn-workspace-mri0jcwxlbhztija'
    main_log = task / '6d0a87bc-7882-47e5-9d08-242d26a8a181.jsonl'
    writing = []
    plot_writes = []
    for number, line in enumerate(main_log.open(encoding='utf-8'), 1):
        row = json.loads(line)
        message = row.get('message', {})
        content = message.get('content', []) if isinstance(message, dict) else []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            data = block.get('input', {})
            new = data.get('new_string', data.get('content', ''))
            if all(value in new for value in ['91.2', '82.4', '78.6', '84.1', '88.7']) and 'tab:motivation' in new:
                match = re.search(r'\\begin\{table\}.*?\\end\{table\}', new, re.S)
                writing.append({'timestamp_UTC': row.get('timestamp'), 'session_line': number,
                    'tool': block.get('name'), 'target_path': data.get('file_path'),
                    'old_text': data.get('old_string', ''), 'table_text': match[0] if match else '',
                    'new_text_sha256': hashlib.sha256(new.encode()).hexdigest()})
            if str(data.get('file_path', '')).endswith('gen_tsc_figures.py') and 'stable_ratio' in new:
                plot_writes.append({'timestamp_UTC': row.get('timestamp'), 'session_line': number,
                    'tool': block.get('name'), 'target_path': data.get('file_path')})
    assert writing
    first = writing[0]
    assert 'To be written' in first['old_text']
    # Scan earlier visible tool results for the complete target family vector.
    # Other occurrences of e.g. 82.46 ms are not Table-I observations.
    earlier_vector = []
    visible_results = 0
    for path in task.rglob('*.jsonl'):
        for number, line in enumerate(path.open(encoding='utf-8'), 1):
            row = json.loads(line)
            if str(row.get('timestamp', '')) >= first['timestamp_UTC']:
                continue
            message = row.get('message', {})
            content = message.get('content', []) if isinstance(message, dict) else []
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get('type') != 'tool_result':
                    continue
                visible_results += 1
                text = json.dumps(block.get('content', ''), ensure_ascii=False)
                if all(value in text for value in ['91.2', '82.4', '78.6', '84.1', '88.7']):
                    earlier_vector.append({'file': str(path.relative_to(task)), 'line': number})
    plot = home / '.qoderworkcn/workspace/mri0jcwxlbhztija/gen_tsc_figures.py'
    tree = ast.parse(plot.read_text(encoding='utf-8'))
    constants = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {'stable_ratio', 'native_recovery'}:
                    constants[target.id] = {'line': node.lineno, 'value': ast.literal_eval(node.value)}
    assert constants['stable_ratio']['value'] == [91.2, 82.4, 78.6, 84.1, 88.7]
    assert constants['native_recovery']['value'] == [2.8, 2.1, 1.9, 2.4, 2.6]
    git = []
    for ref, file in [('c377031', 'README_ContractKV.md'), ('dcfa7d2', 'submission/contractkv_tsc.tex')]:
        blob = subprocess.check_output(['git', 'show', ref + ':' + file])
        stamp = subprocess.check_output(['git', 'show', '-s', '--format=%H %aI', ref], text=True).strip()
        git.append({'commit_and_author_date': stamp, 'file': file, 'blob_sha256': hashlib.sha256(blob).hexdigest()})
    report = {'status': 'Writing lineage located; original measurement lineage not located',
        'first_visible_table_insertion': first,
        'visible_tool_results_examined_before_insertion': visible_results,
        'earlier_complete_target_vectors_in_visible_tool_results': earlier_vector,
        'plot_source': {'path': str(plot), 'sha256': sha(plot), 'literal_constants': constants,
                        'writing_actions': plot_writes},
        'source_session_sha256': sha(main_log), 'git_snapshots': git,
        'arithmetic_only': {'mean_stable_pct': sum(constants['stable_ratio']['value']) / 5,
                            'mean_recovery_pct_before_rounding': sum(constants['native_recovery']['value']) / 5},
        'measurement_reproduction': False,
        'limits': ['Visible writing actions and plotting constants are not raw measurements.',
                  'No conclusion about a human author\'s intent is established.',
                  'An earlier measurement outside the examined records is not ruled out.',
                  'Neither the multi-turn-history hypothesis nor a prior numeric snapshot has been authenticated.']}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'lineage_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.output/'first_table_insertion.tex').write_text(first['table_text']+'\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'first_timestamp_UTC': first['timestamp_UTC'],
                      'first_session_line': first['session_line'], 'earlier_matching_vectors': len(earlier_vector)}))


if __name__ == '__main__':
    main()
