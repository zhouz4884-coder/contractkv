"""Offline explanation only; retain the frozen metric and reported decrease."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from scripts.phase20a_official_quality import normalize_answer,qa_f1

base=Path('results/tsc_revision_r4/development_pilot_v1')
path=base/'fallback_variation_triage_v1.json';data=json.loads(path.read_text(encoding='utf-8'))
reference=data['gold_answers_for_offline_metric_inspection_only'][0];target=normalize_answer(reference).split();details={}
for policy,record in data['outputs'].items():
    tokens=normalize_answer(record['output_text']).split();overlap=sum((Counter(tokens)&Counter(target)).values())
    score=qa_f1(record['output_text'],reference)
    if abs(score-record['task_score'])>1e-12:raise ValueError('Frozen score mismatch')
    details[policy]={'normalized_prediction':tokens,'normalized_reference':target,'prediction_words':len(tokens),
                     'reference_words':len(target),'overlapping_words_with_multiplicity':overlap,'unchanged_frozen_F1':score}
data['offline_metric_explanation']={'scorer_sha256':hashlib.sha256(Path('scripts/phase20a_official_quality.py').read_bytes()).hexdigest(),
    'details':details,'observed_text_change':'her other children -> the other children; one output token differs at index7; both outputs retain Eliza favors her son.',
    'interpretation':'The measured F1 decrease is explained by the unchanged article-removal and word-overlap formula: overlap6/length8 versus overlap5/length7 against reference length7. This is a descriptive text comparison, not a new semantic correctness score.',
    'retained_material_drop':True,'generation_and_metric_changed':False,
    'numerical_cause':'Unknown; same prompt IDs, same112 native prefix-hit tokens and2505 newly prefilled tokens do not identify a causal batch/numerical mechanism.'}
path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data['offline_metric_explanation']))
