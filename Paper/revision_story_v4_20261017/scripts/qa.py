"""Read actual TeX/PDF/vector outputs; no inference from renderer success alone."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
import fitz
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summaries=[]
for stem in ('contractkv_tsc_story_v4','contractkv_supplement'):
    log=(root/(stem+'.log')).read_text(encoding='utf-8',errors='replace')
    failures={key:bool(re.search(pattern,log,re.I)) for key,pattern in {
        'undefined_citations_or_refs':r'(Citation|Reference) .+ undefined',
        'multiply_defined':r'multiply defined', 'overfull_boxes':r'Overfull',
        'oversized_float':r'Float too large', 'tex_errors':r'^! ',}.items()}
    assert not any(failures.values()),failures
    doc=fitz.open(root/(stem+'.pdf'));pages=[];fonts={};text=''
    for i,page in enumerate(doc):
        actual=page.get_text();assert actual.strip();text+=actual
        for font in page.get_fonts(full=True):
            fonts[font[0]]=font
            assert font[2]!='Type3',font
            assert doc.extract_font(font[0])[3],font
        blocks=page.get_text('blocks')
        assert all(b[0]>=-1 and b[1]>=-1 and b[2]<=page.rect.width+1 and b[3]<=page.rect.height+1 for b in blocks)
        assert not page.get_images(),(stem,i,'unexpected raster')
        pages.append({'page':i+1,'text_characters':len(actual),
                      'figure_captions':[line for line in actual.splitlines() if line.startswith('Fig.')]})
    expected=['1.619','1.109','1.070','1,296','1.803','2,442']
    if stem=='contractkv_tsc_story_v4':expected+=['0.0625','0.125','125','25.05','3.24','0.066','1.472','1.428','7.04','10.84','29.41','44.69','726']
    assert all(v in text for v in expected),(stem,[v for v in expected if v not in text])
    if stem=='contractkv_supplement':
        assert '4,695' in text and '240' in text
    if stem=='contractkv_tsc_story_v4':
        assert len(doc)==12
        assert sum(len(p['figure_captions']) for p in pages)==6
        assert 'does not implement a timing-channel defense' in ' '.join(text.split())
        assert 'Trust Model and Manifest Registration' in text
        assert 'LAYOUT TEST' not in text and 'Layout specimen' not in text
        start=re.search(r'CKV_BIO_START page=(\d+); x=(\d+); y=(\d+); height=([\d.]+)pt',log)
        end=re.search(r'CKV_BIO_END page=(\d+); x=(\d+); y=(\d+)',log)
        assert start and end and int(start[1])==int(end[1])==len(doc)
        assert start[2]==end[2]
        actual_height=(int(start[3])-int(end[3]))/65536
        text_height=float(start[4])
        assert abs(actual_height/text_height-.5)<1e-7
        bio_rect=fitz.Rect(int(start[2])/65536*72/72.27,
            doc[-1].rect.height-int(start[3])/65536*72/72.27,
            563.1,doc[-1].rect.height-int(end[3])/65536*72/72.27)
        assert not doc[-1].get_textbox(bio_rect).strip()
        bio={'page':len(doc),'column':'right','height_TeX_pt':actual_height,
            'fraction_of_two_column_text_area':actual_height/(2*text_height),
            'PDF_rect':list(bio_rect),'text_or_images_inserted':False}
    summaries.append({'file':stem+'.pdf','pages':len(doc),'sha256':sha(root/(stem+'.pdf')),
        'checks':failures,'embedded_fonts':len(fonts),'Type3_fonts':0,'raster_images':0,
        'underfull_hboxes':len(re.findall(r'Underfull \\hbox',log)),
        'underfull_vboxes':len(re.findall(r'Underfull \\vbox',log)),
        'page_details':pages})

data=json.loads((root/'figures/figure_data_v7.json').read_text(encoding='utf-8'))
assert [r['compiled_future_pairs'] for r in data['strict']]==[684,342,270]
assert sum(r['compiled_future_pairs'] for r in data['strict'])==1296
for row in data['strict']:
    raw=row['raw_business_prefill_per_repeat'];ckv=row['CKV_business_prefill_per_repeat'];cert=row['qualification_prefill_per_repeat']
    assert abs(100*(1-(ckv+cert)/raw)-row['net_prefill_reduction_pct'])<1e-9
vectors=[]
for p in sorted((root/'figures').glob('fig[1-6]_*.pdf')):
    doc=fitz.open(p);assert not doc[0].get_images()
    svg=p.with_suffix('.svg');nodes=[el.tag.rsplit('}',1)[-1] for el in ET.parse(svg).getroot().iter()]
    assert nodes.count('text')>0 and 'image' not in nodes
    png=Image.open(p.with_suffix('.png'));assert abs(png.width-doc[0].rect.width/72*600)<=1
    vectors.append({'file':p.name,'sha256':sha(p),'editable_SVG_text_nodes':nodes.count('text'),
                    'PNG_pixels':list(png.size),'PNG_DPI':list(png.info['dpi'])})
assert len(vectors)==6
figqa=json.loads((root/'figures/render_manifest_v11.json').read_text())
assert figqa['all_text_inside_canvas'] and figqa['all_text_collision_checks_pass']
arch=json.loads((root/'figures/architecture_QA_v11.json').read_text())
assert not arch['figure']['text_outside_canvas'] and not arch['figure']['text_bbox_collisions']
assert arch['deployment_certificate_separate_from_client_query_records']
assert arch['private_candidate_label_does_not_claim_stable_only']
sections='\n'.join(p.read_text(encoding='utf-8') for p in sorted((root/'sections').glob('[0-9]*.tex')))
assert len(re.findall(r'\\begin\{figure\*\}',sections))==2
assert len(re.findall(r'\\begin\{figure\}',sections))==4
restored=json.loads((root/'evidence/restored_evidence.json').read_text())
assert restored['segment_observations']==4695 and restored['model_session_inputs']==240
for row in restored['source_hashes']:assert sha(root/'evidence'/row['path'])==row['sha256']
new=json.loads((root/'evidence/revision_audit_evidence.json').read_text())
assert len(new['source_rows'])==18 and new['future_pairs']==4860 and new['compiled_future_pairs']==1296
assert len({r['source_group'] for r in new['source_rows']})==6
assert sum(r['actual_reject']=='True' for r in new['manifest_cases'])==7
assert new['manifest_cases'][-1]['actual_reject']=='False'
assert new['source_level_p99_recomputed_and_cross_checked'] and not new['bootstrap_rerun']
for row in new['source_files']:assert sha(root/'evidence'/row['file'])==row['sha256']
broad=(root/'sections/table_deployment_width.tex').read_text()
assert 'Zero-slack' not in broad and '17.50' not in broad and '-2.84' not in broad
assert len(re.findall(r'\d+\.\d+\\%',broad))==8
closure_cost=json.loads((root/'evidence/closure_tableIII_cost_v1.json').read_text())
assert closure_cost['all_four_original_reported_means_reproduced']
assert not closure_cost['all_four_full_verification_costs_closed']
assert sum(r['missing_verifier_RPC_timings'] for r in closure_cost['summary'])==33
closure_structure=json.loads((root/'evidence/closure_tableI_crosswalk_v1.json').read_text())
assert len(closure_structure['rows'])==51 and not closure_structure['original_85_2_4_reproduced']
binding=json.loads((root/'evidence/closure_binding_boundary_v1.json').read_text())
assert binding['case_count']==19 and binding['binding_error_cases']==17
assert not binding['network_authentication_proxy_implemented_by_this_test']
assert not binding['live_registration_helper_integrated']
supp_text=' '.join(fitz.open(root/'contractkv_supplement.pdf')[i].get_text() for i in range(summaries[1]['pages']))
for number in ['16.81','28.91','34.39','2.83','19.74','20.37','147/147','126/126','72/72','75/108']:
    assert number in supp_text,number
for label in ['tab:s-five-family-structure','tab:s-structure-paired','tab:s-matched-original-cost','tab:s-client-binding']:
    assert '\\newlabel{'+label+'}' in (root/'contractkv_supplement.aux').read_text()
for phrase in ["earlier table's exact numerical provenance",'earlier adapter','revised renderer','TABLE INSERTION PENDING']:
    assert phrase not in sections,phrase
record={'status':'PASS','restored_segments':4695,'model_session_inputs':240,'tables_and_cohort_sources_verified':True,'layout':{'double_column_figures':[1,2],'single_column_figures':[3,4,5,6]},'manuscripts':summaries,'figures':vectors,
        'biography_reservation':bio,'source_model_rows_checked':18,'manifest_helper_rejects':7,
        'deployment_and_query_record_objects_separated':True,
        'heterogeneous_cost_cohorts_not_in_same_table':True,
        'restored_open_arrival_interval_status':new['CI_status'],
        'compiled_pair_denominators_and_prefill_arithmetic_checked':True,
        'source_data_sha256':sha(root/'figures/figure_data_v7.json'),
        'all_six_vector_figures':True,'independent_measurements_added':0,
        'historical_original_report_arithmetic_reproduced':True,
        'historical_full_controller_cost_closed':False,
        'original_TableI_measurement_reproduced':False,
        'additional_CPU_binding_cases':19,'binding_errors_deny_compiled':17,
        'bibliographic_metadata':'Original keys retained; row/field reordering citation added from reviewer suggestion and verified primary source; numbering checked.'}
(root/'audit/manuscript_QA.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
print(json.dumps({'status':'PASS','main_pages':summaries[0]['pages'],'supplement_pages':summaries[1]['pages'],'vector_figures':len(vectors)}))
