"""Audit actual PDFs, delivered evidence, numeric ledgers and biography space."""
from pathlib import Path
import csv, hashlib, json, re, xml.etree.ElementTree as ET
import fitz

root=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
register=json.loads((root/'evidence/V5b_evidence_register_v1.json').read_text())
for item in register['source_summaries']:
    assert sha(root/'evidence'/item['file'])==item['sha256'],item['file']
auth=json.loads((root/'evidence/authorization_summary_v1.json').read_text())
assert auth['business_requests']==828 and auth['formal_cells']==9
assert all(v['supported']==v['total']==63 for v in auth['primary_namespace_check_counts'].values())
assert not auth['authorization_or_reuse_observation_violations']
assert auth['rejected_qualification_added_published_tokens']==0
assert auth['stale_request_identities_denied']==63
effects=json.loads((root/'evidence/mechanism_effects_v1.json').read_text())
rows=[r for r in effects['model_totals'] if r['population']=='all_observed_candidates'];m=register['mechanism_matrix']
for key,source in [('observed_changed','observed_ID_or_finish_changes'),('changed_rejected','changed_candidates_conclusively_rejected'),('unchanged','behavior_unchanged_candidates'),('unchanged_admitted','unchanged_candidates_admitted'),('material_decreases','observed_task_score_decreases')]:
    assert m[key]==sum(r[source] for r in rows),(key,source)
assert effects['behavior_candidates']==180
assert sum(r['rejected_actual_published_tokens'] for r in rows)==0
assert 180-sum(r['verification_RPC_attempts'] for r in rows)==18
history=json.loads((root/'evidence/growing_history_metrics_v1.json').read_text())
assert history['all_requests']==3750 and history['future_requests']==3375
assert history['all_actual_prompt_IDs_independently_checked']
ruler=json.loads((root/'evidence/ruler_ci_v1.json').read_text())
assert abs(ruler['macro_point_pct']-86.6723032577496)<1e-10
assert abs(ruler['posthoc_synchronized_source_process95_pct'][0]-86.3204074321047)<1e-10
sens=json.loads((root/'evidence/task_arrival_sensitivity_v1.json').read_text())
main_rows=[r for r in sens['results'] if r['regime']!='gate']
assert len(main_rows)==4
assert all(r['conditional_absolute_change_interval'][0]<0<r['conditional_absolute_change_interval'][1] for r in main_rows)
legacy=list(csv.DictReader((root/'evidence/fullcost_quality_pairs_v1.csv').open()))
assert len(legacy)==4725
legacy_bad=[r for r in legacy if r['compiled_route']=='True' and r['score_down']=='True']
assert len(legacy_bad)==1 and legacy_bad[0]['sample_id']=='389'

records=[];all_text={}
for stem in ['contractkv_tsc_v5b','contractkv_supplement']:
    log=(root/(stem+'.log')).read_text(errors='replace')
    patterns={'undefined_reference_or_citation':r'(?:LaTeX Warning: (?:Reference|Citation).*undefined|There were undefined references)',
              'duplicate_label':r'multiply defined','overfull_box':r'Overfull','oversize_float':r'Float too large','tex_error':r'^! '}
    checks={k:bool(re.search(v,log,re.M)) for k,v in patterns.items()}
    assert not any(checks.values()),(stem,checks)
    doc=fitz.open(root/(stem+'.pdf'));all_text[stem]=' '.join(p.get_text() for p in doc)
    fonts={};pages=[]
    for i,page in enumerate(doc):
        assert page.get_text().strip(),(stem,i)
        for f in page.get_fonts(full=True):
            assert f[2]!='Type3' and doc.extract_font(f[0])[3],f
            fonts[f[0]]=f[3]
        for b in page.get_text('blocks'):
            assert b[0]>=-1 and b[1]>=-1 and b[2]<=page.rect.width+1 and b[3]<=page.rect.height+1,(stem,i,b[:4])
        assert not page.get_images(),(stem,i,'unexpected raster')
        pages.append({'page':i+1,'characters':len(page.get_text())})
    records.append({'file':stem+'.pdf','pages':len(doc),'sha256':sha(root/(stem+'.pdf')),'checks':checks,'embedded_fonts':len(fonts),'raster_images':0,'page_details':pages})
main=all_text['contractkv_tsc_v5b'];supp=all_text['contractkv_supplement']
for value in ['1.619','1.109','1.070','1,296','1.803','2,442','48.05','40.69','38.38','5.242','102','180','828','63/63','0/63','94.144','0.595']:
    assert value in main,('main missing',value)
