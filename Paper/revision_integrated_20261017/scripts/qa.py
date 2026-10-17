"""Read actual TeX/PDF/vector outputs; no inference from renderer success alone."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
import fitz
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summaries=[]
for stem in ('contractkv_tsc_integrated','contractkv_supplement'):
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
    if stem=='contractkv_tsc_integrated':expected+=['0.0625','0.125']
    assert all(v in text for v in expected),(stem,[v for v in expected if v not in text])
    if stem=='contractkv_tsc_integrated':
        assert len(doc)==12
        assert sum(len(p['figure_captions']) for p in pages)==6
        assert 'does not implement a timing-channel defense' in ' '.join(text.split())
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
figqa=json.loads((root/'figures/render_manifest_v9.json').read_text())
assert figqa['all_text_inside_canvas'] and figqa['all_text_collision_checks_pass']
arch=json.loads((root/'figures/architecture_QA_v9.json').read_text())
assert not arch['figure']['text_outside_canvas'] and not arch['figure']['text_bbox_collisions']
sections='\n'.join(p.read_text(encoding='utf-8') for p in sorted((root/'sections').glob('[0-9]*.tex')))
assert len(re.findall(r'\\begin\{figure\*\}',sections))==2
assert len(re.findall(r'\\begin\{figure\}',sections))==4
record={'status':'PASS','layout':{'double_column_figures':[1,2],'single_column_figures':[3,4,5,6]},'manuscripts':summaries,'figures':vectors,
        'compiled_pair_denominators_and_prefill_arithmetic_checked':True,
        'source_data_sha256':sha(root/'figures/figure_data_v7.json'),
        'all_six_vector_figures':True,'independent_measurements_added':0,
        'bibliographic_metadata':'retained from supplied draft; keys and first-use ordering checked offline'}
(root/'audit/manuscript_QA.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
print(json.dumps({'status':'PASS','main_pages':summaries[0]['pages'],'supplement_pages':summaries[1]['pages'],'vector_figures':len(vectors)}))
