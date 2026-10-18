"""Replay the frozen R4 auditor using the same explicit input-only adapter."""
from pathlib import Path
import hashlib
import json
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_r4_fidelity_adapter import installed_adapter
from scripts import tsc_revision_r4_live_summary


if __name__ == '__main__':
    root = Path(sys.argv[sys.argv.index('--root') + 1])
    freeze = json.loads((root / 'freeze.json').read_text(encoding='utf-8'))
    expected = {Path(row['path']).name: row['sha256'] for row in freeze['files'] if row['path'] in
                ('scripts/tsc_revision_r4_fidelity_live.py', 'scripts/tsc_revision_r4_fidelity_adapter.py',
                 'scripts/tsc_revision_r4_live.py')}
    for summary_path in (root / 'cells').glob('*/summary.json'):
        execution = json.loads(summary_path.with_name('input_adapter_execution_v1.json').read_text(encoding='utf-8'))
        actual = {Path(path).name: value for path, value in execution['source_files'].items()}
        if execution['result'] != 'completed' or not execution['unchanged_loop'] or actual != expected:
            raise ValueError('Missing or changed declared input-only adapter execution')
    with installed_adapter():
        tsc_revision_r4_live_summary.main()
