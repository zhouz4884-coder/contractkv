"""Rebuild in a new directory and compare outputs; never makes model requests."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

import fitz

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
dest = args.output.resolve()
assert dest != root and not dest.exists(), 'Use a new output directory.'
stems = ['fig1_architecture', 'fig2_full_cost_benefits',
         'fig3_coverage_and_fidelity', 'fig4_transaction_and_amortization',
         'fig5_service_goodput_and_kv_savings', 'fig6_locality_and_residency']
compared = [f'figures/{s}.{e}' for e in ['pdf', 'svg', 'png'] for s in stems]
compared += ['sections/table_deployment_width.tex', 'sections/table_frozen_gate.tex',
             'sections/supplement_restored_tables.tex',
             'sections/supplement_service_breadth.tex',
             'sections/supplement_revision_audit.tex',
             'sections/supplement_evidence_closure.tex',
             'evidence/restored_evidence.json', 'evidence/revision_audit_evidence.json',
             'audit/evidence_locations.csv', 'audit/paper_evidence_topics.csv']
skip = set(compared + ['contractkv_tsc_story_v4.pdf', 'contractkv_supplement.pdf',
                      'figures/Fig1-6_review.pdf', 'audit/manuscript_QA.json',
                      'audit/independent_reproduction.json', 'audit/package_manifest.json'])
allowed = {'.tex', '.py', '.sh', '.md', '.json', '.jsonl', '.csv', '.pdf', '.svg', '.png', '.txt'}
for path in root.rglob('*'):
    if not path.is_file() or path.suffix not in allowed or '__pycache__' in path.parts:
        continue
    rel = path.relative_to(root).as_posix()
    if rel in skip or '_compile_pass' in path.name:
        continue
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
commands = ['restore_evidence.py', 'restore_revision_audit.py',
            'restore_closure_tables.py', 'plot_figures.py', 'plot_architecture.py',
            'build.py', 'qa.py', 'locate_evidence.py']
logs = []
for script in commands:
    result = subprocess.run([sys.executable, '-B', str(dest / 'scripts' / script)],
                            cwd=dest, capture_output=True)
    (dest / 'audit' / ('reproduce_' + script + '.txt')).write_bytes(
        result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr).decode(errors='replace')[-4000:])
        raise SystemExit(result.returncode)
    logs.append({'script': script, 'exit_code': result.returncode})
    print(script + ': PASS', flush=True)

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for rel in compared:
    assert sha(root / rel) == sha(dest / rel), rel
manuscripts = []
for stem in ['contractkv_tsc_story_v4', 'contractkv_supplement']:
    original = fitz.open(root / (stem + '.pdf'))
    rebuilt = fitz.open(dest / (stem + '.pdf'))
    assert len(original) == len(rebuilt)
    assert all(a.get_text() == b.get_text() for a, b in zip(original, rebuilt))
    assert all(a.get_pixmap(matrix=fitz.Matrix(.5, .5), alpha=False).samples ==
               b.get_pixmap(matrix=fitz.Matrix(.5, .5), alpha=False).samples
               for a, b in zip(original, rebuilt))
    manuscripts.append({'file': stem + '.pdf', 'pages': len(original),
                        'all_page_text_equal': True,
                        'all_half_scale_page_pixels_equal': True})
record = {'status': 'PASS', 'reproduction_directory': str(dest),
          'fresh_generated_exports': 18,
          'byte_identical_generated_outputs': len(compared),
          'compared_files': compared, 'commands': logs, 'manuscripts': manuscripts,
          'comparison': 'Generated exports, tables, aggregates and indices are byte-identical. '
                        'Manuscript pages have equal text and half-scale rendered pixels; '
                        'PDF byte identity is not claimed.',
          'new_model_calls': 0, 'historical_missing_data_not_imputed': True}
(root / 'audit/independent_reproduction.json').write_text(
    json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'PASS', 'compared_outputs': len(compared),
                  'manuscripts': manuscripts}), flush=True)