for value in ['86.6723','86.3204','86.9911','3,750','3,375','1,178','0.72','0.38']:
    assert value in supp,('supp missing',value)
assert 'does not implement a timing-channel defense' in ' '.join(main.split())
assert 'Reviewer-requested' not in main and 'requested by the reviewers' not in main
assert 'TABLE INSERTION PENDING' not in main+supp
assert records[0]['pages']==12
log=(root/'contractkv_tsc_v5b.log').read_text(errors='replace')
start=re.search(r'CKV_BIO_START page=(\d+); x=(\d+); y=(\d+); height=([\d.]+)pt',log)
end=re.search(r'CKV_BIO_END page=(\d+); x=(\d+); y=(\d+)',log)
assert start and end and start[1]==end[1]=='12' and start[2]==end[2]
height=(int(start[3])-int(end[3]))/65536;text_height=float(start[4])
assert abs(height/text_height-.5)<1e-7
doc=fitz.open(root/'contractkv_tsc_v5b.pdf')
rect=fitz.Rect(int(start[2])/65536*72/72.27,doc[-1].rect.height-int(start[3])/65536*72/72.27,
              563.1,doc[-1].rect.height-int(end[3])/65536*72/72.27)
assert not doc[-1].get_textbox(rect).strip()

figs=[]
for i in range(1,7):
    paths=list((root/'figures').glob(f'fig{i}_*.pdf'));assert len(paths)==1
    pdf=paths[0];d=fitz.open(pdf);assert len(d)==1 and not d[0].get_images()
    svg=pdf.with_suffix('.svg');tags=[x.tag.rsplit('}',1)[-1] for x in ET.parse(svg).getroot().iter()]
    assert 'text' in tags and 'image' not in tags
    figs.append({'file':pdf.name,'PDF_sha256':sha(pdf),'editable_SVG_text_nodes':tags.count('text')})
q=json.loads((root/'figures/render_manifest_v5b.json').read_text())['figures'][0]
assert not q['text_outside_canvas'] and not q['text_bbox_collisions']
source='\n'.join(p.read_text() for p in (root/'sections').glob('[0-9]*.tex'))
assert len(re.findall(r'\\begin\{figure\*\}',source))==2
assert len(re.findall(r'\\begin\{figure\}',source))==4
assert r'48.05\\%' not in source and r'.\n\n\noindent' not in source
relocation_path=root/'audit/evaluation_focus_relocation_v1.json'
if relocation_path.exists():
    moved=json.loads(relocation_path.read_text())
    support=(root/'sections/supplement_supporting_audits.tex').read_text()
    assert len(moved['moves'])==5 and not moved['measurements_changed']
    assert '0.40625' not in source and '3,672' not in source
    for value in ['0.40625','3,672','108','642','769','578','224','1.803','1.798','1.808','0.22222','0.12067','0.36667','224 decreases','331 increases']:
        assert value in support,('relocated evidence missing',value)
    for label in ['sec:s-development-scope','sec:s-output-horizon','sec:s-second-qwen','sec:s-input-cost-controls','sec:s-external-reference']:
        assert ('\\label{'+label+'}') in support
        assert ('\\ref{supp-'+label+'}') in source
review=fitz.open()
for row in figs:
    with fitz.open(root/'figures'/row['file']) as d:review.insert_pdf(d)
review.save(root/'figures/Fig1-6_review.pdf');review.close()
out={'status':'PASS','new_model_requests':0,'experimental_data_changed':False,'manuscripts':records,
     'layout':{'double_column_figures':[1,2],'single_column_figures':[3,4,5,6]},
     'biography_reservation':{'page':12,'fraction_of_two_column_text_area':height/(2*text_height),'rect':list(rect),'author_details_invented':False},
     'figures':figs,'source_summaries_SHA_verified':len(register['source_summaries']),
     'authorization_physical_controls_verified':True,'actual_rejection_matrix_verified':True,
     'legacy_quality_exception_retained':True,'HotpotQA_rendered_paragraph_complete':True,
     'scope':'Defined numerical, source-integrity, PDF/font and layout checks; interpretation additionally reviewed manually.'}
(root/'audit/manuscript_QA_v5b.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'status':'PASS','main_pages':records[0]['pages'],'supplement_pages':records[1]['pages'],'biography_fraction':height/(2*text_height),'figures':len(figs)}))
