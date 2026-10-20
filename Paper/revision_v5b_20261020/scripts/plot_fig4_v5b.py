"""Update only Fig.4 from frozen measured data; preserve the other five figures."""
from pathlib import Path
import hashlib
import json
import plot_figures as plot

root=Path(__file__).resolve().parents[1]
out=root/'figures'
d=json.loads((out/'figure_data_v7.json').read_text())
d['restored']=json.loads((root/'evidence/restored_evidence.json').read_text())
d['mechanism_matrix']=json.loads((root/'evidence/V5b_evidence_register_v1.json').read_text())['mechanism_matrix']
plot.figure4(d,out)
record={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'shared_plot_code_sha256':hashlib.sha256((root/'scripts/plot_figures.py').read_bytes()).hexdigest(),
        'source_register_sha256':hashlib.sha256((root/'evidence/V5b_evidence_register_v1.json').read_bytes()).hexdigest(),
        'figures':plot.QA,'backend':'Python/matplotlib','measurement_changes':False}
(out/'render_manifest_v5b.json').write_text(json.dumps(record,indent=2)+'\n')
assert not plot.QA[0]['text_outside_canvas']
assert not plot.QA[0]['text_bbox_collisions'],plot.QA[0]['text_bbox_collisions']
print('Fig.4: vector PDF/SVG, 600-dpi PNG; bounds and text collisions PASS')
